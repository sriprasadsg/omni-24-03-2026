"""SOC report export: the alerts or incidents of a period as CSV, for audits and weekly reports.

Cells that a spreadsheet would run as a formula (starting with = + - @, tab or carriage return) get a
leading apostrophe, so an alert title can never execute in the reader's spreadsheet.
"""
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, List, Optional

from soc_service import RANGES, scope_filter, view

MAX_ROWS = 20000
ALERT_COLUMNS = ["id", "createdAt", "lastSeenAt", "severity", "risk", "typeLabel", "title", "hostname", "agentId", "status",
                 "resolution", "assignee", "acknowledgedAt", "acknowledgedBy", "closedAt", "closedBy", "occurrences", "mitre",
                 "incidentId", "threatIntel", "slaOverdue"]
INCIDENT_COLUMNS = ["id", "startedAt", "lastAlertAt", "severity", "title", "hostname", "agentId", "alertCount", "tactics",
                    "status", "resolution", "assignee", "closedAt", "closedBy", "caseId"]


def safe(value: Any) -> str:
    if isinstance(value, list):
        value = "; ".join(str(v.get("value") if isinstance(v, dict) else v) for v in value)
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def to_csv(columns: List[str], rows: Iterable[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(columns)
    for r in rows:
        w.writerow([safe(r.get(c)) for c in columns])
    return out.getvalue()


async def export(db, scope: Optional[str], kind: str, range_key: str) -> str:
    since = (datetime.now(timezone.utc) - timedelta(seconds=RANGES[range_key][0])).isoformat()
    if kind == "incidents":
        import soc_incidents
        rows = await db.soc_incidents.find({**scope_filter(scope)}, {"_id": 0}).sort("lastAlertAt", -1).to_list(MAX_ROWS)
        rows = [r for r in rows if (r.get("lastAlertAt").isoformat() if hasattr(r.get("lastAlertAt"), "isoformat") else str(r.get("lastAlertAt"))) >= since]
        leads, hosts = await soc_incidents._leads(db, rows), await soc_incidents._hosts(db, [r.get("agentId") for r in rows])
        return to_csv(INCIDENT_COLUMNS, (soc_incidents.incident_view(r, leads.get(r["id"]), hosts.get(r.get("agentId"))) for r in rows))
    import soc_context
    docs = await db.security_alerts.find({**scope_filter(scope), "status": {"$nin": ["merged", "archived"]},
                                          "$or": [{"created_at": {"$gte": since}}, {"lastSeenAt": {"$gte": since}}]},
                                         {"_id": 0}).sort("created_at", -1).to_list(MAX_ROWS)
    hosts = {a["id"]: a.get("hostname") for a in await db.agents.find(scope_filter(scope), {"_id": 0, "id": 1, "hostname": 1}).to_list(5000)}
    views = await soc_context.annotate(db, [view(d, hosts) for d in docs])
    for v in views:
        v["slaOverdue"] = "yes" if (v.get("sla") or {}).get("ackBreached") or (v.get("sla") or {}).get("closeBreached") else ""
    return to_csv(ALERT_COLUMNS, views)
