"""Data Processing Agreement (DPA) management endpoints (GDPR Article 28)."""
from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException, Depends
from auth_utils import get_current_user

router = APIRouter(prefix="/api/dpa", tags=["DPA Management"])

_DPA_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
_DPA_ADMIN_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin"}


async def _db():
    from database import get_database
    return get_database()


def _tenant(user) -> str | None:
    return getattr(user, "tenant_id", None) or (user.get("tenant_id") if isinstance(user, dict) else None)


def _role(user) -> str | None:
    return getattr(user, "role", None) or (user.get("role") if isinstance(user, dict) else None)


def _sub(user) -> str | None:
    """Return user identifier — works for both TokenData (username) and dict (sub/email)."""
    if isinstance(user, dict):
        return user.get("sub") or user.get("email") or user.get("username")
    return getattr(user, "username", None) or getattr(user, "email", None)


def _normalize(doc: dict) -> dict:
    """Normalize stored doc to the shape the frontend expects."""
    doc.pop("_id", None)
    if "vendor_name" in doc and "business_associate" not in doc:
        doc["business_associate"] = doc.pop("vendor_name")
    if "vendor_email" in doc and "contact_email" not in doc:
        doc["contact_email"] = doc.pop("vendor_email")
    if "services_covered" in doc and "services" not in doc:
        doc["services"] = doc.pop("services_covered")
    if "expiry_date" in doc and "expiration_date" not in doc:
        doc["expiration_date"] = doc.pop("expiry_date")
    return doc


@router.get("")
async def list_dpas(db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    query = {} if _role(current_user) in _DPA_SUPER_ROLES else {"tenantId": tenant_id}
    cursor = db["dpa_agreements"].find(query, {"_id": 0}).sort("expiration_date", 1)
    items = await cursor.to_list(length=200)
    return [_normalize(i) for i in items]


# NOTE: static sub-routes MUST be declared before /{dpa_id} in FastAPI
@router.get("/stats")
async def dpa_stats(db=Depends(_db), current_user=Depends(get_current_user)):
    now_ts = time.time()
    thirty_days_ts = now_ts + 86400 * 30
    tenant_id = _tenant(current_user)
    base = {} if _role(current_user) in _DPA_SUPER_ROLES else {"tenantId": tenant_id}

    total         = await db["dpa_agreements"].count_documents(base)
    active        = await db["dpa_agreements"].count_documents({**base, "status": "active"})
    draft         = await db["dpa_agreements"].count_documents({**base, "status": "draft"})
    terminated    = await db["dpa_agreements"].count_documents({**base, "status": "terminated"})
    expired       = await db["dpa_agreements"].count_documents({**base, "status": "expired"})
    expiring_soon = await db["dpa_agreements"].count_documents({
        **base,
        "status": "active",
        "expiration_date": {"$lte": thirty_days_ts, "$gt": now_ts},
    })
    return {
        "total":         total,
        "active":        active,
        "expiring_soon": expiring_soon,
        "expired":       expired,
        "draft":         draft,
    }


@router.get("/{dpa_id}")
async def get_dpa(dpa_id: str, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    dpa_filter: dict = {"id": dpa_id}
    if _role(current_user) not in _DPA_SUPER_ROLES:
        dpa_filter["tenantId"] = tenant_id
    doc = await db["dpa_agreements"].find_one(dpa_filter, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="DPA not found")
    return _normalize(doc)


@router.post("")
async def create_dpa(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    if _role(current_user) not in _DPA_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    tenant_id = _tenant(current_user)
    dpa = {
        "id": f"dpa-{int(time.time())}",
        "business_associate": payload.get("business_associate") or payload.get("vendor_name", ""),
        "contact_email": payload.get("contact_email") or payload.get("vendor_email", ""),
        "services": payload.get("services") or payload.get("services_covered", []),
        "phi_types": payload.get("phi_types", []),
        "effective_date": payload.get("effective_date") or time.time(),
        "expiration_date": payload.get("expiration_date") or payload.get("expiry_date"),
        "status": "draft",
        "version": 1,
        "created_by": _sub(current_user),
        "created_at": time.time(),
        "signed_by_vendor": False,
        "signed_by_us": False,
        "breach_notification_days": payload.get("breach_notification_days", 60),
        "audit_rights": payload.get("audit_rights", True),
        "vendor_id": payload.get("vendor_id"), # REQUIRED DEVIATION 2: Add vendor_id field
    }
    if tenant_id:
        dpa["tenantId"] = tenant_id
    await db["dpa_agreements"].insert_one(dpa)
    dpa.pop("_id", None)
    return dpa


@router.patch("/{dpa_id}")
async def update_dpa(dpa_id: str, payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    payload.pop("id", None)
    payload.pop("_id", None)
    payload["updated_by"] = _sub(current_user)
    payload["updated_at"] = time.time()
    tenant_id = _tenant(current_user)
    dpa_filter: dict = {"id": dpa_id}
    if _role(current_user) not in _DPA_SUPER_ROLES:
        dpa_filter["tenantId"] = tenant_id
    result = await db["dpa_agreements"].update_one(dpa_filter, {"$set": payload})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="DPA not found")
    return {"ok": True}


@router.post("/{dpa_id}/sign")
async def sign_dpa(dpa_id: str, payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    if _role(current_user) not in _DPA_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required") # REQUIRED DEVIATION 1: Admin gate
    tenant_id = _tenant(current_user)
    dpa_filter: dict = {"id": dpa_id}
    if _role(current_user) not in _DPA_SUPER_ROLES:
        dpa_filter["tenantId"] = tenant_id

    party = payload.get("party", "us")
    update_field = "signed_by_vendor" if party == "vendor" else "signed_by_us"
    await db["dpa_agreements"].update_one(
        dpa_filter,
        {"$set": {update_field: True, f"{update_field}_at": time.time(),
                  f"{update_field}_by": _sub(current_user)}}
    )
    doc = await db["dpa_agreements"].find_one(dpa_filter)
    if doc and doc.get("signed_by_us") and doc.get("signed_by_vendor"):
        await db["dpa_agreements"].update_one(dpa_filter, {"$set": {"status": "active"}})
    return {"ok": True}


@router.post("/{dpa_id}/terminate")
async def terminate_dpa(dpa_id: str, payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    if _role(current_user) not in _DPA_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required") # REQUIRED DEVIATION 1: Admin gate
    tenant_id = _tenant(current_user)
    dpa_filter: dict = {"id": dpa_id}
    if _role(current_user) not in _DPA_SUPER_ROLES:
        dpa_filter["tenantId"] = tenant_id
    await db["dpa_agreements"].update_one(
        dpa_filter,
        {"$set": {"status": "terminated", "termination_reason": payload.get("reason"),
                  "terminated_by": _sub(current_user), "terminated_at": time.time()}}
    )
    return {"ok": True}