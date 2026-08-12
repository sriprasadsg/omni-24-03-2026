import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database, TenantIsolatedDatabase
from itam_models import ManualAssetCreate, ASSET_SOURCE_MANUAL, DEFAULT_LIFECYCLE_STATUS, ASSET_TAG_PREFIX
from itam_catalog_service import collect_field_defs, validate_custom_field_values
from cache_service import invalidate_cache
from rbac_utils import verify_permission
from itam_audit_service import log_itam_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["ITAM Assets"])

# WR-04 (57-REVIEW): This router shares the /api/assets prefix with
# backend/asset_endpoints.py. This file defines only POST "" (create_manual_asset)
# — no GET /{asset_id} — so it has nothing that could be shadowed by, or shadow,
# asset_endpoints.py's own GET /{asset_id} regardless of registration order.
# router_registry.py in fact registers this router *before* asset_endpoints. The
# routes that ARE shadowing-sensitive live in itam_lifecycle_endpoints.py, whose
# module docstring covers that reasoning.
#
# Phase 59 will reuse `next_asset_tag` for PO numbers.
#
# The manual-creation path must never write the `status` key — that field belongs
# exclusively to the agent-liveness meaning the heartbeat owns.

async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    """
    Dependency to ensure the current user has 'manage:assets' permission.
    """
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission to manage ITAM assets."
        )
    return current_user

async def next_asset_tag(db: TenantIsolatedDatabase, tenant_id: str, prefix: str = ASSET_TAG_PREFIX) -> str:
    """
    Generates the next unique, sequential asset tag for a given tenant.
    This is an atomic operation using find_one_and_update.
    Phase 59 will reuse this helper for PO numbers.
    """
    # Use db.counters directly as it is a TenantIsolatedCollection
    counter_doc = await db.counters.find_one_and_update(
        {"tenantId": tenant_id, "name": "asset_tag"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    if not counter_doc:
        # This case should ideally not happen with upsert=True
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique asset tag."
        )
    return f"{prefix}-{counter_doc['seq']:04d}"


def build_asset_document(payload: ManualAssetCreate, tenant_id: str, asset_tag: str, now: str) -> Dict[str, Any]:
    """
    Assemble the persisted document shape for a manually-created ITAM asset.

    Extracted (Phase 65 Plan 03) from what used to be inline in
    create_manual_asset so there is exactly one definition of what an ITAM
    asset document looks like. Both create_manual_asset below and the CSV
    import path in itam_data_endpoints.py call this rather than each
    building their own — the two write paths cannot drift apart on
    document shape. Pure: no database I/O, no side effects.
    """
    document = payload.model_dump(exclude_none=True, exclude={
        "assetTag", "lifecycleStatus",  # excluded to add them explicitly below
    })
    asset_id = f"asset-{uuid.uuid4().hex[:8]}"
    document.update({
        "id": asset_id,
        "tenantId": tenant_id,
        "assetSource": ASSET_SOURCE_MANUAL,
        "assetTag": asset_tag,
        "lifecycleStatus": payload.lifecycleStatus.value,  # ensure it's the string value
        "createdAt": now,
        "updatedAt": now,
        "lastScanned": now,  # ensures manual assets appear in sorted lists
    })
    return document


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_manual_asset(
    payload: ManualAssetCreate,
    current_user: TokenData = Depends(_require_itam_admin),
):
    """
    Creates a new manual asset in the assets collection.
    The manual-creation path must never write the `status` key.
    Setting `lastScanned` to creation time ensures manual assets appear in asset lists.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant ID not found for the current user."
        )

    db = get_database()

    # Validate catalog references
    if payload.manufacturerId:
        # db.manufacturers is a TenantIsolatedCollection
        if not await db.manufacturers.find_one({"id": payload.manufacturerId}):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"manufacturerId '{payload.manufacturerId}' not found."
            )
    if payload.modelId:
        model_doc = await db.asset_models.find_one({"id": payload.modelId})
        if not model_doc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"modelId '{payload.modelId}' not found."
            )
        problems = validate_custom_field_values(collect_field_defs(model_doc), payload.customFields)
        if problems:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "customFields do not match the model's fieldset definitions.", "problems": problems}
            )
    # Extend with other catalog references (categoryId, etc.) in future tasks

    asset_tag = payload.assetTag
    if not asset_tag:
        asset_tag = await next_asset_tag(db, tenant_id)
    else:
        # Check for duplicate caller-supplied tag
        # db.assets is a TenantIsolatedCollection
        existing_asset = await db.assets.find_one({"assetTag": asset_tag})
        if existing_asset:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Asset with tag '{asset_tag}' already exists in this tenant."
            )

    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    document = build_asset_document(payload, tenant_id, asset_tag, now)
    asset_id = document["id"]

    try:
        # db.assets is a TenantIsolatedCollection
        await db.assets.insert_one(document)
        # cache_service.invalidate_cache is a synchronous def returning None — awaiting
        # it raises TypeError, which the broad except below converts into a false 500
        # for every real caller (Phase-57 discovered defect; fixed here).
        invalidate_cache("assets:*")
        document.pop("_id", None)
        await log_itam_action(
            current_user,
            action="itam_asset.create",
            resource_type="itam_asset",
            resource_id=asset_id,
            details=f"Created manual asset {asset_tag}",
        )
        return document
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Asset with tag '{asset_tag}' already exists in this tenant. (DuplicateKeyError)"
        )
    except Exception as e:
        logger.error(f"Failed to create manual asset: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create manual asset."
        )
