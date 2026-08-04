import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ReturnDocument

from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database, TenantIsolatedDatabase
from itam_models import (
    CatalogEntityCreate,
    CatalogEntityUpdate,
    LIFECYCLE_STATUSES
)
from rbac_utils import verify_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itam/catalog", tags=["ITAM Catalog"])

CATALOG_KINDS: Dict[str, str] = {
    "manufacturers": "manufacturers",
    # Add other catalog kinds here as they are implemented in future phases
}

CATALOG_REFERENCE_FIELDS: Dict[str, str] = {
    "manufacturers": "manufacturerId",
    # Add other reference fields here as they are implemented
}

async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    """
    Dependency to ensure the current user has 'manage:assets' permission.
    """
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to manage ITAM catalog entities"
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

@router.post("/{kind}", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_catalog_entity(
    kind: str,
    payload: CatalogEntityCreate,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """
    Creates a new ITAM catalog entity (e.g., manufacturer, model).
    """
    collection_name = _resolve_kind(kind)
    db = get_database()
    collection: AsyncIOMotorCollection = db[collection_name]

    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds') + 'Z'
    entity_id_prefix = kind[:-1] if kind.endswith('s') else kind # manufacturers -> manufacturer
    new_id = f"{entity_id_prefix}-{uuid.uuid4().hex[:8]}"

    document = payload.model_dump(exclude_none=True)
    document.update({
        "id": new_id,
        "tenantId": current_user.tenant_id,
        "createdAt": now,
        "updatedAt": now,
    })

    try:
        await collection.insert_one(document)
        document.pop("_id", None) # Remove MongoDB's internal _id
        return document
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
    payload: CatalogEntityUpdate,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """
    Updates an existing ITAM catalog entity.
    """
    collection_name = _resolve_kind(kind)
    db = get_database()
    collection: AsyncIOMotorCollection = db[collection_name]

    update_data = payload.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds') + 'Z'
    update_data["updatedAt"] = now

    result = await collection.find_one_and_update(
        {"id": entity_id},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind.capitalize()} with ID '{entity_id}' not found")
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

    reference_field = CATALOG_REFERENCE_FIELDS.get(collection_name)
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
