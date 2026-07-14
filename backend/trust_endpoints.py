from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
import trust_service
from trust_service import TrustProfile, AccessRequest
from database import get_database
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData

_TRUST_ADMIN_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin", "Tenant Admin"}

router = APIRouter(prefix="/api/trust-center", tags=["Trust Center"])


class RequestCreate(BaseModel):
    requester_email: str
    company: str
    reason: str


class RequestUpdate(BaseModel):
    status: str
    approved_by: Optional[str] = None


def _normalize_trust_domain(value: str) -> str:
    """Validate/normalize a trust_domain value: strip scheme/path, lowercase,
    cap length at 253 (max valid DNS hostname length)."""
    host = value.strip().lower()
    host = host.split("://", 1)[-1]
    host = host.split("/", 1)[0]
    host = host.split(":", 1)[0]
    if not host or len(host) > 253:
        raise HTTPException(status_code=400, detail="Invalid trust_domain value")
    return host


@router.get("/profile")
async def get_profile(current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    tenant_id = current_user.tenant_id
    profile = await trust_service.get_profile(db, tenant_id)
    trust_slug = await trust_service._ensure_trust_slug(db, tenant_id)
    tenant = await db.tenants.find_one({"id": tenant_id}, {"trust_domain": 1, "_id": 0})
    result = dict(profile)
    result["trust_slug"] = trust_slug
    result["trust_domain"] = (tenant or {}).get("trust_domain")
    return result


@router.put("/profile")
async def update_profile(updates: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    if getattr(current_user, "role", "") not in _TRUST_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    tenant_id = current_user.tenant_id

    updates = dict(updates)
    trust_domain = updates.pop("trust_domain", None)
    if trust_domain is not None:
        normalized = _normalize_trust_domain(trust_domain)
        await db.tenants.update_one({"id": tenant_id}, {"$set": {"trust_domain": normalized}})

    profile = await trust_service.update_profile(db, tenant_id, updates)
    trust_slug = await trust_service._ensure_trust_slug(db, tenant_id)
    tenant = await db.tenants.find_one({"id": tenant_id}, {"trust_domain": 1, "_id": 0})
    result = dict(profile)
    result["trust_slug"] = trust_slug
    result["trust_domain"] = (tenant or {}).get("trust_domain")
    return result


@router.get("/requests", response_model=List[AccessRequest])
async def get_requests(current_user: TokenData = Depends(get_current_user)):
    if getattr(current_user, "role", "") not in _TRUST_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    return await trust_service.get_requests(db, current_user.tenant_id)


@router.post("/requests", response_model=AccessRequest)
async def create_request(request: RequestCreate, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    return await trust_service.create_request(db, current_user.tenant_id, request.dict())


@router.put("/requests/{request_id}", response_model=AccessRequest)
async def update_request(request_id: str, update: RequestUpdate, current_user: TokenData = Depends(get_current_user)):
    if getattr(current_user, "role", "") not in _TRUST_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    result = await trust_service.update_request_status(
        db, current_user.tenant_id, request_id, update.status, update.approved_by
    )
    if not result:
        raise HTTPException(status_code=404, detail="Request not found")
    return result
