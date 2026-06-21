"""PATCH /api/assets/{asset_id}/compliance/status — tenant-scoped compliance status override.

Delivers STATUS-01 (status change persists to asset_compliance collection) and
STATUS-02 (immutable status_history entry with changedBy, changedAt, previous_status, notes).

Extracted to a separate file because compliance_evidence_endpoints.py is already at
447 lines; adding this endpoint inline would breach the 500-line CLAUDE.md limit.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Literal
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user

router = APIRouter()

_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


class ComplianceStatusUpdate(BaseModel):
    control_id: str
    status: Literal["Compliant", "Non-Compliant", "Pending_Evidence"]
    notes: str = ""


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

    # Fetch current compliance doc to capture previous_status for STATUS-02
    doc = await db.asset_compliance.find_one(
        {"assetId": asset_id, "controlId": body.control_id, "tenantId": resolved_tenant_id}
    )
    previous_status = doc.get("status", "Unknown") if doc else "Unknown"

    now = datetime.now(timezone.utc)

    await db.asset_compliance.update_one(
        {"assetId": asset_id, "controlId": body.control_id, "tenantId": resolved_tenant_id},
        {
            "$set": {
                "status": body.status,
                "lastUpdated": now.isoformat(),
                "manual_override": True,
                "overriddenBy": actor,
                "overriddenAt": now.isoformat(),
            },
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
        upsert=True,
    )

    return {"ok": True, "status": body.status, "previous_status": previous_status}
