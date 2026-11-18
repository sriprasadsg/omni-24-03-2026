"""Investigation graph for a SOC incident or alert: the endpoint, its alerts, what those alerts name (user,
process, file, public IP, MITRE technique), and the tenant's other endpoints where the same file, IP, user
or process showed up in alerts of the last 7 days.

Built when asked from the stored alerts; nothing is stored. Node ids are stable strings ("host:<agent>",
"alert:<id>", "user:<name>", ...) so the console keeps a selection across refreshes. An alert's graph is
its incident's graph with that alert marked (``focus``). Bounded: at most MAX_ALERTS alerts, MAX_OTHER_HOSTS
other endpoints per entity and MAX_NODES nodes; ``truncated`` says when something was left out.
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from soc_alerts import SEVERITIES
from soc_service import parse_ts, scope_filter, technique_name, techniques_of, view

MAX_ALERTS = 40
MAX_NODES = 90
MAX_OTHER_HOSTS = 5
PIVOT_DAYS = 7
PIVOT_ROWS = 5000
RANK = {s: i for i, s in enumerate(SEVERITIES)}
PROCESS_IN_TEXT = re.compile(r"[Pp]rocess '([^']{1,200})'")
EDGE_LABEL = {"user": "user", "process": "process", "file": "file", "ip": "connected to", "technique": "technique"}
KIND_ORDER = ("user", "process", "file", "ip", "technique")


class GraphError(ValueError):
    def __init__(self, message: str, status: int = 404):
        super().__init__(message)
        self.status = status


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1] or path


def entities(doc: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """(kind, key, label) for what one stored alert names; the key is what other alerts must match."""
    import soc_response
    ev = soc_response.evidence(doc)
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    out: List[Tuple[str, str, str]] = []
    user = soc_response._first(doc, "user", "username", "user_id")
    if user:
        out.append(("user", str(user).strip().lower(), str(user).strip()))
    process = soc_response._first(doc, "process", "process_name")
    if not process:
        found = PROCESS_IN_TEXT.search(f"{doc.get('description') or ''} {meta.get('description') or ''}")
        process = found.group(1) if found else (_basename(str(ev["exe"])) if ev.get("exe") else None)
    if process:
        out.append(("process", str(process).strip().lower(), str(process).strip()))
    if ev.get("sha256") or ev.get("path"):
        # A watched file is the same file by its path (its checksum changes); anything else by its content.
        by_path = ev.get("path") and (doc.get("type") == "fim_violation" or not ev.get("sha256"))
        key = str(ev["path"]).lower() if by_path else ev["sha256"]
        out.append(("file", key, _basename(str(ev["path"])) if ev.get("path") else f"{ev['sha256'][:12]}…"))
    if ev.get("ip"):
        out.append(("ip", ev["ip"], ev["ip"]))
    for t in techniques_of(doc):
        out.append(("technique", t, f"{t} {technique_name(t)[0]}".strip() if technique_name(t)[0] != t else t))
    return out


def _file_detail(doc: Dict[str, Any]) -> Optional[str]:
    import soc_response
    ev = soc_response.evidence(doc)
    parts = [p for p in (ev.get("path"), f"SHA-256 {ev['sha256']}" if ev.get("sha256") else None) if p]
    return " · ".join(parts) or None


async def _pivots(db, tenant: Optional[str], agent: Optional[str], wanted: Dict[Tuple[str, str], str],
                  now: datetime) -> Dict[Tuple[str, str], Dict[str, int]]:
    """For each wanted (kind, key), the other endpoints whose recent alerts name it, with alert counts."""
    keys = {k for k in wanted if k[0] != "technique"}  # a technique on two hosts is a campaign, not a pivot
    if not keys or not tenant:  # never look across tenants
        return {}
    since = (now - timedelta(days=PIVOT_DAYS)).isoformat()
    filt = {**scope_filter(tenant), "agent_id": {"$nin": [agent, None, ""]}, "status": {"$nin": ["merged", "archived"]},
            "$or": [{"created_at": {"$gte": since}}, {"lastSeenAt": {"$gte": since}}]}
    out: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    async for d in db.security_alerts.find(filt, {"_id": 0}).limit(PIVOT_ROWS):
        for kind, key, _ in entities(d):
            if (kind, key) in keys:
                out[(kind, key)][d["agent_id"]] += 1
    return out


async def _hosts(db, ids: List[str]) -> Dict[str, str]:
    ids = sorted({i for i in ids if i})
    rows = await db.agents.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "hostname": 1}).to_list(len(ids)) if ids else []
    return {r["id"]: r.get("hostname") or r["id"] for r in rows}


async def build(db, tenant: Optional[str], agent: Optional[str], docs: List[Dict[str, Any]], focus: Optional[str] = None,
                now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    ranked = sorted(docs, key=lambda d: (d.get("id") != focus, RANK.get(view(d)["severity"], 9),
                                         -(parse_ts(d.get("created_at")) or epoch).timestamp()))
    kept = sorted(ranked[:MAX_ALERTS], key=lambda d: parse_ts(d.get("created_at")) or epoch)
    truncated = len(docs) > len(kept)
    hosts = await _hosts(db, [agent] if agent else [])
    host_id = f"host:{agent or 'none'}"
    nodes: Dict[str, Dict[str, Any]] = {host_id: {"id": host_id, "kind": "host", "label": hosts.get(agent) or agent or "No endpoint",
                                                  "agentId": agent, "primary": True}}
    edges: List[Dict[str, str]] = []
    wanted: Dict[Tuple[str, str], str] = {}
    for d in kept:
        v = view(d, hosts)
        aid = f"alert:{v['id']}"
        nodes[aid] = {"id": aid, "kind": "alert", "label": v["title"], "alertId": v["id"], "severity": v["severity"],
                      "status": v["status"], "sub": v["typeLabel"], "at": v["createdAt"], "focus": v["id"] == focus}
        edges.append({"from": host_id, "to": aid, "label": "raised"})
        for kind, key, label in entities(d):
            nid = f"{kind}:{key}"
            if nid not in nodes:
                nodes[nid] = {"id": nid, "kind": kind, "label": label, "count": 0,
                              "sub": _file_detail(d) if kind == "file" else (technique_name(key)[1] or None) if kind == "technique" else None}
                wanted[(kind, key)] = nid
            nodes[nid]["count"] += 1
            edge = {"from": aid, "to": nid, "label": EDGE_LABEL[kind]}
            if edge not in edges:
                edges.append(edge)
    pivots = await _pivots(db, tenant, agent, wanted, now)
    other_names = await _hosts(db, [a for per in pivots.values() for a in per])
    for (kind, key), per in sorted(pivots.items(), key=lambda kv: KIND_ORDER.index(kv[0][0])):
        for other, count in sorted(per.items(), key=lambda kv: -kv[1])[:MAX_OTHER_HOSTS]:
            if len(nodes) >= MAX_NODES:
                truncated = True
                break
            oid = f"host:{other}"
            nodes.setdefault(oid, {"id": oid, "kind": "host", "label": other_names.get(other) or other, "agentId": other,
                                   "primary": False, "count": 0})
            nodes[oid]["count"] += count
            edges.append({"from": wanted[(kind, key)], "to": oid, "label": f"also seen ({count} alert{'s' if count != 1 else ''})"})
        truncated = truncated or len(per) > MAX_OTHER_HOSTS
    return {"nodes": list(nodes.values()), "edges": edges, "truncated": truncated, "alerts": len(kept),
            "alertsTotal": len(docs), "pivotDays": PIVOT_DAYS, "focus": f"alert:{focus}" if focus else None}


async def incident_graph(db, scope: Optional[str], incident_id: str, focus: Optional[str] = None) -> Dict[str, Any]:
    inc = await db.soc_incidents.find_one({"id": incident_id, **scope_filter(scope)}, {"_id": 0, "id": 1, "tenantId": 1, "agentId": 1})
    if not inc:
        raise GraphError("Incident not found")
    docs = await db.security_alerts.find({"incidentId": incident_id, "tenantId": inc.get("tenantId"),
                                          "status": {"$nin": ["merged", "archived"]}}, {"_id": 0}).to_list(500)
    out = await build(db, inc.get("tenantId"), inc.get("agentId"), docs, focus)
    return {**out, "incidentId": incident_id}


async def alert_graph(db, scope: Optional[str], alert_id: str) -> Dict[str, Any]:
    """The graph of the alert's incident with the alert marked, or of the alert alone when it has none."""
    import soc_actions
    doc, _ = await soc_actions._find(db, scope, alert_id)
    if not doc:
        raise GraphError("Alert not found")
    if doc.get("incidentId"):
        try:
            return await incident_graph(db, scope, doc["incidentId"], focus=alert_id)
        except GraphError:
            pass  # the incident is gone or out of scope: fall back to the alert alone
    agent = doc.get("agent_id") or doc.get("agentId") or ((doc.get("metadata") or {}).get("agent_id") if isinstance(doc.get("metadata"), dict) else None)
    out = await build(db, doc.get("tenantId"), agent, [doc], alert_id)
    return {**out, "incidentId": None}

