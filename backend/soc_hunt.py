"""Threat hunting over real data: SOC alerts, SIEM events and agent logs, one structured query at a time.

A hunt names one source, field filters (equals, not equals, any of, contains, matches, present), free text, a time
range and optionally a field to count by. It is not a query language: fields come from each source's list (FIELDS),
values are matched as data (contains and free text are escaped, a pattern is checked and bounded), every query
carries the caller's tenant and runs under a time limit. A result is the matching total (count_documents over the
same filter, so it equals a direct count), the newest rows and, with count by, the largest groups.

Saved hunts (``soc_hunts``) belong to an organization; a rerun records when it ran and what it counted. A hunt over
SIEM events whose filters are all exact can become a SIEM rule (``to_rule``): its filters become ``logic.match``, its
count-by field the threshold's groupBy, and the rule records hits for 7 days before it alerts, like the platform
library (siem_pipeline).
"""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pymongo.errors import ExecutionTimeout, OperationFailure

from soc_alerts import HIDDEN

PLATFORM = "platform-admin"
RANGES = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000, "90d": 7776000}
OPS = ("eq", "ne", "in", "contains", "regex", "exists")
RULE_OPS = ("eq", "in")  # what siem_pipeline._matches runs
MAX_FILTERS, MAX_IN, MAX_VALUE = 10, 20, 200
ROWS, GROUPS, VALUES = 100, 50, 25
MAX_MS = 15000
MAX_HUNTS = 200
RECORD_DAYS = 7
RULE_SEVERITIES = ("Critical", "High", "Medium", "Low")

# source -> collection, its time field (ISO string or BSON date), the fields a hunt may use (public name -> stored
# path, label, whether the console offers its values), and the text that free text searches.
SOURCES: Dict[str, Dict[str, Any]] = {
    "alerts": {"collection": "security_alerts", "time": "created_at", "iso": True, "text": ("title", "description"),
               "label": "SOC alerts", "hidden": {"status": {"$nin": list(HIDDEN)}}},
    "events": {"collection": "soc_log_events", "time": "at", "iso": False, "text": ("message",),
               "label": "SIEM events"},
    "logs": {"collection": "logs", "time": "timestamp", "iso": True, "text": ("message",), "label": "Agent logs"},
}
FIELDS: Dict[str, Dict[str, tuple]] = {
    "alerts": {"severity": ("severity", "Severity", True), "status": ("status", "Status", True),
               "type": ("type", "Detection", True), "agentId": ("agent_id", "Endpoint", True),
               "process": ("process", "Process", False), "exe": ("exe", "Executable", False),
               "user": ("metadata.user", "User", True), "remoteIp": ("metadata.remote_ip", "Remote IP", False),
               "title": ("title", "Title", False)},
    "events": {"source": ("source", "Log source", True), "action": ("action", "Action", True),
               "outcome": ("outcome", "Outcome", True), "user": ("user", "User", True),
               "srcIp": ("srcIp", "Source IP", True), "host": ("host", "Host", True),
               "process": ("process", "Process", True), "eventId": ("eventId", "Windows event ID", True),
               "logonType": ("logonType", "Logon type", True), "group": ("group", "Group", True),
               "command": ("command", "Command", False), "agentId": ("agentId", "Endpoint", True)},
    "logs": {"service": ("service", "Log", True), "severity": ("severity", "Level", True),
             "agentId": ("agentId", "Endpoint", True)},
}
INT_FIELDS = {"eventId"}
TENANT_FIELD = ("tenantId", "Organization", True)  # only in a Super Admin's all-tenant view


class HuntError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def fields_of(source: str, all_tenants: bool) -> Dict[str, tuple]:
    return {**FIELDS[source], **({"tenantId": TENANT_FIELD} if all_tenants else {})}


def _value(field: str, v: Any) -> Any:
    s = str(v if v is not None else "").strip()[:MAX_VALUE]
    if field in INT_FIELDS:
        try:
            return int(s)
        except ValueError:
            raise HuntError(f"{field} takes a number")
    return s


def normalize(query: Any, all_tenants: bool = False) -> Dict[str, Any]:
    """A hunt query as stored and run: checked source, filters, text, range and count by (raises HuntError)."""
    if not isinstance(query, dict):
        raise HuntError("A hunt query must be an object")
    source = query.get("source")
    if source not in SOURCES:
        raise HuntError(f"source must be one of {', '.join(SOURCES)}")
    allowed = fields_of(source, all_tenants)
    raw_filters = query.get("filters") or []
    if not isinstance(raw_filters, list) or len(raw_filters) > MAX_FILTERS:
        raise HuntError(f"A hunt takes at most {MAX_FILTERS} filters")
    filters = []
    for f in raw_filters:
        if not isinstance(f, dict) or f.get("field") not in allowed:
            raise HuntError(f"Unknown field for {SOURCES[source]['label']}: {f.get('field') if isinstance(f, dict) else f}")
        field, op = f["field"], f.get("op") or "eq"
        if op not in OPS:
            raise HuntError(f"op must be one of {', '.join(OPS)}")
        if op == "exists":
            value: Any = bool(f.get("value", True))
        elif op == "in":
            values = f.get("value")
            if not isinstance(values, list) or not 1 <= len(values) <= MAX_IN:
                raise HuntError(f"'any of' takes a list of 1 to {MAX_IN} values")
            value = list(dict.fromkeys(_value(field, v) for v in values))
        else:
            value = _value(field, f.get("value"))
            if value == "" and op != "eq":
                raise HuntError(f"The {field} filter needs a value")
            if op == "regex":
                try:
                    re.compile(value)
                except re.error as e:
                    raise HuntError(f"The pattern for {field} is not valid: {e}")
            if op in ("contains", "regex") and field in INT_FIELDS:
                raise HuntError(f"{field} takes equals, not equals, any of or present")
        filters.append({"field": field, "op": op, "value": value})
    text = str(query.get("text") or "").strip()[:MAX_VALUE]
    range_key = query.get("range") or "24h"
    if range_key not in RANGES:
        raise HuntError(f"range must be one of {', '.join(RANGES)}")
    count_by = query.get("countBy") or None
    if count_by is not None and count_by not in allowed:
        raise HuntError(f"Cannot count {SOURCES[source]['label']} by {count_by}")
    return {"source": source, "filters": filters, "text": text, "range": range_key, "countBy": count_by}


def _condition(path: str, op: str, value: Any) -> Dict[str, Any]:
    if op == "eq":
        return {path: value}
    if op == "ne":
        return {path: {"$ne": value}}
    if op == "in":
        return {path: {"$in": value}}
    if op == "contains":
        return {path: {"$regex": re.escape(value), "$options": "i"}}
    if op == "regex":
        return {path: {"$regex": value, "$options": "i"}}
    return {path: {"$nin": [None, ""]}} if value else {path: {"$in": [None, ""]}}  # exists: missing or empty


def build_filter(q: Dict[str, Any], scope: Optional[str], now: datetime) -> Dict[str, Any]:
    """The Mongo filter of a normalized hunt: tenant, time range, then every condition ANDed."""
    src = SOURCES[q["source"]]
    since = now - timedelta(seconds=RANGES[q["range"]])
    filt: Dict[str, Any] = {**({"tenantId": scope} if scope else {}), **src.get("hidden", {}),
                            src["time"]: {"$gte": since.isoformat() if src["iso"] else since}}
    paths = fields_of(q["source"], scope is None)
    conds = [_condition(paths[f["field"]][0], f["op"], f["value"]) for f in q["filters"]]
    if q["text"]:
        needle = re.escape(q["text"])
        conds.append({"$or": [{t: {"$regex": needle, "$options": "i"}} for t in src["text"]]})
    if conds:
        filt["$and"] = conds
    return filt


def _get(doc: Dict[str, Any], path: str) -> Any:
    for part in path.split("."):
        doc = doc.get(part) if isinstance(doc, dict) else None
    return doc


def _iso(value: Any) -> Any:
    return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat() if isinstance(value, datetime) else value


def _row(source: str, doc: Dict[str, Any], paths: Dict[str, tuple], hosts: Dict[str, str]) -> Dict[str, Any]:
    src = SOURCES[source]
    row = {name: _get(doc, spec[0]) for name, spec in paths.items()}
    row["time"] = _iso(doc.get(src["time"]))
    row["text"] = (doc.get("title") if source == "alerts" else doc.get("message")) or ""
    if source == "alerts":
        row["id"], row["description"] = doc.get("id"), str(doc.get("description") or "")[:300]
    if row.get("agentId"):
        row["hostname"] = hosts.get(row["agentId"])
    return row


async def _hostnames(db, ids: List[Any]) -> Dict[str, str]:
    ids = sorted({i for i in ids if isinstance(i, str) and i})
    if not ids:
        return {}
    rows = await db.agents.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "hostname": 1}).to_list(len(ids))
    return {r["id"]: r.get("hostname") or r["id"] for r in rows}


async def run(db, scope: Optional[str], query: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Run a hunt in the caller's scope: total, newest rows, top groups when counting by a field."""
    q = normalize(query, scope is None)
    now = now or datetime.now(timezone.utc)
    src, paths = SOURCES[q["source"]], fields_of(q["source"], scope is None)
    filt, coll = build_filter(q, scope, now), getattr(db, SOURCES[q["source"]]["collection"])
    projection = {"_id": 0, src["time"]: 1, "id": 1, "title": 1, "description": 1, "message": 1,
                  **{spec[0]: 1 for spec in paths.values()}}
    started = datetime.now(timezone.utc)
    try:
        total = await coll.count_documents(filt, maxTimeMS=MAX_MS)
        docs = await coll.find(filt, projection).sort(src["time"], -1).limit(ROWS).max_time_ms(MAX_MS).to_list(ROWS)
        groups: List[Dict[str, Any]] = []
        group_count = 0
        if q["countBy"]:
            path = paths[q["countBy"]][0]
            out = await coll.aggregate([{"$match": filt}, {"$group": {"_id": f"${path}", "count": {"$sum": 1}}},
                                        {"$facet": {"top": [{"$sort": {"count": -1, "_id": 1}}, {"$limit": GROUPS}],
                                                    "n": [{"$count": "n"}]}}], maxTimeMS=MAX_MS).to_list(1)
            groups = [{"value": g["_id"], "count": g["count"]} for g in (out[0]["top"] if out else [])]
            group_count = out[0]["n"][0]["n"] if out and out[0]["n"] else 0
    except ExecutionTimeout:
        raise HuntError(f"The hunt ran longer than {MAX_MS // 1000} seconds; narrow the time range or add a filter", 422)
    except OperationFailure as e:
        raise HuntError(f"The database refused this hunt: {e.details.get('errmsg') if e.details else e}")
    hosts = await _hostnames(db, [_get(d, paths["agentId"][0]) for d in docs if "agentId" in paths]
                             + ([g["value"] for g in groups] if q["countBy"] == "agentId" else []))
    if q["countBy"] == "agentId":
        for g in groups:
            g["label"] = hosts.get(g["value"])
    return {"query": q, "total": total, "rows": [_row(q["source"], d, paths, hosts) for d in docs],
            "groups": groups, "groupCount": group_count, "since": (now - timedelta(seconds=RANGES[q["range"]])).isoformat(),
            "until": now.isoformat(), "tookMs": int((datetime.now(timezone.utc) - started).total_seconds() * 1000)}


async def catalogue(db, scope: Optional[str], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Each source's fields with labels, and the most frequent values of the last 30 days for the listed ones."""
    now, out = now or datetime.now(timezone.utc), {}
    for source, src in SOURCES.items():
        since = now - timedelta(seconds=RANGES["30d"])
        base = {**({"tenantId": scope} if scope else {}), **src.get("hidden", {}),
                src["time"]: {"$gte": since.isoformat() if src["iso"] else since}}
        fields = []
        for name, (path, label, listed) in fields_of(source, scope is None).items():
            values: List[Any] = []
            if listed:
                rows = await getattr(db, src["collection"]).aggregate(
                    [{"$match": {**base, path: {"$nin": [None, ""]}}}, {"$group": {"_id": f"${path}", "n": {"$sum": 1}}},
                     {"$sort": {"n": -1, "_id": 1}}, {"$limit": VALUES}], maxTimeMS=MAX_MS).to_list(VALUES)
                values = [r["_id"] for r in rows if not isinstance(r["_id"], (dict, list))]
            fields.append({"name": name, "label": label, "values": values,
                           "ruleable": source == "events" and name != "tenantId"})
        out[source] = {"label": src["label"], "fields": fields, "text": " and ".join(src["text"])}
    return {"sources": out, "ranges": list(RANGES), "ops": list(OPS)}


# ── Saved hunts ─────────────────────────────────────────────────────────────


def _tenant(scope: Optional[str]) -> str:
    return scope or PLATFORM


def _meta(body: Dict[str, Any]) -> Dict[str, Any]:
    name = str(body.get("name") or "").strip()[:120]
    if not name:
        raise HuntError("A saved hunt needs a name")
    return {"name": name, "description": str(body.get("description") or "").strip()[:500] or None}


async def list_hunts(db, scope: Optional[str]) -> List[Dict[str, Any]]:
    return await db.soc_hunts.find({"tenantId": _tenant(scope)}, {"_id": 0}).sort("updatedAt", -1).to_list(MAX_HUNTS)


async def _load(db, scope: Optional[str], hunt_id: str) -> Dict[str, Any]:
    hunt = await db.soc_hunts.find_one({"id": hunt_id, "tenantId": _tenant(scope)}, {"_id": 0})
    if not hunt:
        raise HuntError("Saved hunt not found", 404)
    return hunt


async def save(db, scope: Optional[str], body: Dict[str, Any], who: str, hunt_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a saved hunt, or replace one's name, description and query."""
    meta, query = _meta(body), normalize(body.get("query"), scope is None)
    tenant, now = _tenant(scope), datetime.now(timezone.utc).isoformat()
    if hunt_id:
        await _load(db, scope, hunt_id)
        await db.soc_hunts.update_one({"id": hunt_id, "tenantId": tenant},
                                      {"$set": {**meta, "query": query, "updatedAt": now, "updatedBy": who}})
        return await _load(db, scope, hunt_id)
    if await db.soc_hunts.count_documents({"tenantId": tenant}) >= MAX_HUNTS:
        raise HuntError(f"An organization keeps at most {MAX_HUNTS} saved hunts", 409)
    hunt = {"id": f"hunt-{uuid.uuid4().hex[:12]}", "tenantId": tenant, **meta, "query": query, "createdBy": who,
            "createdAt": now, "updatedAt": now, "runCount": 0, "lastRunAt": None, "lastCount": None, "ruleId": None}
    await db.soc_hunts.insert_one(dict(hunt))
    return hunt


async def rerun(db, scope: Optional[str], hunt_id: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Run a saved hunt again and record when it ran and what it counted."""
    hunt = await _load(db, scope, hunt_id)
    result = await run(db, scope, hunt["query"], now)
    await db.soc_hunts.update_one({"id": hunt_id, "tenantId": _tenant(scope)},
                                  {"$inc": {"runCount": 1}, "$set": {"lastRunAt": result["until"], "lastCount": result["total"]}})
    return {**result, "hunt": {**hunt, "runCount": hunt.get("runCount", 0) + 1, "lastRunAt": result["until"],
                               "lastCount": result["total"]}}


async def delete(db, scope: Optional[str], hunt_id: str) -> None:
    """Remove a saved hunt; a rule made from it stays (it is the SIEM's now)."""
    if (await db.soc_hunts.delete_one({"id": hunt_id, "tenantId": _tenant(scope)})).deleted_count == 0:
        raise HuntError("Saved hunt not found", 404)


# ── Hunt -> SIEM rule ───────────────────────────────────────────────────────


def rule_logic(q: Dict[str, Any]) -> tuple:
    """(logSource, match) of a hunt that can run as a SIEM rule, else HuntError saying what stops it."""
    if q["source"] != "events":
        raise HuntError("Only a hunt over SIEM events can become a rule")
    if q["text"]:
        raise HuntError("A rule matches fields, not free text: turn the text into a field filter")
    sources = [f for f in q["filters"] if f["field"] == "source" and f["op"] == "eq"]
    if len(sources) != 1:
        raise HuntError("A rule runs on one log source: add exactly one 'Log source equals' filter")
    match: Dict[str, Any] = {}
    for f in q["filters"]:
        if f["field"] == "source":
            if f["op"] != "eq":
                raise HuntError("A rule runs on one log source: add exactly one 'Log source equals' filter")
            continue
        if f["op"] not in RULE_OPS:
            raise HuntError("A rule can use only 'equals' and 'any of' filters")
        if f["field"] in match:
            raise HuntError(f"A rule can filter {f['field']} only once")
        match[f["field"]] = f["value"] if f["op"] == "eq" else {"in": f["value"]}
    if not match:
        raise HuntError("Add at least one filter besides the log source, so the rule does not fire on every event")
    return sources[0]["value"], match


async def to_rule(db, scope: Optional[str], hunt_id: str, body: Dict[str, Any], who: str,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Make a SIEM rule from a saved hunt: N matching events per count-by value within a window."""
    hunt, now = await _load(db, scope, hunt_id), now or datetime.now(timezone.utc)
    if hunt.get("ruleId"):
        raise HuntError("This hunt already has a rule", 409)
    q = normalize(hunt["query"], scope is None)
    log_source, match = rule_logic(q)
    try:
        count, minutes = int(body.get("count") or 1), int(body.get("windowMinutes") or 10)
    except (TypeError, ValueError):
        raise HuntError("count and windowMinutes take whole numbers")
    if not 1 <= count <= 1000 or not 1 <= minutes <= 1440:
        raise HuntError("count runs from 1 to 1000 and windowMinutes from 1 to 1440")
    severity = str(body.get("severity") or "Medium").capitalize()
    if severity not in RULE_SEVERITIES:
        raise HuntError(f"severity must be one of {', '.join(RULE_SEVERITIES)}")
    distinct = body.get("distinct") or None
    if distinct is not None and distinct not in FIELDS["events"]:
        raise HuntError(f"Cannot count distinct {distinct}")
    threshold = {"count": count, "windowSeconds": minutes * 60, "groupBy": q["countBy"] or "agentId",
                 **({"distinct": distinct} if distinct else {})}
    alert_now = bool(body.get("alertNow"))
    rule = {"id": f"hunt-rule-{uuid.uuid4().hex[:10]}", "name": str(body.get("name") or hunt["name"]).strip()[:120],
            "description": f"Made from the saved hunt \"{hunt['name']}\".", "severity": severity, "enabled": True,
            "logSource": log_source, "logic": {"match": match, "threshold": threshold},
            "mode": "alert" if alert_now else "record",
            "alertAfter": None if alert_now else (now + timedelta(days=RECORD_DAYS)).isoformat(),
            "mitre_technique": str(body.get("technique") or "").strip()[:80], "tenant_id": _tenant(scope),
            "created_by": who, "created_at": now.isoformat(), "match_count": 0, "huntId": hunt_id}
    raw = getattr(db, "_db", db)  # siem_rules keep their own tenant field (tenant_id)
    await raw.siem_rules.insert_one(dict(rule))
    await db.soc_hunts.update_one({"id": hunt_id, "tenantId": _tenant(scope)}, {"$set": {"ruleId": rule["id"]}})
    return rule


async def ensure_indexes(db) -> None:
    raw = getattr(db, "_db", db)
    await raw.soc_hunts.create_index("id", unique=True, name="soc_hunt_id")
    await raw.soc_hunts.create_index([("tenantId", 1), ("updatedAt", -1)], name="soc_hunt_recent")
    await raw.logs.create_index([("tenantId", 1), ("timestamp", -1)], name="logs_tenant_time")
