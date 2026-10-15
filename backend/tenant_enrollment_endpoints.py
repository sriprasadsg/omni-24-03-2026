"""Enrollment controls API (spec C4): hardware allowlist and limited-use install keys.

The Platform Owner and Platform Billing (manage:tenant_license, spec C1) manage every
tenant, like the license PATCH; platform staff read every tenant; tenant users read their
own tenant only.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import agent_allowlist
import enrollment_keys
from authentication_service import get_current_user
from database import mongodb
from rbac_utils import has_platform_permission
from tenant_endpoints import _assert_tenant_read
from catalogue_mounts_billing_identity import TENANT_OWN_SCOPE, TENANT_PLATFORM_STAFF

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tenants", tags=["Tenant Management"])

MAX_CSV_CHARS = 2_000_000  # ~10,000 rows of serial,uuid,mac,note


def _actor(user) -> str:
    return getattr(user, "username", None) or getattr(user, "email", None) or "unknown"


async def _require_license_manager(user) -> None:
    if not await has_platform_permission(user, "manage:tenant_license"):
        raise HTTPException(status_code=403, detail="Only Platform Owner or Billing can change enrollment controls")


async def _tenant_or_404(tenant_id: str) -> Dict[str, Any]:
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id}, {"_id": 0, "id": 1, "name": 1})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


async def _audit(action: str, tenant_id: str, user, details: str, resource_id: str = "") -> None:
    try:
        from audit_service import get_audit_service
        await get_audit_service().log_action_async(
            user_name=_actor(user), action=action, resource_type="agent_enrollment",
            resource_id=resource_id or tenant_id, details=details, tenant_id=tenant_id)
    except Exception as e:  # auditing never blocks the change
        logger.warning("Enrollment audit write failed (%s): %s", action, e)


# ── Allowlist ─────────────────────────────────────────────────────────────────

class AllowlistEntry(BaseModel):
    serialNumber: Optional[str] = Field(None, max_length=128)
    smbiosUuid: Optional[str] = Field(None, max_length=64)
    macAddress: Optional[str] = Field(None, max_length=32)
    note: Optional[str] = Field(None, max_length=agent_allowlist.MAX_NOTE)


class AllowlistImport(BaseModel):
    csv: str = Field(..., max_length=MAX_CSV_CHARS)


@router.get("/{tenant_id}/allowlist", dependencies=[Depends(TENANT_OWN_SCOPE)])
async def get_allowlist(tenant_id: str, skip: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000),
                        current_user=Depends(get_current_user)):
    _assert_tenant_read(current_user, tenant_id)
    await _tenant_or_404(tenant_id)
    return await agent_allowlist.list_entries(mongodb.db, tenant_id, skip, limit)


@router.post("/{tenant_id}/allowlist", status_code=201, dependencies=[Depends(TENANT_PLATFORM_STAFF)])
async def add_allowlist_entry(tenant_id: str, body: AllowlistEntry, current_user=Depends(get_current_user)):
    await _require_license_manager(current_user)
    await _tenant_or_404(tenant_id)
    try:
        entry = agent_allowlist.entry_from_body(body.model_dump())
        doc = await agent_allowlist.add(mongodb.db, tenant_id, entry, _actor(current_user))
    except agent_allowlist.EntryError as e:
        raise HTTPException(status_code=422 if "already" not in str(e) else 409, detail=str(e))
    await _audit("allowlist.added", tenant_id, current_user, agent_allowlist.describe(doc), doc["id"])
    return doc


@router.delete("/{tenant_id}/allowlist/{entry_id}", dependencies=[Depends(TENANT_PLATFORM_STAFF)])
async def delete_allowlist_entry(tenant_id: str, entry_id: str, current_user=Depends(get_current_user)):
    await _require_license_manager(current_user)
    if not await agent_allowlist.remove(mongodb.db, tenant_id, entry_id):
        raise HTTPException(status_code=404, detail="Allowlist entry not found")
    await _audit("allowlist.removed", tenant_id, current_user, f"entry {entry_id}", entry_id)
    return {"success": True}


@router.post("/{tenant_id}/allowlist/import", dependencies=[Depends(TENANT_PLATFORM_STAFF)])
async def import_allowlist(tenant_id: str, body: AllowlistImport, current_user=Depends(get_current_user)):
    """CSV ``serial,uuid,mac,note`` (header optional, at most 10,000 rows). Bad, repeated
    or already-listed rows are reported with their line number and skipped."""
    await _require_license_manager(current_user)
    await _tenant_or_404(tenant_id)
    try:
        result = await agent_allowlist.import_csv(mongodb.db, tenant_id, body.csv, _actor(current_user))
    except agent_allowlist.EntryError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _audit("allowlist.imported", tenant_id, current_user,
                 f"{result['imported']} imported, {result['skipped']} skipped")
    return result


# ── Install keys ──────────────────────────────────────────────────────────────

class KeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    maxUses: Optional[int] = Field(None, ge=1, le=1_000_000)
    expiresAt: Optional[datetime] = None
    defaultGroupId: Optional[str] = Field(None, max_length=64)


@router.get("/{tenant_id}/enrollment-keys", dependencies=[Depends(TENANT_OWN_SCOPE)])
async def get_enrollment_keys(tenant_id: str, current_user=Depends(get_current_user)):
    _assert_tenant_read(current_user, tenant_id)
    await _tenant_or_404(tenant_id)
    return {"keys": await enrollment_keys.list_keys(mongodb.db, tenant_id)}


@router.post("/{tenant_id}/enrollment-keys", status_code=201, dependencies=[Depends(TENANT_PLATFORM_STAFF)])
async def create_enrollment_key(tenant_id: str, body: KeyCreate, current_user=Depends(get_current_user)):
    """Returns the key once (``key``); only its hash is stored."""
    await _require_license_manager(current_user)
    await _tenant_or_404(tenant_id)
    expires_at = None
    if body.expiresAt:
        at = body.expiresAt if body.expiresAt.tzinfo else body.expiresAt.replace(tzinfo=timezone.utc)
        if at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="expiresAt must be in the future")
        expires_at = at.astimezone(timezone.utc).isoformat()
    if body.defaultGroupId and not await mongodb.db.agent_groups.find_one(
            {"id": body.defaultGroupId, "tenantId": tenant_id}, {"_id": 1}):
        raise HTTPException(status_code=422, detail="defaultGroupId: no such agent group in this tenant")
    created = await enrollment_keys.create(mongodb.db, tenant_id, body.name.strip(), _actor(current_user),
                                           body.maxUses, expires_at, body.defaultGroupId)
    await _audit("enrollment_key.created", tenant_id, current_user,
                 f"{created['name']} ({created['prefix']}…) maxUses={body.maxUses} expiresAt={expires_at} "
                 f"group={body.defaultGroupId}", created["id"])
    return created


@router.post("/{tenant_id}/enrollment-keys/{key_id}/revoke", dependencies=[Depends(TENANT_PLATFORM_STAFF)])
async def revoke_enrollment_key(tenant_id: str, key_id: str, current_user=Depends(get_current_user)):
    """The key stops enrolling new agents; agents it already enrolled keep working."""
    await _require_license_manager(current_user)
    row = await enrollment_keys.revoke(mongodb.db, tenant_id, key_id, _actor(current_user))
    if not row:
        raise HTTPException(status_code=404, detail="Install key not found")
    await _audit("enrollment_key.revoked", tenant_id, current_user, f"{row.get('name')} ({row.get('prefix')}…)", key_id)
    return enrollment_keys.public(row)
