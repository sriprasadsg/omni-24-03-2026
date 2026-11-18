"""Endpoint context, alert enrichment and risk scores for the SOC console.

* An endpoint's importance (low / medium / high / critical) and owner are set from the console and kept in
  ``soc_endpoint_context`` (one row per tenant and agent); an endpoint never set counts as medium.
* An alert's risk (0-100) = severity base x endpoint importance, plus a little for repeats, discounted
  with age, plus 20 when a threat-intel feed lists one of its hashes or IPs; a closed alert scores 0.
  It is computed when shown, so a changed importance applies at once.
* A host's or user's risk is its riskiest active alert plus a small share of the next four.
* ``match_alert`` checks a new alert's hashes and IPs against the threat-intel indicators and stores hits.
"""
import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from soc_service import parse_ts, scope_filter, view

IMPORTANCE = ("low", "medium", "high", "critical")
IMPORTANCE_FACTOR = {"low": 0.8, "medium": 1.0, "high": 1.2, "critical": 1.4}
SEVERITY_BASE = {"critical": 85, "high": 65, "medium": 40, "low": 20, "info": 8}
TI_BONUS = 20


class ContextError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def risk(alert: Dict[str, Any], importance: Optional[str], now: datetime) -> int:
    """0-100 for one viewed alert (soc_service.view)."""
    if alert.get("status") == "closed":
        return 0
    score = SEVERITY_BASE.get(alert.get("severity"), 20) * IMPORTANCE_FACTOR.get(importance or "medium", 1.0)
    if int(alert.get("occurrences") or 1) > 1:
        score += min(10.0, 3 * math.log2(int(alert["occurrences"])))
    seen = parse_ts(alert.get("lastSeenAt"))
    age_days = (now - seen).total_seconds() / 86400 if seen else 30
    score *= 1.0 if age_days <= 1 else 0.85 if age_days <= 7 else 0.7
    if alert.get("threatIntel"):
        score += TI_BONUS
    return int(min(100, round(score)))


def combined(scores: Iterable[int]) -> int:
    ordered = sorted((s for s in scores if s > 0), reverse=True)
    return int(min(100, round(ordered[0] + 0.15 * sum(ordered[1:5])))) if ordered else 0


def _raw(db):
    return getattr(db, "_db", db)


async def importance_map(db, pairs: Iterable[tuple]) -> Dict[tuple, Dict[str, Any]]:
    """(tenantId, agentId) -> {importance, owner} for the endpoints that have context set."""
    pairs = {(t, a) for t, a in pairs if a}
    if not pairs:
        return {}
    rows = await _raw(db).soc_endpoint_context.find(
        {"$or": [{"tenantId": t, "agentId": a} for t, a in pairs]}, {"_id": 0}).to_list(len(pairs))
    return {(r["tenantId"], r["agentId"]): r for r in rows}


async def annotate(db, alerts: List[Dict[str, Any]], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Set ``risk`` and ``importance`` on viewed alerts."""
    now = now or datetime.now(timezone.utc)
    ctx = await importance_map(db, ((a.get("tenantId"), a.get("agentId")) for a in alerts))
    for a in alerts:
        imp = (ctx.get((a.get("tenantId"), a.get("agentId"))) or {}).get("importance")
        a["importance"] = imp or "medium"
        a["risk"] = risk(a, imp, now)
    return alerts


async def set_context(db, scope: Optional[str], agent_id: str, importance: Optional[str], owner: Optional[str], who: str) -> Dict[str, Any]:
    if importance not in (None, *IMPORTANCE):
        raise ContextError(f"importance must be one of: {', '.join(IMPORTANCE)}")
    agent = await db.agents.find_one({"id": agent_id, **scope_filter(scope)}, {"_id": 0, "id": 1, "tenantId": 1})
    if not agent:
        raise ContextError("Endpoint not found", 404)
    row = {"tenantId": agent["tenantId"], "agentId": agent_id, "importance": importance or "medium",
           "owner": (owner or "").strip()[:120] or None, "updatedBy": who, "updatedAt": datetime.now(timezone.utc).isoformat()}
    await _raw(db).soc_endpoint_context.update_one({"tenantId": agent["tenantId"], "agentId": agent_id}, {"$set": row}, upsert=True)
    return row


async def match_alert(db, alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Threat-intel hits for a new alert's hashes and IPs (stored on the alert as ``threatIntel``)."""
    import soc_response
    import soc_threat_intel
    ev = soc_response.evidence(alert)
    import soc_watchlist
    hits = await soc_threat_intel.lookup(_raw(db), [ev.get("sha256"), ev.get("ip")]) + await soc_watchlist.hits_for(db, alert)
    if hits:
        alert["threatIntel"] = hits
        await db.security_alerts.update_one({"id": alert["id"], "tenantId": alert.get("tenantId")}, {"$set": {"threatIntel": hits}})
    return hits


async def alert_context(db, scope: Optional[str], alert_id: str) -> Dict[str, Any]:
    """Everything around one alert: its endpoint, user, other active alerts there, threat-intel hits."""
    doc = await db.security_alerts.find_one({"id": alert_id, **scope_filter(scope)}, {"_id": 0})
    if not doc:
        raise ContextError("Alert not found", 404)
    v = (await annotate(db, [view(doc)]))[0]
    tenant, agent_id = doc.get("tenantId"), v.get("agentId")
    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant}, {"_id": 0, "hostname": 1, "ipAddress": 1, "platform": 1,
                                                                          "meta.os": 1, "lastSeen": 1, "status": 1, "version": 1}) if agent_id else None
    ctx = (await importance_map(db, [(tenant, agent_id)])).get((tenant, agent_id)) or {}
    others = await db.security_alerts.count_documents({"tenantId": tenant, "agent_id": agent_id, "id": {"$ne": alert_id},
                                                       "status": {"$in": ["open", "new", "acknowledged"]}}) if agent_id else 0
    import soc_response
    import soc_threat_intel
    ev = soc_response.evidence(doc)
    import soc_watchlist
    hits = await soc_threat_intel.lookup(_raw(db), [ev.get("sha256"), ev.get("ip")]) + await soc_watchlist.hits_for(db, doc)
    return {
        "risk": v["risk"],
        "host": {"agentId": agent_id, "enrolled": bool(agent), "hostname": (agent or {}).get("hostname"),
                 "ip": (agent or {}).get("ipAddress"), "os": ((agent or {}).get("meta") or {}).get("os") or (agent or {}).get("platform"),
                 "lastSeen": (agent or {}).get("lastSeen"), "status": (agent or {}).get("status"), "agentVersion": (agent or {}).get("version"),
                 "importance": ctx.get("importance") or "medium", "owner": ctx.get("owner"), "otherActiveAlerts": others},
        "user": (v.get("evidence") or {}).get("user"),
        "indicators": {"sha256": ev.get("sha256"), "ip": ev.get("ip")},
        "threatIntel": hits,
        "feeds": await soc_threat_intel.feed_status(_raw(db)),
    }
