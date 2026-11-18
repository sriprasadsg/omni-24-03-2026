"""SOC incidents: the alerts on one endpoint that arrive less than an hour apart belong to one incident.

The grouping rule is the one Autonomous Ops uses (autonomous_ops/incidents.py, D-16): an incident keeps
taking new alerts (``grouping`` true) until an hour passes with none, then the next alert opens a new
one. A unique partial index allows one grouping incident per endpoint, so racing writers end with one.
Repeats of an alert do not move the incident (the alert counts them). Closing an incident stops its
grouping. The analyst status (open / acknowledged / closed with a resolution) is separate from grouping.

An incident lists its MITRE tactics in attack order (the ATT&CK matrix order), links the Autonomous Ops
incident of the same endpoint when one is open (``autonomyIncidentId``; never changes it), and can open a
case. Nothing is deleted.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from mitre_service import ATTACK_MATRIX
from soc_alerts import SEVERITIES, severity_of, status_of
from soc_service import STATUS_QUERY, TECHNIQUE_NAMES, parse_ts, scope_filter, techniques_of, view

logger = logging.getLogger(__name__)

GAP = timedelta(hours=1)
RANK = {s: i for i, s in enumerate(SEVERITIES)}
TACTIC_ORDER = [t["name"] for t in ATTACK_MATRIX["tactics"]]
_TRIES = 4


def _ms(at: datetime) -> datetime:
    return at.replace(microsecond=at.microsecond // 1000 * 1000)


def tactics_of(techniques: List[str]) -> List[str]:
    """The ATT&CK tactics of these techniques, in attack order (sub-techniques fall back to their parent)."""
    names = set()
    for t in techniques:
        tactic = (TECHNIQUE_NAMES.get(t) or TECHNIQUE_NAMES.get(t.split(".")[0]) or ("", ""))[1]
        if tactic:
            names.add(tactic)
    return [t for t in TACTIC_ORDER if t in names]


async def ensure_indexes(db) -> None:
    await db.soc_incidents.create_index([("tenantId", 1), ("agentId", 1)], unique=True,
                                        partialFilterExpression={"grouping": True}, name="soc_incident_one_grouping")
    await db.soc_incidents.create_index([("tenantId", 1), ("status", 1), ("lastAlertAt", -1)], name="soc_incident_recent")
    await db.soc_incidents.create_index("id", unique=True, name="soc_incident_id")
    await db.security_alerts.create_index([("tenantId", 1), ("incidentId", 1)], name="soc_alert_incident")


async def _autonomy_link(db, tenant_id: Optional[str], agent_id: Optional[str]) -> Optional[str]:
    try:
        raw = getattr(db, "_db", db)
        doc = await raw.autonomy_incidents.find_one({"tenantId": tenant_id, "agentId": agent_id, "closed": False}, {"_id": 0, "id": 1})
        return (doc or {}).get("id")
    except Exception:  # a link is a courtesy
        return None


async def attach(db, alert: Dict[str, Any]) -> Optional[str]:
    """Put a new alert on its endpoint's incident (opening one when needed); returns the incident id."""
    tenant, agent = alert.get("tenantId"), alert.get("agent_id") or None
    at = parse_ts(alert.get("created_at")) or datetime.now(timezone.utc)
    at = _ms(at)
    rank = RANK.get(severity_of(alert.get("severity")), len(SEVERITIES))
    techs = techniques_of(alert)
    for _ in range(_TRIES):
        found = await db.soc_incidents.find_one_and_update(
            {"tenantId": tenant, "agentId": agent, "grouping": True, "lastAlertAt": {"$gt": at - GAP}},
            {"$max": {"lastAlertAt": at}, "$min": {"startedAt": at, "severityRank": rank}, "$inc": {"alertCount": 1},
             "$addToSet": {"techniques": {"$each": techs}}},
            projection={"_id": 0, "id": 1}, return_document=ReturnDocument.AFTER)
        if found:
            break
        await db.soc_incidents.update_many(
            {"tenantId": tenant, "agentId": agent, "grouping": True, "lastAlertAt": {"$lte": at - GAP}},
            {"$set": {"grouping": False}})
        found = {"id": f"SINC-{uuid.uuid4().hex[:12]}", "tenantId": tenant, "agentId": agent, "grouping": True,
                 "status": "open", "startedAt": at, "lastAlertAt": at, "alertCount": 1, "severityRank": rank,
                 "techniques": techs, "autonomyIncidentId": await _autonomy_link(db, tenant, agent),
                 "createdAt": datetime.now(timezone.utc)}
        try:
            await db.soc_incidents.insert_one(dict(found))
            break
        except DuplicateKeyError:
            continue
    else:
        logger.warning("SOC incident for %s could not be opened", agent)
        return None
    await db.security_alerts.update_one({"id": alert.get("id"), "tenantId": tenant}, {"$set": {"incidentId": found["id"]}})
    return found["id"]


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else v


def incident_view(inc: Dict[str, Any], top: Optional[Dict[str, Any]] = None, host: Optional[str] = None) -> Dict[str, Any]:
    status, resolution = status_of(inc)
    severity = SEVERITIES[inc["severityRank"]] if isinstance(inc.get("severityRank"), int) and inc["severityRank"] < len(SEVERITIES) else "info"
    count = int(inc.get("alertCount") or 0)
    lead = (top or {}).get("title") or "Alerts"
    return {
        "id": inc["id"], "tenantId": inc.get("tenantId"), "agentId": inc.get("agentId"), "hostname": host,
        "title": lead + (f" and {count - 1} more" if count > 1 else ""), "severity": severity,
        "status": status, "resolution": resolution, "alertCount": count, "grouping": bool(inc.get("grouping")),
        "startedAt": _iso(inc.get("startedAt")), "lastAlertAt": _iso(inc.get("lastAlertAt")),
        "tactics": tactics_of(inc.get("techniques") or []), "techniques": inc.get("techniques") or [],
        "assignee": inc.get("assignee"), "acknowledgedAt": inc.get("acknowledgedAt"), "acknowledgedBy": inc.get("acknowledgedBy"),
        "closedAt": inc.get("closedAt"), "closedBy": inc.get("closedBy"), "closeNote": inc.get("closeNote"),
        "caseId": inc.get("caseId"), "autonomyIncidentId": inc.get("autonomyIncidentId"),
        "aiSummary": inc.get("aiSummary") if isinstance(inc.get("aiSummary"), dict) else None,
    }


async def _leads(db, incidents: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The most severe (then latest) alert of each incident, for its title."""
    ids = [i["id"] for i in incidents]
    if not ids:
        return {}
    rows = await db.security_alerts.find({"incidentId": {"$in": ids}}, {"_id": 0, "incidentId": 1, "title": 1, "severity": 1,
                                                                         "created_at": 1}).to_list(5000)
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)   # latest first wins a tie
    best: Dict[str, tuple] = {}
    for r in rows:
        rank = RANK.get(severity_of(r.get("severity")), len(SEVERITIES))
        if r["incidentId"] not in best or rank < best[r["incidentId"]][0]:
            best[r["incidentId"]] = (rank, r)
    return {k: v[1] for k, v in best.items()}


async def _hosts(db, agent_ids: List[Optional[str]]) -> Dict[str, str]:
    ids = sorted({a for a in agent_ids if a})
    rows = await db.agents.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "hostname": 1}).to_list(len(ids) or 1) if ids else []
    return {r["id"]: r.get("hostname") or r["id"] for r in rows}


async def list_incidents(db, scope: Optional[str], status: str = "active", limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    filt = {**scope_filter(scope)}
    filt["status"] = {"$in": STATUS_QUERY[status]} if status in STATUS_QUERY else {"$exists": True}
    total = await db.soc_incidents.count_documents(filt)
    rows = await db.soc_incidents.find(filt, {"_id": 0}).sort([("severityRank", 1), ("lastAlertAt", -1)]).skip(offset).limit(limit).to_list(limit)
    leads, hosts = await _leads(db, rows), await _hosts(db, [r.get("agentId") for r in rows])
    return {"items": [incident_view(r, leads.get(r["id"]), hosts.get(r.get("agentId"))) for r in rows],
            "total": total, "limit": limit, "offset": offset}


async def get_incident(db, scope: Optional[str], incident_id: str) -> Dict[str, Any]:
    inc = await db.soc_incidents.find_one({"id": incident_id, **scope_filter(scope)}, {"_id": 0})
    if not inc:
        return {}
    alerts = await db.security_alerts.find({"incidentId": incident_id, "tenantId": inc.get("tenantId"),
                                            "status": {"$nin": ["merged", "archived"]}}, {"_id": 0}).sort("created_at", 1).to_list(500)
    hosts = await _hosts(db, [inc.get("agentId")])
    leads = await _leads(db, [inc])
    return {**incident_view(inc, leads.get(incident_id), hosts.get(inc.get("agentId"))),
            "timeline": [view(a, hosts) for a in alerts]}


async def backfill(db, now: Optional[datetime] = None) -> int:
    """Group alerts that have no incident yet, endpoint by endpoint in time order (migration 037)."""
    now = now or datetime.now(timezone.utc)
    cursor = db.security_alerts.find({"incidentId": {"$exists": False}, "status": {"$nin": ["merged", "archived"]}},
                                     {"_id": 0}).sort([("tenantId", 1), ("agent_id", 1), ("created_at", 1)])
    made, current, key = 0, None, None
    async for a in cursor:
        at = parse_ts(a.get("created_at")) or now
        at = _ms(at)
        k = (a.get("tenantId"), a.get("agent_id") or None)
        if current is None or k != key or at - current["lastAlertAt"] > GAP:
            if current is not None:
                await _save_backfilled(db, current, now)
            key = k
            current = {"id": f"SINC-{uuid.uuid4().hex[:12]}", "tenantId": k[0], "agentId": k[1], "startedAt": at,
                       "lastAlertAt": at, "alertCount": 0, "severityRank": len(SEVERITIES), "techniques": [],
                       "alerts": [], "createdAt": now}
            made += 1
        current["lastAlertAt"] = max(current["lastAlertAt"], at)
        current["alertCount"] += 1
        current["severityRank"] = min(current["severityRank"], RANK.get(severity_of(a.get("severity")), len(SEVERITIES)))
        current["techniques"] = list(dict.fromkeys(current["techniques"] + techniques_of(a)))
        current["alerts"].append((a.get("id"), status_of(a)))
    if current is not None:
        await _save_backfilled(db, current, now)
    return made


async def _save_backfilled(db, inc: Dict[str, Any], now: datetime) -> None:
    alerts = inc.pop("alerts")
    statuses = [s for _, (s, _) in alerts]
    closed = all(s == "closed" for s in statuses)
    inc["status"] = "closed" if closed else ("acknowledged" if all(s != "open" for s in statuses) else "open")
    if closed:
        resolutions = [r for _, (_, r) in alerts if r]
        inc["resolution"] = max(set(resolutions), key=resolutions.count) if resolutions else "resolved"
    last = inc["lastAlertAt"] if inc["lastAlertAt"].tzinfo else inc["lastAlertAt"].replace(tzinfo=timezone.utc)
    inc["grouping"] = (not closed) and now - last < GAP
    inc["autonomyIncidentId"] = await _autonomy_link(db, inc["tenantId"], inc["agentId"]) if inc["grouping"] else None
    try:
        await db.soc_incidents.insert_one(dict(inc))
    except DuplicateKeyError:            # a live alert opened this endpoint's grouping incident meanwhile
        inc["grouping"] = False
        await db.soc_incidents.insert_one(dict(inc))
    await db.security_alerts.update_many({"id": {"$in": [i for i, _ in alerts if i]}, "tenantId": inc["tenantId"]},
                                         {"$set": {"incidentId": inc["id"]}})


async def act(scope: Optional[str], incident_id: str, action: str, user: Any, resolution: Optional[str] = None,
              note: Optional[str] = None, close_alerts: bool = False) -> Dict[str, Any]:
    """Acknowledge, assign, close (optionally closing its active alerts the same way) or reopen an incident."""
    import soc_actions
    from database import get_database
    db = get_database()
    precondition, update = soc_actions.change_for(action, user, datetime.now(timezone.utc).isoformat(), resolution, note)
    if action == "archive":
        raise soc_actions.ActionError("Incidents are closed, not archived", 400)
    inc = await db.soc_incidents.find_one({"id": incident_id, **scope_filter(scope)}, {"_id": 0, "id": 1, "tenantId": 1})
    if not inc:
        raise soc_actions.ActionError("Incident not found", 404)
    if action == "close":
        update = [*update, {"$set": {"grouping": False}}]
    result = await db.soc_incidents.update_one({"id": incident_id, **scope_filter(scope), "status": precondition}, update)
    if result.matched_count == 0:
        raise soc_actions.ActionError(f"This incident can't be {soc_actions.PAST[action]} in its current state; refresh and try again")
    closed_alerts = 0
    if action == "close" and close_alerts:
        _, alert_update = soc_actions.change_for("close", user, datetime.now(timezone.utc).isoformat(), resolution, note)
        res = await db.security_alerts.update_many(
            {"incidentId": incident_id, "tenantId": inc["tenantId"], "status": {"$in": STATUS_QUERY["active"]}}, alert_update)
        closed_alerts = res.modified_count
    await soc_actions._audit(f"soc.incident.{action}", inc["tenantId"], user, incidentId=incident_id,
                             resolution=resolution, closedAlerts=closed_alerts)
    return {**(await get_incident(db, scope, incident_id)), "closedAlerts": closed_alerts}


async def open_case(scope: Optional[str], incident_id: str, user: Any) -> Dict[str, Any]:
    """A security case holding the incident's alerts (or the case it already has)."""
    import soc_actions
    from database import get_database
    db = get_database()
    inc = await get_incident(db, scope, incident_id)
    if not inc:
        raise soc_actions.ActionError("Incident not found", 404)
    if inc.get("caseId"):
        existing = await db.security_cases.find_one({"id": inc["caseId"], **scope_filter(scope)}, {"_id": 0})
        if existing:
            return {"case": existing, "created": False}
    now = datetime.now(timezone.utc).isoformat()
    sev = soc_actions._case_severity(inc["severity"])
    case = {
        "id": f"case-{uuid.uuid4()}", "tenantId": inc["tenantId"], "title": f"Incident: {inc['title']}"[:300],
        "status": "New", "severity": sev, "owner": soc_actions._actor(user), "createdAt": now, "updatedAt": now,
        "relatedEvents": [{
            "id": a["id"], "tenantId": inc["tenantId"], "timestamp": a["createdAt"], "severity": soc_actions._case_severity(a["severity"]),
            "description": a["description"] or a["title"], "type": a["typeLabel"],
            "source": {"ip": "", "hostname": inc.get("hostname") or inc.get("agentId") or ""}, "details": a["evidence"],
        } for a in inc["timeline"][:50]],
        "comments": [], "enrichmentData": [], "alertIds": [a["id"] for a in inc["timeline"]], "incidentId": incident_id,
    }
    await db.security_cases.insert_one({**case, "_id": case["id"]})
    case.pop("_id", None)
    await db.soc_incidents.update_one({"id": incident_id, **scope_filter(scope)}, {"$set": {"caseId": case["id"]}})
    await soc_actions._audit("soc.incident.case", inc["tenantId"], user, incidentId=incident_id, caseId=case["id"])
    return {"case": case, "created": True}
