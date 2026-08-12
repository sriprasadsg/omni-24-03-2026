"""LDAP/AD admin configuration and authentication endpoints (ITAM-USR-03).

Admin-only config/sync/mapping endpoints are gated by
itam_asset_endpoints._require_itam_admin (imported, not re-implemented —
matches the ITAM phases 56-63 / 64-01 convention). The LDAP login route is
a **dedicated** POST /api/auth/ldap/login endpoint, not a branch inside the
existing local-auth login handler in authentication_endpoints.py — that
file is rewritten by plan 64-06 in the same wave for two-phase MFA, so a
competing edit here would collide. The two-flow "try local, then LDAP"
chaining is deferred until after 64-06 lands (see 64-03 SUMMARY.md).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from auth_types import TokenData
from database import get_database
from itam_asset_endpoints import _require_itam_admin
from rbac_utils import is_super_admin
from rate_limiter import limiter
from tenant_context import get_tenant_id

from ldap_service import (
    LDAPAuthError,
    LDAPConfigError,
    LDAPConnectionError,
    LDAPConnectionManager,
    LDAPGroupMapper,
    LDAPSyncError,
    LDAPUserSyncer,
    authenticate_ldap,
    get_ldap_config,
)

import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(tags=["LDAP/AD Integration"])


def _config_scope(current_user: TokenData) -> Optional[str]:
    """Super Admins manage the platform-wide default config (tenant_id=None,
    the one /api/auth/ldap/login resolves to); everyone else who reaches
    _require_itam_admin manages their own tenant's config."""
    return None if is_super_admin(current_user.role) else get_tenant_id()


# ─── Pydantic models ───────────────────────────────────────────────────────────

class LDAPConfigIn(BaseModel):
    uri: str
    bind_dn: str
    bind_password: str
    user_base_dn: str
    group_base_dn: Optional[str] = ""
    user_filter: Optional[str] = "(objectClass=user)"
    group_filter: Optional[str] = "(objectClass=group)"
    user_id_attr: Optional[str] = "sAMAccountName"
    user_email_attr: Optional[str] = "mail"
    user_name_attr: Optional[str] = "displayName"
    group_member_attr: Optional[str] = "member"
    tls_ca_cert: Optional[str] = None


class GroupMappingIn(BaseModel):
    group_dn: str
    role: str
    priority: Optional[int] = 100


class LDAPLoginRequest(BaseModel):
    username: str
    password: str


# ─── Config management ─────────────────────────────────────────────────────────

@router.post("/api/admin/ldap/config")
async def save_ldap_config(config: LDAPConfigIn, current_user: TokenData = Depends(_require_itam_admin)):
    """Persist LDAP configuration. The bind password is encrypted at rest
    via encryption_service (T-64-08) — never stored in plaintext."""
    from encryption_service import get_encryption_service

    db = get_database()
    tenant_id = _config_scope(current_user)
    doc = config.model_dump()
    enc = get_encryption_service()
    doc["bind_password_encrypted"] = enc.encrypt(doc.pop("bind_password"))
    doc["tenant_id"] = tenant_id
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    doc["updated_by"] = getattr(current_user, "username", "unknown")

    await db.ldap_configs.update_one({"tenant_id": tenant_id}, {"$set": doc}, upsert=True)
    return {"success": True}


@router.get("/api/admin/ldap/config")
async def read_ldap_config(current_user: TokenData = Depends(_require_itam_admin)):
    """Return the saved LDAP config with the bind password masked."""
    db = get_database()
    tenant_id = _config_scope(current_user)
    doc = await db.ldap_configs.find_one({"tenant_id": tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="LDAP is not configured for this scope")
    doc["_id"] = str(doc["_id"])
    doc.pop("bind_password_encrypted", None)
    doc["bind_password"] = "***masked***"
    return doc


@router.post("/api/admin/ldap/test-connection")
async def test_ldap_connection(current_user: TokenData = Depends(_require_itam_admin)):
    """Test LDAP connectivity and service-account bind without touching
    any user data."""
    tenant_id = _config_scope(current_user)
    try:
        config = await get_ldap_config(tenant_id)
    except LDAPConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    conn_mgr = LDAPConnectionManager(config)

    def _test() -> bool:
        with conn_mgr.service_connection():
            return True

    try:
        await asyncio.to_thread(_test)
    except LDAPConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"success": True, "message": "LDAP connection and bind succeeded"}


# ─── Manual sync trigger ────────────────────────────────────────────────────────

@router.post("/api/admin/ldap/sync")
async def trigger_ldap_sync(current_user: TokenData = Depends(_require_itam_admin)):
    """Trigger a manual full user/group sync for the caller's tenant."""
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context available for sync")

    try:
        config = await get_ldap_config(tenant_id)
    except LDAPConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    syncer = LDAPUserSyncer(config)
    group_mapper = LDAPGroupMapper(config)
    try:
        result = await syncer.sync_all(tenant_id, group_mapper=group_mapper)
    except LDAPConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"success": True, **result}


# ─── Group -> role mapping ────────────────────────────────────────────────────────

@router.get("/api/admin/ldap/group-mapping")
async def list_group_mappings(current_user: TokenData = Depends(_require_itam_admin)):
    tenant_id = _config_scope(current_user)
    return await LDAPGroupMapper.list_mappings(tenant_id)


@router.post("/api/admin/ldap/group-mapping")
async def upsert_group_mapping(mapping: GroupMappingIn, current_user: TokenData = Depends(_require_itam_admin)):
    tenant_id = _config_scope(current_user)
    try:
        return await LDAPGroupMapper.upsert_mapping(
            mapping.group_dn, mapping.role, tenant_id=tenant_id, priority=mapping.priority or 100,
        )
    except LDAPConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/api/admin/ldap/group-mapping/{mapping_id}")
async def delete_group_mapping(mapping_id: str, current_user: TokenData = Depends(_require_itam_admin)):
    try:
        deleted = await LDAPGroupMapper.delete_mapping(mapping_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid mapping ID")
    if not deleted:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"success": True}


# ─── LDAP authentication (dedicated route, not a branch of local login) ───────────

@router.post("/api/auth/ldap/login")
@limiter.limit("10/minute")
async def ldap_login(request: Request, response: Response, body: LDAPLoginRequest):  # noqa: ARG001
    """Authenticate against LDAP/AD: bind -> sync local user record
    (source="ldap") -> mint the same JWT shape as the local-auth login
    endpoint. Kept as its own route (see module docstring) so it never
    collides with 64-06's rewrite of the local login handler.
    """
    try:
        result = await authenticate_ldap(body.username, body.password)
    except LDAPAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc), headers={"WWW-Authenticate": "Bearer"})
    except LDAPConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except (LDAPConfigError, LDAPSyncError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return result
