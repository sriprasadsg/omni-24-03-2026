"""Approval of self-service sign-ups (Super Admin only).

Public sign-up (/api/auth/signup) creates the tenant and its first admin as pending, with no
session. A Super Admin lists them here and approves (the tenant and its pending users become
active; the tenant still starts with Overview only, tenant_features.START_FEATURES) or rejects
(the pending tenant and its users are removed). Reads the raw collections with explicit tenant
ids, like tenant creation, because the caller works in the platform tenant.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from authentication_endpoints import PENDING_TENANT_STATUS, PENDING_USER_STATUS
from authentication_service import get_current_user
from catalogue_mounts_billing_identity import TENANT_MANAGEMENT_GUARD
from database import mongodb
from rbac_utils import is_super_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tenants/signups", tags=["Tenant Management"])


def _require_super_admin(user) -> None:
    if not is_super_admin(getattr(user, "role", "")):
        raise HTTPException(status_code=403, detail="Only Super Admin can review sign-ups")


async def _pending_tenant(tenant_id: str) -> dict:
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id, "status": PENDING_TENANT_STATUS}, {"_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="No pending sign-up for this tenant")
    return tenant


async def _audit(user, action: str, tenant: dict, details: str) -> None:
    try:
        from audit_service import get_audit_service
        await get_audit_service().log_action_async(
            user.username, action, "tenant", tenant["id"], details, tenant_id=tenant["id"])
    except Exception as exc:  # the decision is made; a ledger hiccup must not undo it
        logger.warning("Sign-up audit entry failed for %s: %s", tenant.get("id"), exc)


@router.get("/pending", dependencies=[Depends(TENANT_MANAGEMENT_GUARD)])
async def list_pending_signups(current_user=Depends(get_current_user)):
    """Sign-ups waiting for a decision, oldest first, each with the admin who asked."""
    _require_super_admin(current_user)
    tenants = await mongodb.db.tenants.find(
        {"status": PENDING_TENANT_STATUS}, {"_id": 0, "id": 1, "name": 1, "signupRequestedAt": 1, "createdAt": 1},
    ).to_list(length=200)
    out = []
    for tenant in sorted(tenants, key=lambda t: t.get("signupRequestedAt") or t.get("createdAt") or ""):
        admin = await mongodb.db.users.find_one(
            {"tenantId": tenant["id"], "status": PENDING_USER_STATUS}, {"_id": 0, "email": 1, "name": 1})
        out.append({"id": tenant["id"], "name": tenant.get("name"),
                    "requestedAt": tenant.get("signupRequestedAt") or tenant.get("createdAt"),
                    "adminEmail": (admin or {}).get("email"), "adminName": (admin or {}).get("name")})
    return {"signups": out}


@router.post("/{tenant_id}/approve", dependencies=[Depends(TENANT_MANAGEMENT_GUARD)])
async def approve_signup(tenant_id: str, current_user=Depends(get_current_user)):
    """Let the tenant's admin sign in. The tenant keeps its Overview-only start set."""
    _require_super_admin(current_user)
    tenant = await _pending_tenant(tenant_id)
    now = datetime.now(timezone.utc).isoformat()
    await mongodb.db.tenants.update_one(
        {"id": tenant_id}, {"$set": {"status": "active", "approvedAt": now, "approvedBy": current_user.username}})
    users = await mongodb.db.users.update_many(
        {"tenantId": tenant_id, "status": PENDING_USER_STATUS}, {"$set": {"status": "Active"}})
    await _audit(current_user, "tenant.signup_approved", tenant, f"Approved sign-up of '{tenant.get('name')}'")
    return {"approved": tenant_id, "usersActivated": getattr(users, "modified_count", 0)}


@router.post("/{tenant_id}/reject", dependencies=[Depends(TENANT_MANAGEMENT_GUARD)])
async def reject_signup(tenant_id: str, current_user=Depends(get_current_user)):
    """Remove a pending sign-up: the tenant and the users it created. Nothing else exists for it yet."""
    _require_super_admin(current_user)
    tenant = await _pending_tenant(tenant_id)
    await mongodb.db.users.delete_many({"tenantId": tenant_id, "status": PENDING_USER_STATUS})
    await mongodb.db.user_consents.delete_many({"tenantId": tenant_id})
    await mongodb.db.tenants.delete_one({"id": tenant_id, "status": PENDING_TENANT_STATUS})
    await _audit(current_user, "tenant.signup_rejected", tenant, f"Rejected sign-up of '{tenant.get('name')}'")
    return {"rejected": tenant_id}
