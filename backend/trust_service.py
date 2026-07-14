"""
Trust Center service — Mongo-backed profile + access-request CRUD.

Replaces the former in-memory TrustService singleton (self.profile/self.requests,
reset on every restart). All CRUD flows through the caller-supplied `db` handle
(the TenantIsolatedCollection-wrapped database from get_database()) so tenant
isolation is enforced the same way as every other GRC module in this codebase.
trust_profiles/trust_access_requests are deliberately NOT added to database.py's
global-exemption allowlist.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid


class TrustProfile(BaseModel):
    company_name: str
    description: str
    contact_email: str
    logo_url: str
    compliance_frameworks: List[str]  # e.g., ["SOC2", "ISO27001"]
    public_documents: List[Dict[str, str]]  # {"name": "Security Whitepaper", "url": "..."}
    private_documents: List[Dict[str, str]]  # {"name": "SOC2 Type II Report", "url": "..."}


class AccessRequest(BaseModel):
    id: str
    requester_email: str
    company: str
    reason: str
    status: str  # Pending, Approved, Denied
    requested_at: str
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _default_profile(tenant_id: str) -> Dict[str, Any]:
    """Empty-but-valid TrustProfile-shaped dict returned when no profile exists yet."""
    return {
        "company_name": "",
        "description": "",
        "contact_email": "",
        "logo_url": "",
        "compliance_frameworks": [],
        "public_documents": [],
        "private_documents": [],
    }


async def get_profile(db, tenant_id: str) -> Dict[str, Any]:
    """Return the stored profile for the tenant, or a default empty profile
    when none exists yet (no crash on first read)."""
    profile = await db.trust_profiles.find_one({}, {"_id": 0})
    return profile or _default_profile(tenant_id)


async def update_profile(db, tenant_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert the profile doc and return the merged result with a refreshed updated_at."""
    await db.trust_profiles.update_one(
        {},
        {"$set": {**updates, "updated_at": _now_iso()}},
        upsert=True,
    )
    return await get_profile(db, tenant_id)


async def get_requests(db, tenant_id: str) -> List[Dict[str, Any]]:
    """Return access requests for the tenant, newest-first."""
    cursor = db.trust_access_requests.find({}, {"_id": 0})
    return await cursor.sort("requested_at", -1).to_list(length=500)


async def create_request(db, tenant_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a Pending access request with server-side id/requested_at."""
    record = {
        "id": _gen_id("req"),
        "status": "Pending",
        "requested_at": _now_iso(),
        "approved_at": None,
        "approved_by": None,
        **request_data,
    }
    await db.trust_access_requests.insert_one(record)
    record.pop("_id", None)
    return record


async def update_request_status(
    db, tenant_id: str, request_id: str, status: str, approved_by: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Flip status to Approved/Denied, stamping approved_at/approved_by only on
    Approved. Returns None for an unknown id."""
    existing = await db.trust_access_requests.find_one({"id": request_id})
    if not existing:
        return None

    update: Dict[str, Any] = {"status": status}
    if status == "Approved":
        update["approved_at"] = _now_iso()
        update["approved_by"] = approved_by
    else:
        update["approved_at"] = None
        update["approved_by"] = None

    await db.trust_access_requests.update_one({"id": request_id}, {"$set": update})

    merged = dict(existing)
    merged.update(update)
    merged.pop("_id", None)
    return merged


async def _ensure_trust_slug(db, tenant_id: str) -> str:
    """Generate and persist a trust_slug onto db.tenants for the tenant, only
    when absent. Idempotent on repeat calls. tenants is tenant-isolation-exempt,
    safe to query directly by id."""
    tenant = await db.tenants.find_one({"id": tenant_id}, {"trust_slug": 1, "_id": 0})
    if tenant and tenant.get("trust_slug"):
        return tenant["trust_slug"]

    slug = _gen_id("trust")
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"trust_slug": slug}})
    return slug
