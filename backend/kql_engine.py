"""Run a parsed KQL query (kql_parser) as a MongoDB aggregation over the real hunting data.

Tables are views over the collections the SOC Hunting tab reads (soc_hunt.SOURCES): SIEM events (soc_log_events),
SOC alerts (security_alerts) and agent logs (logs). A column is a fixed alias of a stored field, so a query can only
reach fields listed here. The pipeline always starts with the caller's tenant, the table's own filter and the
time range, and runs under a time limit and a row cap.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo.errors import ExecutionTimeout, OperationFailure

from kql_parser import KqlError, parse
from soc_alerts import HIDDEN

MAX_MS, MAX_ROWS, MAX_HOURS, SET_CAP = 15000, 1000, 2160, 25

# column kinds: s = text, i = whole number, t = time; first name is the one results show
_EVENT_COLS = [
    (("TimeGenerated", "Timestamp"), "at", "t"), (("Source", "LogSource"), "source", "s"),
    (("Action",), "action", "s"), (("Outcome",), "outcome", "s"),
    (("Account", "User", "TargetUserName", "UserPrincipalName"), "user", "s"),
    (("SourceIP", "IpAddress", "SrcIp"), "srcIp", "s"), (("DestinationIP", "DestIp"), "destIp", "s"),
    (("SourcePort",), "srcPort", "i"), (("DestinationPort", "DestPort"), "destPort", "i"),
    (("Protocol", "Proto"), "proto", "s"), (("Computer", "Host", "DeviceName"), "host", "s"),
    (("Process", "ProcessName"), "process", "s"), (("EventID", "EventId"), "eventId", "i"),
    (("LogonType",), "logonType", "s"), (("Group", "TargetGroup"), "group", "s"),
    (("CommandLine", "Command"), "command", "s"), (("AgentId",), "agentId", "s"),
    (("Signature", "AlertName"), "signature", "s"), (("SignatureId",), "signatureId", "i"),
    (("Category",), "category", "s"), (("IdsSeverity",), "idsSeverity", "i"),
    (("Technique",), "technique", "s"), (("Message",), "message", "s"),
]
_ALERT_COLS = [
    (("TimeGenerated", "Timestamp"), "created_at", "t"), (("Title", "AlertName"), "title", "s"),
    (("Severity",), "severity", "s"), (("Status",), "status", "s"), (("Type", "Detection"), "type", "s"),
    (("AgentId",), "agent_id", "s"), (("Process", "ProcessName"), "process", "s"), (("Exe",), "exe", "s"),
    (("Account", "User"), "metadata.user", "s"), (("RemoteIP",), "metadata.remote_ip", "s"),
    (("Description",), "description", "s"), (("AlertId", "Id"), "id", "s"),
]
_LOG_COLS = [
    (("TimeGenerated", "Timestamp"), "timestamp", "t"), (("Service", "Facility"), "service", "s"),
    (("Level", "Severity", "SeverityLevel"), "severity", "s"), (("AgentId",), "agentId", "s"),
    (("Message", "SyslogMessage"), "message", "s"),
]
_LOGIN_ACTIONS = ["login_failed", "login_success"]

# table -> collection, whether its time field is an ISO string, its columns, its own filter, a description
TABLES: Dict[str, Dict[str, Any]] = {
    "SocEvents": {"coll": "soc_log_events", "iso": False, "cols": _EVENT_COLS, "filter": {},
                  "about": "Every SIEM event: Windows Security log, Linux auth, IDS, identity and cloud logs"},
    "SecurityEvent": {"coll": "soc_log_events", "iso": False, "cols": _EVENT_COLS,
                      "filter": {"source": "windows_security"}, "about": "Windows Security and service-install events"},
    "SigninLogs": {"coll": "soc_log_events", "iso": False, "cols": _EVENT_COLS,
                   "filter": {"action": {"$in": _LOGIN_ACTIONS}}, "about": "Sign-ins from every log source"},
    "Syslog": {"coll": "soc_log_events", "iso": False, "cols": _EVENT_COLS, "filter": {"source": "linux_auth"},
               "about": "Linux auth.log: SSH, sudo and account events"},
    "IdsAlerts": {"coll": "soc_log_events", "iso": False, "cols": _EVENT_COLS, "filter": {"source": "network"},
                  "about": "Suricata network intrusion alerts"},
    "SecurityAlert": {"coll": "security_alerts", "iso": True, "cols": _ALERT_COLS,
                      "filter": {"status": {"$nin": list(HIDDEN)}}, "about": "SOC alerts"},
    "AgentLogs": {"coll": "logs", "iso": True, "cols": _LOG_COLS, "filter": {}, "about": "Logs shipped by agents"},
}
_TENANT_COL = (("TenantId",), "tenantId", "s")


class _Col:
    def __init__(self, name: str, path: str, kind: str, iso: bool):
        self.name, self.path, self.kind, self.iso = name, path, kind, iso


def _table(name: str) -> Tuple[str, Dict[str, Any]]:
    for key, spec in TABLES.items():
        if key.lower() == name.lower():
            return key, spec
    raise KqlError(f"Unknown table {name}; use one of {', '.join(TABLES)}")


def _schema(spec: Dict[str, Any], all_tenants: bool) -> Dict[str, _Col]:
    out: Dict[str, _Col] = {}
    for names, path, kind in spec["cols"] + ([_TENANT_COL] if all_tenants else []):
        col = _Col(names[0], path, kind, spec["iso"] and kind == "t")
        for n in names:
            out[n.lower()] = col
    return out


def _lookup(schema: Dict[str, _Col], name: str) -> _Col:
    col = schema.get(name.lower())
    if col is None:
        known = sorted({c.name for c in schema.values()})
        raise KqlError(f"Unknown column {name}; columns here: {', '.join(known)}")
    return col


# -- where ------------------------------------------------------------------------------------------------------

def _scalar(col: _Col, val: Tuple[str, Any]) -> Any:
    kind, v = val
    if col.kind == "t":
        if kind == "str":
            try:
                v = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                raise KqlError(f"{col.name} compares with a time, such as ago(1h) or datetime(\"2026-11-19\")")
            v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        elif kind != "time":
            raise KqlError(f"{col.name} compares with a time, such as ago(1h) or datetime(\"2026-11-19\")")
        return v.isoformat() if col.iso else v
    if kind == "time":
        raise KqlError(f"{col.name} is not a time column")
    if col.kind == "i":
        try:
            return int(v)
        except (TypeError, ValueError):
            raise KqlError(f"{col.name} takes a whole number")
    return v


def _equal_values(col: _Col, val: Tuple[str, Any]) -> List[Any]:
    """A number typed for a text column matches the number and its text, since logs store both."""
    v = _scalar(col, val)
    if col.kind == "s" and val[0] == "num":
        return [v, str(v)]
    return [v]


def _rx(col: _Col, pattern: str, ci: bool) -> Dict[str, Any]:
    if col.kind != "s":
        raise KqlError(f"{col.name} is not text; use ==, !=, in, <, >")
    return {col.path: {"$regex": pattern, "$options": "i" if ci else ""}}


def _cmp(col: _Col, op: str, val: Tuple[str, Any]) -> Dict[str, Any]:
    neg = op.startswith("!") and op not in ("!=", "!~")
    base = op.lstrip("!") if neg else op
    if base in ("==", "!="):
        vals = _equal_values(col, val)
        cond = {col.path: vals[0]} if len(vals) == 1 else {col.path: {"$in": vals}}
        return {"$nor": [cond]} if base == "!=" else cond
    if base in ("<", "<=", ">", ">="):
        if val[0] == "str" and col.kind != "t":
            raise KqlError(f"{op} compares numbers or times")
        mop = {"<": "$lt", "<=": "$lte", ">": "$gt", ">=": "$gte"}[base]
        return {col.path: {mop: _scalar(col, val)}}
    if base in ("in", "in~"):
        items = [x for item in val[1] for x in _equal_values(col, item)]
        if base == "in~":
            if col.kind != "s":
                raise KqlError(f"{col.name} is not text; use in")
            items = [re.compile(f"^{re.escape(str(x))}$", re.I) for x in items]
        cond = {col.path: {"$in": items}}
        return {"$nor": [cond]} if neg else cond
    if val[0] != "str":
        raise KqlError(f"{op} takes quoted text")
    text = val[1]
    if base in ("=~", "!~"):
        cond = _rx(col, f"^{re.escape(text)}$", True)
        return {"$nor": [cond]} if base == "!~" else cond
    if base == "matches":
        if len(text) > 200:
            raise KqlError("A pattern can be at most 200 characters")
        try:
            re.compile(text)
        except re.error as e:
            raise KqlError(f"The pattern is not valid: {e}")
        return _rx(col, text, False)
    cs = base.endswith("_cs")
    word = base[:-3] if cs else base
    esc = re.escape(text)
    pattern = {"contains": esc, "has": rf"\b{esc}\b", "startswith": f"^{esc}", "endswith": f"{esc}$"}[word]
    cond = _rx(col, pattern, not cs)
    return {"$nor": [cond]} if neg else cond


def _match(expr: Any, schema: Dict[str, _Col]) -> Dict[str, Any]:
    tag = expr[0]
    if tag in ("and", "or"):
        return {f"${tag}": [_match(e, schema) for e in expr[1]]}
    if tag == "not":
        return {"$nor": [_match(expr[1], schema)]}
    if tag == "fn":
        col = _lookup(schema, expr[2])
        return {col.path: {"$in" if expr[1] == "isempty" else "$nin": [None, ""]}}
    _, name, op, val = expr
    return _cmp(_lookup(schema, name), op, val)


# -- reshaping stages ---------------------------------------------------------------------------------------------

def _out(name: str, kind: str) -> _Col:
    return _Col(name, name, kind, False)


def _bin(col: _Col, span: timedelta) -> Dict[str, Any]:
    if col.kind != "t":
        raise KqlError(f"bin() needs a time column, not {col.name}")
    secs = int(span.total_seconds())
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1)):
        if secs >= size and secs % size == 0:
            date = {"$dateFromString": {"dateString": f"${col.path}", "onError": None}} if col.iso else f"${col.path}"
            return {"$dateTrunc": {"date": date, "unit": unit, "binSize": secs // size}}
    raise KqlError("bin() takes a span of whole seconds")


def _summarize(stage: dict, schema: Dict[str, _Col]) -> Tuple[List[dict], Dict[str, _Col]]:
    keys, out_schema, flat = {}, {}, {"_id": 0}
    for alias, how, name, span in stage["by"]:
        col = _lookup(schema, name)
        out_name = col.name if alias == name and how == "col" else alias
        if how == "bin":
            out_name = col.name
        keys[out_name] = _bin(col, span) if how == "bin" else f"${col.path}"
        out_schema[out_name.lower()] = _out(out_name, col.kind)
        flat[out_name] = f"$_id.{out_name}"
    group: Dict[str, Any] = {"_id": keys or None}
    for alias, fn, name in stage["aggs"]:
        col = _lookup(schema, name) if name else None
        out_name = alias or (f"{fn}_" if col is None else f"{fn}_{col.name}")
        if out_name.lower() in out_schema:
            raise KqlError(f"Column {out_name} is named twice")
        src = f"${col.path}" if col else None
        if fn == "count":
            group[out_name], flat[out_name] = {"$sum": 1}, 1
        elif fn in ("dcount", "make_set"):
            group[out_name] = {"$addToSet": src}
            flat[out_name] = {"$size": f"${out_name}"} if fn == "dcount" else {"$slice": [f"${out_name}", SET_CAP]}
        else:
            group[out_name], flat[out_name] = {f"${fn}": src}, 1
        out_schema[out_name.lower()] = _out(out_name, "i" if fn in ("count", "dcount") else
                                            ("s" if fn == "make_set" else col.kind if fn in ("min", "max") else "n"))
    return [{"$group": group}, {"$project": flat}], out_schema


def _project(cols: List[Tuple[str, str]], schema: Dict[str, _Col]) -> Tuple[dict, Dict[str, _Col]]:
    proj, out = {"_id": 0}, {}
    for alias, name in cols:
        col = _lookup(schema, name)
        out_name = col.name if alias == name else alias
        if out_name.lower() in out:
            raise KqlError(f"Column {out_name} is named twice")
        proj[out_name] = f"${col.path}"
        out[out_name.lower()] = _out(out_name, col.kind)
    return {"$project": proj}, out


def build(table_name: str, stages: List[dict], scope: Optional[str], since: datetime,
          limit: int) -> Tuple[str, str, List[dict]]:
    """The table, its collection and the pipeline: scope, table filter and time range first, then the stages."""
    table, spec = _table(table_name)
    schema = _schema(spec, scope is None)
    time_path = spec["cols"][0][1]
    first = {**({"tenantId": scope} if scope else {}), **spec["filter"],
             time_path: {"$gte": since.isoformat() if spec["iso"] else since}}
    pipeline: List[dict] = [{"$match": first}]
    shaped = False
    for st in stages:
        op = st["op"]
        if op == "where":
            pipeline.append({"$match": _match(st["expr"], schema)})
        elif op == "project":
            proj, schema = _project(st["cols"], schema)
            pipeline.append(proj)
            shaped = True
        elif op == "summarize":
            more, schema = _summarize(st, schema)
            pipeline += more
            shaped = True
        elif op == "distinct":
            more, schema = _summarize({"aggs": [], "by": [(a, "col", n, None) for a, n in st["cols"]]}, schema)
            pipeline += more
            shaped = True
        elif op == "count":
            pipeline.append({"$count": "Count"})
            schema, shaped = {"count": _out("Count", "i")}, True
        elif op in ("sort", "top"):
            pipeline.append({"$sort": {_lookup(schema, c).path: -1 if d else 1 for c, d in st["keys"]}})
            if op == "top":
                pipeline.append({"$limit": st["n"]})
        elif op == "take":
            pipeline.append({"$limit": st["n"]})
    if not shaped:
        pipeline.insert(1, {"$sort": {time_path: -1}})
        seen, proj = set(), {"_id": 0}
        for col in schema.values():
            if col.name not in seen:
                seen.add(col.name)
                proj[col.name] = f"${col.path}"
        pipeline.append({"$project": proj})
    pipeline.append({"$limit": limit})
    return table, spec["coll"], pipeline


def _plain(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.replace(tzinfo=v.tzinfo or timezone.utc).isoformat()
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


async def run(db, scope: Optional[str], query: str, hours: int = 24, limit: int = 100,
              now: Optional[datetime] = None) -> Dict[str, Any]:
    """Parse, build and run a query in the caller's scope (None = a Super Admin's all-tenant view)."""
    now = now or datetime.now(timezone.utc)
    hours, limit = max(1, min(int(hours), MAX_HOURS)), max(1, min(int(limit), MAX_ROWS))
    table_name, stages = parse(query, now)
    table, coll, pipeline = build(table_name, stages, scope, now - timedelta(hours=hours), limit)
    started = datetime.now(timezone.utc)
    try:
        docs = await getattr(db, coll).aggregate(pipeline, maxTimeMS=MAX_MS).to_list(limit)
    except ExecutionTimeout:
        raise KqlError(f"The query ran longer than {MAX_MS // 1000} seconds; narrow the time range or add a where")
    except OperationFailure as e:
        raise KqlError(f"The database refused this query: {e.details.get('errmsg') if e.details else e}")
    rows = [{k: _plain(v) for k, v in d.items()} for d in docs]
    if not rows and stages and stages[-1]["op"] == "count":
        rows = [{"Count": 0}]
    columns: List[str] = []
    for r in rows:
        columns += [k for k in r if k not in columns]
    return {"table": table, "results": rows, "columns": columns, "total": len(rows), "truncated": len(rows) >= limit,
            "elapsed_ms": int((datetime.now(timezone.utc) - started).total_seconds() * 1000)}
