"""Approval of self-service sign-ups (Super Admin only).

Public sign-up (/api/auth/signup) creates the tenant and its first admin as pending, with no
session. A Super Admin lists them here and approves (the tenant and its pending users become
active; the tenant still starts with Overview only, tenant_features.START_FEATURES) or rejects
(the pending tenant and its users are removed). Reads the raw collections with explicit tenant
ids, like tenant creation, because the caller works in the platform tenant.

Nothing proves a signer owns the admin address (no mail is sent), so the queue says so, and a
sign-up left undecided for SIGNUP_PENDING_DAYS expires: it leaves the queue and cannot be
approved, and a new sign-up with its email or company name replaces it (77 WR-13).
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from authentication_endpoints import PENDING_TENANT_STATUS, PENDING_USER_STATUS
from authentication_service import get_current_user
from catalogue_mounts_billing_identity import TENANT_MANAGEMENT_GUARD
import plan_trial
from database import mongodb
from rbac_utils import is_super_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tenants/signups", tags=["Tenant Management"])

# 77 WR-13: an undecided sign-up stops claiming its email and company name after this long.
SIGNUP_PENDING_DAYS = 7


def signup_expired(record: dict, now=None) -> bool:
    """True once a pending sign-up (its tenant, or its admin) waited longer than SIGNUP_PENDING_DAYS.

    Reads ``signupRequestedAt``, else ``createdAt``. A sign-up whose age cannot be read never
    expires, so it is never displaced.
    """
    raw = (record or {}).get("signupRequestedAt") or (record or {}).get("createdAt")
    if not raw:
        return False
    try:
        when = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - when > timedelta(days=SIGNUP_PENDING_DAYS)


async def remove_pending_signup(db, tenant_id: str) -> None:
    """Delete a pending sign-up: every account of its tenant, their consent records, then the tenant.

    Callers first confirm the tenant is a pending sign-up. The tenant goes last and only while
    it is still pending, so a failure part-way leaves it findable and a retry finishes the job;
    an account an interrupted approval already activated goes with it, since its tenant no
    longer exists (77 WR-12).
    """
    await db.users.delete_many({"tenantId": tenant_id})
    await db.user_consents.delete_many({"tenantId": tenant_id})
    await db.tenants.delete_one({"id": tenant_id, "status": PENDING_TENANT_STATUS})


async def expired_signup_tenant(db, tenant_id, user: dict = None):
    """``tenant_id`` when it names an expired pending sign-up (and ``user``, if given, is its pending
    admin), else None. Anything approved, active or still within SIGNUP_PENDING_DAYS is never touched."""
    if not tenant_id:
        return None
    if user is not None and str(user.get("status", "")).strip().lower() != PENDING_USER_STATUS.lower():
        return None
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant or tenant.get("status") != PENDING_TENANT_STATUS or not signup_expired(tenant):
        return None
    return tenant_id


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
    """Sign-ups waiting for a decision, oldest first, each with the admin who asked.

    Expired sign-ups are left out (newest are read first, so they never crowd out a live one), and
    ``adminEmailVerified`` is always False: sign-up sends no confirmation mail (77 WR-13).
    """
    _require_super_admin(current_user)
    tenants = await mongodb.db.tenants.find(
        {"status": PENDING_TENANT_STATUS}, {"_id": 0, "id": 1, "name": 1, "signupRequestedAt": 1, "createdAt": 1},
    ).sort("signupRequestedAt", -1).to_list(length=200)
    out = []
    live = [t for t in tenants if not signup_expired(t)]
    for tenant in sorted(live, key=lambda t: t.get("signupRequestedAt") or t.get("createdAt") or ""):
        admin = await mongodb.db.users.find_one(
            {"tenantId": tenant["id"], "status": PENDING_USER_STATUS}, {"_id": 0, "email": 1, "name": 1})
        out.append({"id": tenant["id"], "name": tenant.get("name"),
                    "requestedAt": tenant.get("signupRequestedAt") or tenant.get("createdAt"),
                    "adminEmail": (admin or {}).get("email"), "adminName": (admin or {}).get("name"),
                    "adminEmailVerified": False})
    return {"signups": out}


@router.post("/{tenant_id}/approve", dependencies=[Depends(TENANT_MANAGEMENT_GUARD)])
async def approve_signup(tenant_id: str, current_user=Depends(get_current_user)):
    """Let the tenant's admin sign in. The tenant keeps its Overview-only start set.

    77 WR-12: the users are activated first and the tenant last, so a failure in between leaves the
    sign-up pending and listed, and approving again finishes it. Sign-in refuses an active user
    whose tenant is still pending, so the user write alone opens no session.
    """
    _require_super_admin(current_user)
    tenant = await _pending_tenant(tenant_id)
    if signup_expired(tenant):
        raise HTTPException(status_code=410, detail=(
            f"This sign-up expired after {SIGNUP_PENDING_DAYS} days without a decision. "
            "The requester can sign up again."))
    now = datetime.now(timezone.utc).isoformat()
    users = await mongodb.db.users.update_many(
        {"tenantId": tenant_id, "status": PENDING_USER_STATUS}, {"$set": {"status": "Active"}})
    approved = await mongodb.db.tenants.update_one(
        {"id": tenant_id, "status": PENDING_TENANT_STATUS},
        {"$set": {"status": "active", "approvedAt": now, "approvedBy": current_user.username}})
    if getattr(approved, "matched_count", 1) == 0:
        raise HTTPException(status_code=409, detail="This sign-up was removed while it was being approved.")
    try:  # D-23: the Free trial starts now; the hourly job and the Super Admin can still fix seats or extend
        await plan_trial.start_for_signup(mongodb.db, tenant_id)
    except Exception as exc:
        logger.warning("Trial of approved sign-up %s was not started: %s", tenant_id, exc)
    await _audit(current_user, "tenant.signup_approved", tenant, f"Approved sign-up of '{tenant.get('name')}'")
    return {"approved": tenant_id, "usersActivated": getattr(users, "modified_count", 0)}


@router.post("/{tenant_id}/reject", dependencies=[Depends(TENANT_MANAGEMENT_GUARD)])
async def reject_signup(tenant_id: str, current_user=Depends(get_current_user)):
    """Remove a pending sign-up: the tenant and its accounts. Nothing else exists for it yet.

    The tenant is removed last, so a failure part-way leaves it pending and rejecting again finishes
    it; an account an interrupted approval already activated goes too (77 WR-12). Expired sign-ups
    can still be rejected.
    """
    _require_super_admin(current_user)
    tenant = await _pending_tenant(tenant_id)
    await remove_pending_signup(mongodb.db, tenant_id)
    await _audit(current_user, "tenant.signup_rejected", tenant, f"Rejected sign-up of '{tenant.get('name')}'")
    return {"rejected": tenant_id}
