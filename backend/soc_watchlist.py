"""Tenant watchlists: indicators (IP, SHA-256, domain) an organization adds itself, with a retro-hunt.

Adding an indicator checks the tenant's alerts of the last 90 days (``retro_hunt``) and marks every alert
that names it (its hash or IP, or the domain in its text) with a ``threatIntel`` hit from source
"watchlist"; new alerts are checked as they arrive (soc_context.match_alert). Rows are tenant-scoped;
removing one stops future matches and leaves past marks as a record.
"""
import ipaddress
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

SHA256 = re.compile(r"^[0-9a-f]{64}$")
DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$")
RETRO_DAYS = 90
MAX_ITEMS = 1000


class WatchlistError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def kind_of(value: str) -> Optional[str]:
    v = value.strip().lower()
    try:
        ipaddress.ip_address(v)
        return "ip"
    except ValueError:
        pass
    return "sha256" if SHA256.match(v) else "domain" if DOMAIN.match(v) else None


def _hit(item: Dict[str, Any]) -> Dict[str, Any]:
    return {"value": item["value"], "kind": item["kind"], "source": "watchlist", "malware": item.get("note")}


def alert_matches(item: Dict[str, Any], alert: Dict[str, Any], ev: Dict[str, Any]) -> bool:
    if item["kind"] == "sha256":
        return ev.get("sha256") == item["value"]
    if item["kind"] == "ip":
        return ev.get("ip") == item["value"]
    text = f"{alert.get('title') or ''} {alert.get('description') or ''} {(alert.get('metadata') or {}).get('description') or ''}".lower()
    return item["value"] in text


async def hits_for(db, alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    import soc_response
    items = await db.soc_watchlist.find({"tenantId": alert.get("tenantId")}, {"_id": 0}).to_list(MAX_ITEMS)
    ev = soc_response.evidence(alert)
    return [_hit(i) for i in items if alert_matches(i, alert, ev)]


async def retro_hunt(db, tenant: str, item: Dict[str, Any], now: datetime) -> int:
    import soc_response
    since = (now - timedelta(days=RETRO_DAYS)).isoformat()
    matched = 0
    async for a in db.security_alerts.find({"tenantId": tenant, "created_at": {"$gte": since}, "status": {"$nin": ["merged", "archived"]}}, {"_id": 0}):
        if alert_matches(item, a, soc_response.evidence(a)):
            await db.security_alerts.update_one({"id": a["id"], "tenantId": tenant, "threatIntel.value": {"$ne": item["value"]}},
                                                {"$push": {"threatIntel": _hit(item)}})
            matched += 1
    return matched


async def add(db, scope: Optional[str], value: str, note: Optional[str], who: str) -> Dict[str, Any]:
    tenant, v = scope or "platform-admin", str(value or "").strip().lower()[:253]
    kind = kind_of(v)
    if not kind:
        raise WatchlistError("Give an IP address, a SHA-256 hash or a domain")
    if await db.soc_watchlist.count_documents({"tenantId": tenant}) >= MAX_ITEMS:
        raise WatchlistError(f"A watchlist holds at most {MAX_ITEMS} indicators", 409)
    if await db.soc_watchlist.find_one({"tenantId": tenant, "value": v}, {"_id": 1}):
        raise WatchlistError("That indicator is already on the watchlist", 409)
    now = datetime.now(timezone.utc)
    item = {"id": f"wl-{uuid.uuid4().hex[:12]}", "tenantId": tenant, "value": v, "kind": kind,
            "note": (note or "").strip()[:200] or None, "addedBy": who, "addedAt": now.isoformat()}
    await db.soc_watchlist.insert_one(dict(item))
    item["retroMatches"] = await retro_hunt(db, tenant, item, now)
    await db.soc_watchlist.update_one({"id": item["id"], "tenantId": tenant}, {"$set": {"retroMatches": item["retroMatches"]}})
    return item


async def list_items(db, scope: Optional[str]) -> List[Dict[str, Any]]:
    return await db.soc_watchlist.find({"tenantId": scope or "platform-admin"}, {"_id": 0}).sort("addedAt", -1).to_list(MAX_ITEMS)


async def remove(db, scope: Optional[str], item_id: str) -> None:
    if (await db.soc_watchlist.delete_one({"id": item_id, "tenantId": scope or "platform-admin"})).deleted_count == 0:
        raise WatchlistError("Indicator not found", 404)
