"""IP Ban Management Endpoints — /api/security/ip-bans"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from authentication_service import get_current_user
from tenant_context import get_tenant_id
from rbac_service import rbac_service
import ip_ban_service

router = APIRouter(prefix="/api/security/ip-bans", tags=["IP Bans"])

_ADMIN_ROLES = {"admin", "Admin", "Tenant Admin", "Super Admin", "super_admin", "platform-admin"}


class BanRequest(BaseModel):
    ip: str
    reason: str
    expires_hours: Optional[int] = None


@router.get("")
async def get_bans(
    active_only: bool = True,
    current_user=Depends(rbac_service.has_permission("view:security")),
):
    tenant_id = get_tenant_id()
    return await ip_ban_service.list_bans(tenant_id=tenant_id, active_only=active_only)


@router.post("")
async def create_ban(
    req: BanRequest,
    current_user=Depends(rbac_service.has_permission("manage:security_cases")),
):
    if not req.ip:
        raise HTTPException(status_code=400, detail="IP address is required")
    tenant_id = get_tenant_id()
    caller = getattr(current_user, "username", "admin")
    doc = await ip_ban_service.ban_ip(
        ip=req.ip,
        reason=req.reason,
        tenant_id=tenant_id,
        banned_by=caller,
        auto=False,
        expires_hours=req.expires_hours,
    )
    return {"success": True, "ban": doc}


@router.delete("/{ip}")
async def remove_ban(
    ip: str,
    current_user=Depends(rbac_service.has_permission("manage:security_cases")),
):
    tenant_id = get_tenant_id()
    updated = await ip_ban_service.unban_ip(ip=ip, tenant_id=tenant_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Ban not found")
    return {"success": True}


@router.post("/expire")
async def run_expiry(
    current_user=Depends(rbac_service.has_permission("manage:security_cases")),
):
    """Manually trigger expiry of time-limited bans."""
    count = await ip_ban_service.expire_bans()
    return {"success": True, "expired": count}
