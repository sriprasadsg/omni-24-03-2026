"""Partner document readers and the D-01 customer row (Phase 87).

Everything here runs on the raw handle with an explicit filter: ``tenants`` is exempt from the tenant
wrapper, so the partner scoping is the filter written in this file, never the request context.
``CUSTOMER_FIELDS`` is the whole of what a partner may see about a customer (D-01): customer rows are
rebuilt key by key from it and a stored document is never returned.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi.responses import JSONResponse

import audit_ledger
import license_rules
import licensing
from partner_pool import PartnerError, _raw

logger = logging.getLogger(__name__)

PARTNER_TYPE = "partner"
PLATFORM_AUDIT_TENANT = "platform-admin"
# D-01: the only customer fields a partner ever receives, in this order.
CUSTOMER_FIELDS = ("id", "name", "seatsAssigned", "seatsUsed", "agentsOnline", "agentsTotal", "licenseExpiresAt")
_NOT_COUNTED_AGENTS = frozenset({"Pending", "Rejected"})


async def find_partner(db, partner_id: str) -> Optional[Dict[str, Any]]:
    """The partner organization with this id, or None (a customer or a missing id is never returned)."""
    if not partner_id:
        return None
    return await _raw(db).tenants.find_one({"id": partner_id, "type": PARTNER_TYPE}, {"_id": 0})


def pool_view(partner_doc: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    pool = partner_doc.get("partner") or {}
    size = int(pool.get("poolSize") or 0)
    handed_out = int(pool.get("allocated") or 0)
    expires_at = pool.get("expiresAt") if isinstance(pool.get("expiresAt"), str) else None
    return {
        "size": size,
        "handedOut": handed_out,
        "free": max(size - handed_out, 0),
        "expiresAt": expires_at,
        "expired": license_rules.expired({"expiresAt": expires_at}, now),
    }


def partner_summary(partner_doc: Dict[str, Any], customer_count: int, now: Optional[datetime] = None) -> Dict[str, Any]:
    pool = partner_doc.get("partner") or {}
    view = pool_view(partner_doc, now)
    ceiling = [s for s in pool.get("screenCeiling") or [] if isinstance(s, str)]
    return {
        "id": partner_doc.get("id"),
        "name": partner_doc.get("name"),
        "poolSize": view["size"],
        "allocated": view["handedOut"],
        "free": view["free"],
        "expiresAt": view["expiresAt"],
        "expired": view["expired"],
        "screenCeiling": ceiling,
        "unrestricted": "all" in ceiling,
        "status": pool.get("status") or "active",
        "customerCount": customer_count,
    }


def _parse(iso: Optional[str]) -> Optional[datetime]:
    if not isinstance(iso, str):
        return None
    try:
        at = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _earlier(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """The earlier of two ISO dates (the other when only one is a date), as the stored string."""
    pa, pb = _parse(a), _parse(b)
    if pa and pb:
        return a if pa <= pb else b
    return a if pa else (b if pb else None)


async def customer_rows(db, partner_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One D-01 row per customer of this partner, ordered by name then id."""
    raw = _raw(db)
    partner_id = partner_doc["id"]
    pool_expiry = (partner_doc.get("partner") or {}).get("expiresAt")
    customers = await raw.tenants.find(
        {"partnerId": partner_id},
        {"_id": 0, "id": 1, "name": 1, "license": 1, "maxAgents": 1},
    ).to_list(length=None)
    ids = [c["id"] for c in customers]
    online: Dict[str, int] = {}
    total: Dict[str, int] = {}
    if ids:
        pipeline = [
            {"$match": {"tenantId": {"$in": ids}}},
            {"$group": {"_id": {"t": "$tenantId", "s": "$status"}, "count": {"$sum": 1}}},
        ]
        async for doc in raw.agents.aggregate(pipeline):
            tid, status = doc["_id"].get("t"), doc["_id"].get("s")
            if status in _NOT_COUNTED_AGENTS:
                continue
            total[tid] = total.get(tid, 0) + doc["count"]
            if status == "Online":
                online[tid] = online.get(tid, 0) + doc["count"]
    rows: List[Dict[str, Any]] = []
    for customer in customers:
        lic = licensing.license_of(customer)
        values = {
            "id": customer["id"],
            "name": customer.get("name"),
            "seatsAssigned": lic["maxAgents"],
            "seatsUsed": lic["seatsUsed"] if lic["seatsUsed"] is not None else total.get(customer["id"], 0),
            "agentsOnline": online.get(customer["id"], 0),
            "agentsTotal": total.get(customer["id"], 0),
            "licenseExpiresAt": _earlier(lic["expiresAt"], pool_expiry),
        }
        rows.append({key: values[key] for key in CUSTOMER_FIELDS})
    rows.sort(key=lambda r: (str(r["name"] or "").casefold(), r["id"]))
    return rows


async def name_taken(db, name: str, exclude_id: Optional[str] = None) -> bool:
    """True when an organization already carries this name (trimmed, case-insensitive)."""
    query: Dict[str, Any] = {"name": {"$regex": f"^{re.escape(name.strip())}$", "$options": "i"}}
    if exclude_id:
        query["id"] = {"$ne": exclude_id}
    return await _raw(db).tenants.find_one(query, {"_id": 0, "id": 1}) is not None


def error_response(err: PartnerError) -> JSONResponse:
    """The contract body for a partner refusal; the UI shows ``error`` verbatim."""
    return JSONResponse(
        status_code=err.status,
        content={"error": err.message, "code": err.code, "status_code": err.status, **err.numbers},
    )


def _actor(actor: Any) -> Dict[str, Any]:
    if isinstance(actor, dict):
        return actor
    return {"email": getattr(actor, "username", None) or "system", "role": getattr(actor, "role", None)}


async def audit(action: str, *, actor: Any, partner_id: str, platform: bool = False, **fields: Any) -> None:
    """Record under the partner's own tenant id, and under the platform ledger when the Super Admin acted.
    The ledger spools on failure and never raises; a lookup problem here must not undo the action."""
    who = _actor(actor)
    try:
        await audit_ledger.event(action, partner_id, actor=who, outcome="success", partnerId=partner_id, **fields)
        if platform:
            await audit_ledger.event(action, PLATFORM_AUDIT_TENANT, actor=who, outcome="success",
                                     partnerId=partner_id, **fields)
    except Exception as exc:
        logger.warning("audit for %s on partner %s was not recorded: %s", action, partner_id, exc)
