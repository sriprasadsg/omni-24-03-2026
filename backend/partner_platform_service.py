"""The Super Admin's side of the partner channel (Phase 87): appoint and list partners.

Raw handle and explicit filters throughout (``tenants`` is exempt from the tenant wrapper). A partner
is its own organization marked ``type: "partner"`` (D-13) with no seats of its own: ``license.maxAgents``
is stored as 0 so the licensing defaults never invent seats for it.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import licensing
import tenant_features
from partner_pool import PartnerError, _raw
from partner_store import PARTNER_TYPE, audit, name_taken, partner_summary

ALL_SCREENS = "all"
_NAME_UNAVAILABLE = "That name isn't available."


def validate_ceiling(values: Iterable[str]) -> List[str]:
    """The screen ceiling (D-10): switchable screens or features, or the single value ``all``."""
    cleaned = list(dict.fromkeys(values or []))
    for value in cleaned:
        if value != ALL_SCREENS and value not in tenant_features.SWITCHABLE:
            raise PartnerError(422, "invalid_screen", f"'{value}' is not a screen that can be sold.")
    if ALL_SCREENS in cleaned and len(cleaned) > 1:
        raise PartnerError(422, "invalid_screen", "'all' cannot be combined with individual screens.")
    return cleaned


def _utc_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


async def appoint(db, *, name: str, pool_size: int, expires_at: Optional[datetime],
                  screen_ceiling: Iterable[str], actor: Any) -> Dict[str, Any]:
    """Create the partner organization; returns its summary."""
    name = name.strip()
    ceiling = validate_ceiling(screen_ceiling)
    if await name_taken(db, name):
        raise PartnerError(409, "name_unavailable", _NAME_UNAVAILABLE)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"partner_{uuid.uuid4().hex[:12]}",
        "name": name,
        "type": PARTNER_TYPE,
        "partner": {
            "poolSize": pool_size,
            "allocated": 0,
            "expiresAt": _utc_iso(expires_at),
            "screenCeiling": ceiling,
            "status": "active",
        },
        "license": {"maxAgents": 0, "seatsUsed": 0, "inactiveReclaimDays": licensing.DEFAULT_RECLAIM_DAYS},
        "maxAgents": 0,
        "enabledFeatures": [],
        "emailConfig": {},
        "createdAt": now,
        "updatedAt": now,
    }
    await _raw(db).tenants.insert_one(dict(doc))
    await audit("partner.appointed", actor=actor, partner_id=doc["id"], platform=True,
                poolSize=pool_size, expiresAt=doc["partner"]["expiresAt"])
    return partner_summary(doc, 0)


async def list_partners(db) -> List[Dict[str, Any]]:
    """Every partner with its pool and customer count, ordered by name then id."""
    raw = _raw(db)
    partners = await raw.tenants.find({"type": PARTNER_TYPE}, {"_id": 0}).to_list(length=None)
    counts: Dict[str, int] = {}
    async for row in raw.tenants.aggregate([
        {"$match": {"partnerId": {"$type": "string"}}},
        {"$group": {"_id": "$partnerId", "count": {"$sum": 1}}},
    ]):
        counts[row["_id"]] = row["count"]
    out = [partner_summary(p, counts.get(p["id"], 0)) for p in partners]
    out.sort(key=lambda s: (str(s["name"] or "").casefold(), s["id"]))
    return out
