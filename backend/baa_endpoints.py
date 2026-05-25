"""Business Associate Agreement (BAA) management endpoints (HIPAA §164.308(b))."""
from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException, Depends
from auth_utils import get_current_user

router = APIRouter(prefix="/api/baa", tags=["BAA Management"])

_BAA_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


async def _db():
    from database import get_database
    return get_database()


def _tenant(user) -> str | None:
    return getattr(user, "tenant_id", None) or (user.get("tenant_id") if isinstance(user, dict) else None)


def _role(user) -> str | None:
    return getattr(user, "role", None) or (user.get("role") if isinstance(user, dict) else None)


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
async def list_baas(db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    query = {} if _role(current_user) in _BAA_SUPER_ROLES else {"tenantId": tenant_id}
    cursor = db["baa_agreements"].find(query, {"_id": 0}).sort("expiration_date", 1)
    items = await cursor.to_list(length=200)
    return [_normalize(i) for i in items]


# NOTE: static sub-routes MUST be declared before /{baa_id} in FastAPI
@router.get("/stats")
async def baa_stats(db=Depends(_db), current_user=Depends(get_current_user)):
    now_ts = time.time()
    thirty_days_ts = now_ts + 86400 * 30
    tenant_id = _tenant(current_user)
    base = {} if _role(current_user) in _BAA_SUPER_ROLES else {"tenantId": tenant_id}

    total         = await db["baa_agreements"].count_documents(base)
    active        = await db["baa_agreements"].count_documents({**base, "status": "active"})
    draft         = await db["baa_agreements"].count_documents({**base, "status": "draft"})
    terminated    = await db["baa_agreements"].count_documents({**base, "status": "terminated"})
    expired       = await db["baa_agreements"].count_documents({**base, "status": "expired"})
    expiring_soon = await db["baa_agreements"].count_documents({
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


@router.get("/{baa_id}")
async def get_baa(baa_id: str, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    baa_filter: dict = {"id": baa_id}
    if _role(current_user) not in _BAA_SUPER_ROLES:
        baa_filter["tenantId"] = tenant_id
    doc = await db["baa_agreements"].find_one(baa_filter, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="BAA not found")
    return _normalize(doc)


@router.post("")
async def create_baa(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    baa = {
        "id": f"baa-{int(time.time())}",
        "business_associate": payload.get("business_associate") or payload.get("vendor_name", ""),
        "contact_email": payload.get("contact_email") or payload.get("vendor_email", ""),
        "services": payload.get("services") or payload.get("services_covered", []),
        "phi_types": payload.get("phi_types", []),
        "effective_date": payload.get("effective_date") or time.time(),
        "expiration_date": payload.get("expiration_date") or payload.get("expiry_date"),
        "status": "draft",
        "version": 1,
        "created_by": current_user.get("sub"),
        "created_at": time.time(),
        "signed_by_vendor": False,
        "signed_by_us": False,
        "breach_notification_days": payload.get("breach_notification_days", 60),
        "audit_rights": payload.get("audit_rights", True),
    }
    if tenant_id:
        baa["tenantId"] = tenant_id
    await db["baa_agreements"].insert_one(baa)
    baa.pop("_id", None)
    return baa


@router.patch("/{baa_id}")
async def update_baa(baa_id: str, payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    payload.pop("id", None)
    payload.pop("_id", None)
    payload["updated_by"] = current_user.get("sub")
    payload["updated_at"] = time.time()
    tenant_id = _tenant(current_user)
    baa_filter: dict = {"id": baa_id}
    if _role(current_user) not in _BAA_SUPER_ROLES:
        baa_filter["tenantId"] = tenant_id
    result = await db["baa_agreements"].update_one(baa_filter, {"$set": payload})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="BAA not found")
    return {"ok": True}


@router.post("/{baa_id}/sign")
async def sign_baa(baa_id: str, payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    baa_filter: dict = {"id": baa_id}
    if _role(current_user) not in _BAA_SUPER_ROLES:
        baa_filter["tenantId"] = tenant_id

    party = payload.get("party", "us")
    update_field = "signed_by_vendor" if party == "vendor" else "signed_by_us"
    await db["baa_agreements"].update_one(
        baa_filter,
        {"$set": {update_field: True, f"{update_field}_at": time.time(),
                  f"{update_field}_by": current_user.get("sub")}}
    )
    doc = await db["baa_agreements"].find_one(baa_filter)
    if doc and doc.get("signed_by_us") and doc.get("signed_by_vendor"):
        await db["baa_agreements"].update_one(baa_filter, {"$set": {"status": "active"}})
    await db["baa_agreements"].update_one(baa_filter, {"$set": {"status": "active"}})
    return {"ok": True}


@router.post("/{baa_id}/terminate")
async def terminate_baa(baa_id: str, payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    baa_filter: dict = {"id": baa_id}
    if _role(current_user) not in _BAA_SUPER_ROLES:
        baa_filter["tenantId"] = tenant_id
    await db["baa_agreements"].update_one(
        baa_filter,
        {"$set": {"status": "terminated", "termination_reason": payload.get("reason"),
                  "terminated_by": current_user.get("sub"), "terminated_at": time.time()}}
    )
    return {"ok": True}
