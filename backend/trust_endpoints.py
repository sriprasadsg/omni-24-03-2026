from fastapi import APIRouter, HTTPException, Depends, Request, Response
from typing import List, Dict, Any, Optional
import trust_service
from trust_service import TrustProfile, AccessRequest, _now_iso
from database import get_database
from pydantic import BaseModel, Field
from authentication_service import get_current_user
from auth_types import TokenData
from rate_limiter import limiter
from tenant_context import set_tenant_id

_TRUST_ADMIN_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin"}

router = APIRouter(prefix="/api/trust-center", tags=["Trust Center"])

# Genuinely public router — NO get_current_user on any route here. Mounted with
# no prefix so paths are exactly /api/public/trust/... (registered separately
# in router_registry.py as trust_endpoints.public_router).
public_router = APIRouter(tags=["Trust Center Public"])


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


# ─── Public, unauthenticated routes (TRUST-02/TRUST-03) ────────────────────────
# Clones agent_registry_endpoints.register_agent's shape: resolve tenant from a
# public identifier against the tenant-isolation-EXEMPT db.tenants collection,
# then explicitly set_tenant_id(...) BEFORE any tenant-scoped query. Never add
# trust_profiles/trust_access_requests to database.py's exemption allowlist.

async def _resolve_tenant_from_request(db, request: Request, slug: str) -> Dict[str, Any]:
    """Resolve a tenant for a public request: Host-header match against
    tenants.trust_domain first (TRUST-03 custom-domain support), falling back
    to a path-slug match against tenants.trust_slug. Raises an identical 404
    "Not found" for both no-match cases (no existence-leak via distinct
    messages)."""
    host = (request.headers.get("host") or "").split(":")[0]
    tenant = None
    if host:
        tenant = await db.tenants.find_one({"trust_domain": host}, {"id": 1, "_id": 0})
    if not tenant and slug:
        tenant = await db.tenants.find_one({"trust_slug": slug}, {"id": 1, "_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Not found")
    return tenant


def _public_view(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Server-side filtered view of a trust profile for unauthenticated
    visitors: private_documents are reduced to name-only stubs (no url)."""
    view = dict(profile)
    view["private_documents"] = [
        {"name": d.get("name")} for d in profile.get("private_documents", [])
    ]
    return view


@public_router.get("/api/public/trust/{slug}")
@limiter.limit("30/minute")
async def get_public_trust_profile(request: Request, response: Response, slug: str):
    """Genuinely public trust profile — no auth. Serves a private-URL-stripped
    view of the tenant's trust profile, resolved by slug or custom Host domain."""
    db = get_database()
    tenant = await _resolve_tenant_from_request(db, request, slug)
    set_tenant_id(tenant["id"])
    profile = await trust_service.get_profile(db, tenant["id"])
    return _public_view(profile)


class AccessRequestCreate(BaseModel):
    """Self-reported identity + explicit NDA consent from an external visitor.
    ip_address/user_agent/requested_at are NEVER accepted here — they are
    always server-derived in the route handler."""
    requester_email: str = Field(..., max_length=254)
    company: str = Field(..., max_length=200)
    reason: str = Field(..., max_length=2000)
    consent: bool = False


@public_router.post("/api/public/trust/{slug}/requests")
@limiter.limit("5/minute")
async def create_public_access_request(
    request: Request, response: Response, slug: str, payload: AccessRequestCreate
):
    """Public NDA-gated access-request submission — no auth. Requires explicit
    consent; ip_address/user_agent/requested_at are server-derived, never taken
    from the request body (un-forgeable)."""
    if not payload.consent:
        raise HTTPException(status_code=400, detail="Explicit NDA-acceptance consent is required")

    db = get_database()
    tenant = await _resolve_tenant_from_request(db, request, slug)
    set_tenant_id(tenant["id"])

    record_data = {
        "requester_email": payload.requester_email,
        "company": payload.company,
        "reason": payload.reason,
        "consented": True,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "")[:512],
        "requested_at": _now_iso(),
    }
    await trust_service.create_request(db, tenant["id"], record_data)
    return {"success": True}
