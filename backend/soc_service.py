"""SOC console data: a tenant's security alerts summarised over a range, and the alert queue.

Reads ``security_alerts`` (every detection, written through soc_alerts.record_alert) and the legacy
``alerts`` collection (alerts posted to /api/alerts), so the console and Alert Management show one
list. Nothing is estimated: response times appear once analysts acknowledge or close alerts, and
MITRE techniques are only those an alert names (or its type maps to in mitre_service).

``scope`` is a tenant id, or None for a Super Admin's all-tenant view.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from database import get_database
from network_topology_service import HIDDEN_AGENT_STATUSES, ONLINE_WITHIN
from mitre_service import ALERT_TYPE_TO_TECHNIQUE, ATTACK_MATRIX
from soc_alerts import ACTIVE, HIDDEN, SEVERITIES, TYPE_LABELS, severity_of, status_of, type_label

# Range -> (seconds, bucket seconds)
RANGES: Dict[str, tuple] = {"1h": (3600, 300), "24h": (86400, 3600), "7d": (604800, 21600), "30d": (2592000, 86400)}
MAX_ROWS = 20000
TECHNIQUE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")
TECHNIQUE_NAMES = {t["id"]: (t["name"], tac["name"]) for tac in ATTACK_MATRIX["tactics"] for t in tac["techniques"]}
# Checks an agent reports in availableCapabilities, and the alert types they raise.
CHECKS = {"fim": "File integrity", "runtime_security": "Runtime threats", "ueba": "User behaviour",
          "shadow_ai": "Shadow AI", "vulnerability_scanning": "Vulnerabilities"}
STATUS_QUERY = {
    "active": ["open", "new", "acknowledged"],
    "open": ["open", "new"],
    "acknowledged": ["acknowledged"],
    "closed": ["closed", "resolved", "false_positive", "benign", "approved", "dismissed"],
}
EVIDENCE_KEYS = ("process", "exe", "sha256", "vt_detection_ratio", "location", "risk_score", "rule", "path", "target")


def parse_ts(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def techniques_of(doc: Dict[str, Any]) -> List[str]:
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    text = " ".join(str(v) for v in (doc.get("mitre_technique"), doc.get("mitre"), meta.get("mitre"),
                                     meta.get("description"), doc.get("title"), doc.get("description")) if v)
    found = list(dict.fromkeys(TECHNIQUE.findall(text)))
    mapped = ALERT_TYPE_TO_TECHNIQUE.get(str(doc.get("type") or ""))
    return found or ([mapped] if mapped else [])


def _evidence(doc: Dict[str, Any]) -> Dict[str, Any]:
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    out = {k: doc[k] for k in EVIDENCE_KEYS if doc.get(k) not in (None, "")}
    for k, v in meta.items():
        if k in ("tenantId", "agent_id", "severity", "description", "type") or v in (None, ""):
            continue
        out[k] = v[:20] if isinstance(v, list) else v
    return out


def view(doc: Dict[str, Any], hosts: Optional[Dict[str, str]] = None, legacy: bool = False) -> Dict[str, Any]:
    """One alert in the console's shape, whichever collection and writer it came from."""
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    status, resolution = status_of(doc)
    agent = doc.get("agent_id") or doc.get("agentId") or meta.get("agent_id")
    created = doc.get("created_at") or doc.get("timestamp")
    kind = str(doc.get("type") or "")
    return {
        "id": doc.get("id") or str(doc.get("_id")),
        "source": "legacy" if legacy else "security",
        "type": kind, "typeLabel": type_label(kind),
        "severity": severity_of(doc.get("severity")),
        "title": doc.get("title") or doc.get("message") or type_label(kind),
        "description": doc.get("description") or "",
        "status": status, "resolution": resolution,
        "tenantId": doc.get("tenantId") or meta.get("tenantId"),
        "agentId": agent,
        "hostname": (hosts or {}).get(agent) or doc.get("hostname"),
        "createdAt": created,
        "lastSeenAt": doc.get("lastSeenAt") or created,
        "occurrences": int(doc.get("occurrences") or 1),
        "assignee": doc.get("assignee"),
        "acknowledgedAt": doc.get("acknowledgedAt"), "acknowledgedBy": doc.get("acknowledgedBy"),
        "closedAt": doc.get("closedAt"), "closedBy": doc.get("closedBy"), "closeNote": doc.get("closeNote"),
        "autoClosed": bool(doc.get("autoClosed")),
        "caseId": doc.get("caseId"),
        "aiTriage": doc.get("aiTriage") if isinstance(doc.get("aiTriage"), dict) else None,
        "origin": doc["source"] if isinstance(doc.get("source"), dict) else None,  # legacy alerts: {ip, hostname}
        "mitre": techniques_of(doc),
        "evidence": _evidence(doc),
    }


def _avg_seconds(pairs: Iterable[tuple]) -> Dict[str, Any]:
    spans = [(b - a).total_seconds() for a, b in pairs if a and b and b >= a]
    return {"seconds": round(sum(spans) / len(spans)) if spans else None, "count": len(spans)}


def build_summary(alerts: List[Dict[str, Any]], agents: List[Dict[str, Any]], range_key: str, now: datetime,
                  sources: Optional[List[Dict[str, Any]]] = None, counts: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Everything the console's overview shows, from viewed alerts (``view``) and the scope's agents."""
    span, bucket = RANGES[range_key]
    start, prev_start = now - timedelta(seconds=span), now - timedelta(seconds=2 * span)
    buckets = span // bucket
    rows = [a for a in alerts if a["status"] not in HIDDEN]
    for a in rows:
        a["_created"], a["_seen"] = parse_ts(a["createdAt"]), parse_ts(a["lastSeenAt"])
    active = [a for a in rows if a["status"] in ACTIVE]
    in_range = [a for a in rows if a["_created"] and a["_created"] >= start]
    previous = [a for a in rows if a["_created"] and prev_start <= a["_created"] < start]
    in_range_ids = {id(a) for a in in_range}
    touched = in_range_ids | {id(a) for a in active}

    trend = [{"t": (start + timedelta(seconds=i * bucket)).isoformat(), **{s: 0 for s in SEVERITIES}} for i in range(buckets)]
    for a in in_range:
        i = min(buckets - 1, int((a["_created"] - start).total_seconds() // bucket))
        trend[i][a["severity"]] += 1

    acked = [(a["_created"], parse_ts(a["acknowledgedAt"])) for a in rows if a.get("acknowledgedAt")]
    closed = [(a["_created"], parse_ts(a["closedAt"])) for a in rows if a.get("closedAt") and not a["autoClosed"]]

    by_type: Dict[str, Dict[str, Any]] = {}
    for a in rows:
        if id(a) not in touched:
            continue
        t = by_type.setdefault(a["type"], {"type": a["type"], "label": a["typeLabel"], "active": 0, "inRange": 0, "lastSeen": None})
        t["active"] += a["status"] in ACTIVE
        t["inRange"] += id(a) in in_range_ids
        if a["_seen"] and (t["lastSeen"] is None or a["_seen"].isoformat() > t["lastSeen"]):
            t["lastSeen"] = a["_seen"].isoformat()

    agent_by_id = {g.get("id"): g for g in agents}
    per_agent: Dict[str, Counter] = defaultdict(Counter)
    last_alert: Dict[str, str] = {}
    for a in active:
        key = a["agentId"] or ""
        per_agent[key][a["severity"]] += 1
        seen = a["_seen"].isoformat() if a["_seen"] else ""
        last_alert[key] = max(last_alert.get(key, ""), seen)
    endpoints = []
    for key, sev in per_agent.items():
        agent = agent_by_id.get(key) or {}
        seen = parse_ts(agent.get("lastSeen"))
        endpoints.append({
            "agentId": key or None, "hostname": agent.get("hostname") or (key or "No endpoint"),
            "online": bool(seen and now - seen <= ONLINE_WITHIN), "known": bool(agent),
            "active": sum(sev.values()), **{s: sev.get(s, 0) for s in SEVERITIES},
            "lastAlertAt": last_alert.get(key) or None,
        })
    endpoints.sort(key=lambda e: tuple(-e[s] for s in SEVERITIES) + (e["hostname"],))

    mitre = Counter(t for a in rows if id(a) in touched for t in a["mitre"])
    online = [g for g in agents if (s := parse_ts(g.get("lastSeen"))) and now - s <= ONLINE_WITHIN]
    coverage = [{"check": c, "label": label,
                 "agents": sum(1 for g in agents if c in (g.get("availableCapabilities") or []))} for c, label in CHECKS.items()]

    return {
        "generatedAt": now.isoformat(), "range": range_key, "rangeSeconds": span, "bucketSeconds": bucket,
        "kpis": {
            "active": len(active),
            "open": sum(1 for a in active if a["status"] == "open"),
            "activeBySeverity": {s: sum(1 for a in active if a["severity"] == s) for s in SEVERITIES},
            "newInRange": len(in_range), "newPrevious": len(previous),
            "occurrencesInRange": sum(a["occurrences"] for a in in_range),
            "timeToAcknowledge": _avg_seconds((c, t) for c, t in acked if t and t >= start),
            "timeToClose": _avg_seconds((c, t) for c, t in closed if t and t >= start),
            "endpointsWithActive": sum(1 for e in endpoints if e["agentId"]),
            "removedWithActive": sum(1 for e in endpoints if e["agentId"] and not e["known"]),
            "endpointsOnline": len(online), "endpoints": len(agents),
        },
        "trend": trend,
        "byType": sorted(by_type.values(), key=lambda t: (-t["active"], -t["inRange"], t["label"])),
        "endpoints": endpoints[:8],
        "mitre": [{"technique": t, "name": TECHNIQUE_NAMES.get(t, (t, ""))[0], "tactic": TECHNIQUE_NAMES.get(t, ("", ""))[1],
                   "count": n} for t, n in mitre.most_common(10)],
        "sources": sources or [],
        "coverage": coverage,
        "counts": counts or {},
    }


def scope_filter(scope: Optional[str]) -> Dict[str, Any]:
    return {"tenantId": scope} if scope else {}


def queue_filter(scope: Optional[str], status: str = "active", severity: Optional[str] = None,
                 alert_type: Optional[str] = None, agent_id: Optional[str] = None, q: Optional[str] = None) -> Dict[str, Any]:
    """Mongo filter for the queue; matches rows of both collections (legacy severities are capitalised)."""
    filt: Dict[str, Any] = dict(scope_filter(scope))
    filt["status"] = {"$in": STATUS_QUERY[status]} if status in STATUS_QUERY else {"$nin": list(HIDDEN)}
    if severity:
        filt["severity"] = {"$in": [severity, severity.capitalize(), severity.upper()]}
    if alert_type:
        filt["type"] = alert_type
    if agent_id:
        filt["agent_id"] = agent_id
    if q:
        pattern = {"$regex": re.escape(q.strip()[:100]), "$options": "i"}
        filt["$or"] = [{"title": pattern}, {"description": pattern}, {"message": pattern}]
    return filt


async def _hostnames(db, agent_ids: Iterable[Optional[str]]) -> Dict[str, str]:
    ids = sorted({a for a in agent_ids if a})
    if not ids:
        return {}
    rows = await db.agents.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "hostname": 1}).to_list(len(ids))
    return {r["id"]: r.get("hostname") or r["id"] for r in rows}


async def alert_queue(scope: Optional[str], status: str = "active", severity: Optional[str] = None,
                      alert_type: Optional[str] = None, agent_id: Optional[str] = None, q: Optional[str] = None,
                      limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """One page of the queue: active alerts first, then by severity, newest activity first."""
    db = get_database()
    filt = queue_filter(scope, status, severity, alert_type, agent_id, q)
    sev_rank = {"$switch": {"branches": [{"case": {"$eq": [{"$toLower": "$severity"}, s]}, "then": i}
                                         for i, s in enumerate(SEVERITIES)], "default": len(SEVERITIES)}}
    pipeline = [
        {"$match": filt},
        {"$unionWith": {"coll": "alerts", "pipeline": [{"$match": filt}, {"$addFields": {"_legacy": True}}]}},
        {"$addFields": {
            "_act": {"$cond": [{"$in": [{"$toLower": {"$ifNull": ["$status", "open"]}}, STATUS_QUERY["active"]]}, 0, 1]},
            "_sev": sev_rank,
            "_seen": {"$ifNull": ["$lastSeenAt", {"$ifNull": ["$created_at", "$timestamp"]}]},
        }},
        {"$sort": {"_act": 1, "_sev": 1, "_seen": -1}},
        {"$facet": {"items": [{"$skip": offset}, {"$limit": limit}], "total": [{"$count": "n"}]}},
    ]
    result = await db.security_alerts.aggregate(pipeline).to_list(1)
    page = result[0] if result else {"items": [], "total": []}
    docs = page.get("items", [])
    hosts = await _hostnames(db, (d.get("agent_id") or d.get("agentId") for d in docs))
    total = page["total"][0]["n"] if page.get("total") else 0
    return {"items": [view(d, hosts, legacy=bool(d.get("_legacy"))) for d in docs], "total": total,
            "limit": limit, "offset": offset}


async def _source_health(db, scope: Optional[str]) -> List[Dict[str, Any]]:
    """Last alert and total per detection type, over all time, so a quiet source shows as quiet."""
    pipeline = [
        {"$match": {**scope_filter(scope), "status": {"$nin": list(HIDDEN)}}},
        {"$group": {"_id": "$type", "last": {"$max": {"$ifNull": ["$lastSeenAt", "$created_at"]}}, "total": {"$sum": 1}}},
    ]
    seen = {r["_id"]: r for r in await db.security_alerts.aggregate(pipeline).to_list(200)}
    kinds = list(TYPE_LABELS) + sorted(k for k in seen if k and k not in TYPE_LABELS)
    return [{"type": k, "label": type_label(k), "lastAlertAt": (seen.get(k) or {}).get("last"),
             "total": (seen.get(k) or {}).get("total", 0)} for k in kinds]


async def _counts(db, scope: Optional[str]) -> Dict[str, int]:
    raw = getattr(db, "_db", db)  # siem_rules / xdr_hunts keep their own tenant fields
    rules = {"tenant_id": scope} if scope else {}
    hunts = {"tenantId": {"$in": [scope, "global"]}} if scope else {}
    return {
        "openCases": await db.security_cases.count_documents({**scope_filter(scope), "status": {"$nin": ["Resolved", "Closed"]}}),
        "siemRules": await raw.siem_rules.count_documents(rules),
        "activeHunts": await raw.xdr_hunts.count_documents({**hunts, "status": "active"}),
    }


async def soc_summary(scope: Optional[str], range_key: str = "24h", now: Optional[datetime] = None) -> Dict[str, Any]:
    db = get_database()
    now = now or datetime.now(timezone.utc)
    span, _ = RANGES[range_key]
    since = (now - timedelta(seconds=2 * span)).isoformat()
    filt = {**scope_filter(scope), "$or": [
        {"status": {"$in": STATUS_QUERY["active"]}},
        {"created_at": {"$gte": since}}, {"timestamp": {"$gte": since}}, {"lastSeenAt": {"$gte": since}},
        {"acknowledgedAt": {"$gte": since}}, {"closedAt": {"$gte": since}},
    ]}
    docs = await db.security_alerts.find(filt, {"_id": 0}).sort("created_at", -1).to_list(MAX_ROWS)
    docs += [{**d, "_legacy": True} for d in await db.alerts.find(filt, {"_id": 0}).to_list(MAX_ROWS)]
    agents = [g for g in await db.agents.find(scope_filter(scope), {"_id": 0, "id": 1, "hostname": 1, "lastSeen": 1,
                                                                    "status": 1, "availableCapabilities": 1}).to_list(5000)
              if g.get("status") not in HIDDEN_AGENT_STATUSES]
    hosts = {g["id"]: g.get("hostname") or g["id"] for g in agents if g.get("id")}
    alerts = [view(d, hosts, legacy=bool(d.get("_legacy"))) for d in docs]
    summary = build_summary(alerts, agents, range_key, now, await _source_health(db, scope), await _counts(db, scope))
    summary["truncated"] = len(docs) >= MAX_ROWS
    return summary
