"""PATCH /api/assets/{asset_id}/compliance/status — tenant-scoped compliance status override.

Delivers STATUS-01 (status change persists to asset_compliance collection) and
STATUS-02 (immutable status_history entry with changedBy, changedAt, previous_status, notes).

Extracted to a separate file because compliance_evidence_endpoints.py is already at
447 lines; adding this endpoint inline would breach the 500-line CLAUDE.md limit.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from cache_service import invalidate_cache

router = APIRouter()

_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

# Roles permitted to override compliance status (mirrors _WRITE_ROLES in
# compliance_bulk_evidence_endpoints.py). Read-only tenant members (e.g.
# "viewer", "analyst") must not be able to mutate compliance status.
_WRITE_ROLES: frozenset[str] = frozenset({
    "admin", "Admin", "Super Admin", "superadmin", "super_admin", "platform-admin"
})


class ComplianceStatusUpdate(BaseModel):
    control_id: str
    status: Literal["Compliant", "Non-Compliant", "Pending_Evidence"]
    notes: str = Field("", max_length=2000)


@router.patch("/api/assets/{asset_id}/compliance/status")
async def patch_asset_compliance_status(
    asset_id: str,
    body: ComplianceStatusUpdate,
    current_user=Depends(get_current_user),
):
    """Override the compliance status for a specific asset/control pair.

    Non-super-admin callers must own the asset (tenant isolation guard).
    Every successful PATCH appends an immutable status_history entry and
    sets manual_override=True on the asset_compliance document.
    """
    user_role = getattr(current_user, "role", "")
    actor = getattr(current_user, "username", "unknown")
    tenant_id = getattr(current_user, "tenant_id", None) or ""

    if user_role not in _WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient permissions to override compliance status")

    db = get_database()

    # Always resolve the asset from the database to get its authoritative tenantId.
    # This prevents a super-admin with no tenant_id (or the wrong one) from
    # polluting the "" bucket or writing into another tenant's namespace.
    asset = await db.assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    resolved_tenant_id = asset.get("tenantId", "")

    # Enforce tenant isolation: non-super-admin callers must own the asset
    if user_role not in _SUPER_ROLES and resolved_tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Asset not found in your tenant")

    now = datetime.now(timezone.utc)

    # find_one_and_update returns the document as it existed *before* the
    # update (return_document=BEFORE is the pymongo/motor default), making
    # the previous_status capture atomic with the status write itself and
    # eliminating the TOCTOU window that existed between a separate
    # find_one() read and update_one() write (WR-03).
    prior_doc = await db.asset_compliance.find_one_and_update(
        {"assetId": asset_id, "controlId": body.control_id, "tenantId": resolved_tenant_id},
        {
            "$set": {
                "status": body.status,
                "lastUpdated": now.isoformat(),
                "manual_override": True,
                "overriddenBy": actor,
                "overriddenAt": now.isoformat(),
            },
        },
        upsert=True,
    )
    previous_status = prior_doc.get("status", "Unknown") if prior_doc else "Unknown"

    # Append the immutable history entry with the atomically-captured
    # previous_status. This second write does not depend on document state,
    # so it does not reintroduce a race: previous_status was already fixed
    # correctly by the atomic operation above regardless of concurrent calls.
    await db.asset_compliance.update_one(
        {"assetId": asset_id, "controlId": body.control_id, "tenantId": resolved_tenant_id},
        {
            "$push": {
                "status_history": {
                    "status": body.status,
                    "changedBy": actor,
                    "changedAt": now.isoformat(),
                    "previous_status": previous_status,
                    "notes": body.notes,
                }
            },
        },
    )

    invalidate_cache(f"compliance:score:{resolved_tenant_id}")
    invalidate_cache("compliance:score:__super__")
    invalidate_cache(f"compliance:threat-score:{resolved_tenant_id}")
    invalidate_cache("compliance:threat-score:__super__")
    return {"ok": True, "status": body.status, "previous_status": previous_status}
