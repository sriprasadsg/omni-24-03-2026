import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import ValidationError
from pymongo import ReturnDocument

from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database, TenantIsolatedDatabase
from itam_catalog_service import count_field_usage_keys, flatten_fieldsets, validate_fieldsets
from itam_models import (
    AssetModelCreate,
    AssetModelUpdate,
    CatalogEntityCreate,
    CatalogEntityUpdate,
    SupplierCreate,
    SupplierUpdate,
)
from rbac_utils import verify_permission
from rbac_service import rbac_service as _rbac_service
from api_key_auth import get_current_user_or_api_key
from itam_audit_service import log_itam_action, catalog_resource_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itam/catalog", tags=["ITAM Catalog"])

CATALOG_KINDS: Dict[str, str] = {
    "manufacturers": "manufacturers",
    "categories": "asset_categories",
    "locations": "locations",
    "suppliers": "suppliers",
    "models": "asset_models",
}

# Cap the per-key usage-count fan-out on GET /models/{model_id}/fields so a model with an
# unreasonable number of declared field keys cannot turn one request into an unbounded burst
# of count_documents calls (T-65-01-04).
_MAX_USAGE_COUNT_KEYS = 50

CATALOG_REFERENCE_FIELDS: Dict[str, str] = {
    "manufacturers": "manufacturerId",
    "categories": "categoryId",
    "locations": "locationId",
    "suppliers": "supplierId",
    "models": "modelId",
}

# Per-kind request-body shapes. A kind absent from this registry falls back to the base
# CatalogEntityCreate/CatalogEntityUpdate pair. A single generic route cannot express five
# different Pydantic body types in its signature, so the body is typed loosely at the
# signature (Dict[str, Any]) and validated explicitly against the resolved model below.
CATALOG_MODELS: Dict[str, Tuple[type, type]] = {
    "suppliers": (SupplierCreate, SupplierUpdate),
    "models": (AssetModelCreate, AssetModelUpdate),
}


def _resolve_models(kind: str) -> Tuple[type, type]:
    return CATALOG_MODELS.get(kind, (CatalogEntityCreate, CatalogEntityUpdate))


def _validation_error_to_http(exc: ValidationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors())


async def _require_itam_admin(current_user: TokenData = Depends(get_current_user_or_api_key)):
    """
    Dependency to ensure the caller has 'manage:assets' permission — session
    or API-key authenticated (D-01/D-02, ITAM-API-01).

    NOTE: this is an INDEPENDENT DUPLICATE of itam_asset_endpoints._require_itam_admin
    (same permission string, different 403 detail text — it is not an import).
    Both definitions must move together on any future change to the D-01/D-02
    auth swap; a grep-only migration would miss this one entirely (T-73-04).

    Enforcement order mirrors the canonical guard: role check first
    (verify_permission), then scope narrowing (_rbac_service._scopes_allow) —
    closes RESEARCH.md Pitfall 1 for this router too.
    """
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to manage ITAM catalog entities"
        )
    if not _rbac_service._scopes_allow(current_user, "manage:assets"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key scope does not permit: manage:assets"
        )
    return current_user

def _resolve_kind(kind: str) -> str:
    """
    Resolves the URL 'kind' segment to its corresponding MongoDB collection name.
    Raises HTTPException 404 if the kind is not registered.
    """
    collection_name = CATALOG_KINDS.get(kind)
    if not collection_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog kind '{kind}' not found"
        )
    return collection_name


async def _validate_asset_model_references(document: Dict[str, Any], db: TenantIsolatedDatabase) -> None:
    """
    Per-kind post-validation hook for the 'models' kind: confirm a supplied manufacturerId
    exists in the manufacturers collection and a supplied categoryId exists in the
    asset_categories collection, raising 400 naming the field that failed, then validate the
    model's fieldsets and translate a structural violation into 400. Reference existence is
    checked at write time only — this codebase enforces no Mongo-level foreign keys and none
    is introduced here.
    """
    manufacturer_id = document.get("manufacturerId")
    if manufacturer_id and not await db.manufacturers.find_one({"id": manufacturer_id}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"manufacturerId '{manufacturer_id}' not found."
        )

    category_id = document.get("categoryId")
    if category_id and not await db.asset_categories.find_one({"id": category_id}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"categoryId '{category_id}' not found."
        )

    try:
        validate_fieldsets(document.get("fieldsets") or [])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@router.post("/{kind}", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_catalog_entity(
    kind: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """
    Creates a new ITAM catalog entity (e.g., manufacturer, category, location, supplier, model).
    """
    collection_name = _resolve_kind(kind)
    create_model, _ = _resolve_models(kind)
    try:
        validated = create_model(**payload)
    except ValidationError as exc:
        raise _validation_error_to_http(exc)

    db = get_database()
    collection: AsyncIOMotorCollection = db[collection_name]

    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds') + 'Z'
    entity_id_prefix = kind[:-1] if kind.endswith('s') else kind # manufacturers -> manufacturer
    new_id = f"{entity_id_prefix}-{uuid.uuid4().hex[:8]}"

    document = validated.model_dump(exclude_none=True)
    document.update({
        "id": new_id,
        "tenantId": current_user.tenant_id,
        "createdAt": now,
        "updatedAt": now,
    })

    if kind == "models":
        await _validate_asset_model_references(document, db)

    try:
        await collection.insert_one(document)
        document.pop("_id", None) # Remove MongoDB's internal _id
        await log_itam_action(
            current_user,
            action=f"{catalog_resource_type(kind)}.create",
            resource_type=catalog_resource_type(kind),
            resource_id=new_id,
            details=f"Created {kind} entity {document.get('name', new_id)}",
        )
        return document
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create catalog entity {kind}/{new_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create {kind}."
        )

@router.get("/{kind}", status_code=status.HTTP_200_OK, response_model=List[Dict[str, Any]])
async def list_catalog_entities(
    kind: str,
    limit: int = Query(200, ge=1, le=500),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """
    Retrieves a list of ITAM catalog entities.
    """
    collection_name = _resolve_kind(kind)
    db = get_database()
    collection: AsyncIOMotorCollection = db[collection_name]

    entities = await collection.find({}, {"_id": 0}).limit(limit).to_list(length=limit)
    return entities

@router.get("/models/{model_id}/fields", status_code=status.HTTP_200_OK, response_model=Dict[str, Any])
async def get_asset_model_fields(
    model_id: str,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """
    Returns an asset Model's custom-field definitions flattened for display, plus a
    per-key usage count of how many assets currently carry a value for each key.

    Declared before the generic `GET /{kind}/{entity_id}` route so the literal `models`
    path segment here is matched first and is not swallowed by that route's `{kind}`
    parameter.
    """
    db = get_database()
    doc = await db.asset_models.find_one({"id": model_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Model with ID '{model_id}' not found")

    usage_counts: Dict[str, int] = {}
    usage_counts_truncated = False
    try:
        keys = count_field_usage_keys(doc)
        if len(keys) > _MAX_USAGE_COUNT_KEYS:
            usage_counts_truncated = True
            keys = keys[:_MAX_USAGE_COUNT_KEYS]
        for key in keys:
            usage_counts[key] = await db.assets.count_documents({
                "modelId": model_id,
                f"customFields.{key}": {"$exists": True},
            })
    except Exception as e:
        logger.error(f"Failed to compute custom-field usage counts for model {model_id}: {e}")
        usage_counts = {}
        usage_counts_truncated = False

    response: Dict[str, Any] = {
        "modelId": model_id,
        "modelName": doc.get("name"),
        "fieldsets": doc.get("fieldsets") or [],
        "fields": flatten_fieldsets(doc),
        "usageCounts": usage_counts,
    }
    if usage_counts_truncated:
        response["usageCountsTruncated"] = True
    return response


@router.get("/{kind}/{entity_id}", status_code=status.HTTP_200_OK, response_model=Dict[str, Any])
async def get_catalog_entity_by_id(
    kind: str,
    entity_id: str,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """
    Retrieves a specific ITAM catalog entity by its ID.
    """
    collection_name = _resolve_kind(kind)
    db = get_database()
    collection: AsyncIOMotorCollection = db[collection_name]

    entity = await collection.find_one({"id": entity_id}, {"_id": 0})
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind.capitalize()} with ID '{entity_id}' not found")
    return entity

@router.patch("/{kind}/{entity_id}", status_code=status.HTTP_200_OK, response_model=Dict[str, Any])
async def update_catalog_entity(
    kind: str,
    entity_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(_require_itam_admin),
):
    """
    Updates an existing ITAM catalog entity.
    """
    collection_name = _resolve_kind(kind)
    _, update_model = _resolve_models(kind)
    try:
        validated = update_model(**payload)
    except ValidationError as exc:
        raise _validation_error_to_http(exc)

    db = get_database()
    collection: AsyncIOMotorCollection = db[collection_name]

    update_data = validated.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds') + 'Z'
    update_data["updatedAt"] = now

    if kind == "models":
        await _validate_asset_model_references(update_data, db)

    result = await collection.find_one_and_update(
        {"id": entity_id},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind.capitalize()} with ID '{entity_id}' not found")
    await log_itam_action(
        current_user,
        action=f"{catalog_resource_type(kind)}.update",
        resource_type=catalog_resource_type(kind),
        resource_id=entity_id,
        details=f"Updated fields: {', '.join(sorted(update_data.keys()))}",
    )
    return result

@router.delete("/{kind}/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog_entity(
    kind: str,
    entity_id: str,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """
    Deletes an ITAM catalog entity.
    Deletion is refused if any assets reference this entity.
    """
    collection_name = _resolve_kind(kind)
    db = get_database()

    # Keyed by the URL 'kind' segment (CATALOG_REFERENCE_FIELDS' own keyspace), not by
    # collection_name — for manufacturers the two strings happen to be identical, which
    # masked this lookup being wrong for every other kind (categories/locations/suppliers/
    # models, whose collection name differs from the URL segment).
    reference_field = CATALOG_REFERENCE_FIELDS.get(kind)
    if reference_field:
        assets_collection: AsyncIOMotorCollection = db.assets
        asset_count = await assets_collection.count_documents({reference_field: entity_id})
        if asset_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete {kind} with ID '{entity_id}'. {asset_count} asset(s) currently reference it."
            )

    collection: AsyncIOMotorCollection = db[collection_name]
    result = await collection.delete_one({"id": entity_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind.capitalize()} with ID '{entity_id}' not found")

    await log_itam_action(
        current_user,
        action=f"{catalog_resource_type(kind)}.delete",
        resource_type=catalog_resource_type(kind),
        resource_id=entity_id,
        details=f"Deleted {kind} entity {entity_id}",
    )
