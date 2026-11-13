"""The activity export builder (Phase 86, ACTV-06, D-09, D-10, D-11).

One builder for both entry points (the Reporting screen and the Activity header): it reads exactly the rows the
Activity list shows for a state (``views.activity_filter``, presented by ``views.present_row``), limited to the
last 7, 30 or 90 days or all time, newest first, at most ``EXPORT_ROW_CAP`` rows. When more match, the newest
rows are kept and the file says so (``cap_sentence``). Zero rows gives no file (``content`` None).

Every text cell of the CSV passes through ``sanitize_csv_cell`` so a target, host or rule id that starts with a
formula character cannot run in a spreadsheet. The PDF is built by ``export_pdf`` (its own escaping).

Read only; the raw handle and an explicit tenantId are used and the ambient tenant context is never read.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from autonomous_ops import ledger, views
from autonomous_ops.scope import raw
from itam_data_service import sanitize_csv_cell

from . import EXPORT_ROW_CAP, stats
from .rule_names import rule_name

CSV_HEADER = ("When (UTC)", "State", "Action", "Target", "Host", "Rule", "Rule id", "Approved by", "Result")
STATE_WORDS = {"pending": "Pending", "done": "Done", "undone": "Undone", "failed": "Failed", "refused": "Refused",
               "suggested": "Suggested", "simulation": "Simulation", "control": "Control"}
PERIODS = ("7", "30", "90", "all")
MEDIA_TYPES = {"csv": "text/csv", "pdf": "application/pdf"}
PERIOD_WORDS = {"7": "Last 7 days", "30": "Last 30 days", "90": "Last 90 days", "all": "All time"}


@dataclass
class ExportResult:
    content: Optional[bytes]
    filename: str
    media_type: str
    shown: int
    total: int
    truncated: bool
    rows: List[List[str]] = field(default_factory=list)


def cap_sentence(shown: int, total: int) -> str:
    return (f"the newest {shown:,} of {total:,} rows. Rows older than that were left out. "
            "Pick a shorter period or a single state to get the rest.")


def file_name(tenant_id: str, fmt: str, now: datetime) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", str(tenant_id))
    return f"autonomous-ops-activity-{safe}-{now.strftime('%Y%m%d')}.{fmt}"


def _when(value: Any) -> str:
    if not isinstance(value, datetime):
        return ""
    value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _approver(doc: Dict[str, Any], viewer_is_platform_staff: bool) -> str:
    """Who approved, as this viewer may see it (D-25): platform staff read as "Platform administrator" to a tenant."""
    approver = (doc.get("approval") or {}).get("approver")
    if doc.get("kind") == "control" or not isinstance(approver, dict):
        return ""
    scope = "platform" if approver.get("tier") == "platform" else "tenant"
    return views.display_actor(approver, scope, viewer_is_platform_staff)


def table_row(doc: Dict[str, Any], shown: Dict[str, Any], viewer_is_platform_staff: bool) -> List[str]:
    """One export row (the nine CSV columns, unsanitized) from a ledger document and its Activity-list form."""
    rule_id = shown.get("ruleId") or ""
    return [_when(doc.get("createdAt")), STATE_WORDS.get(shown["bucket"], ""), shown.get("actionLabel") or "",
            shown.get("target") or "", shown.get("host") or "", rule_name(rule_id) if rule_id else "", rule_id,
            _approver(doc, viewer_is_platform_staff), shown.get("resultText") or ""]


def csv_bytes(rows: List[List[str]], total: int, truncated: bool) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow([sanitize_csv_cell(cell) for cell in row])
    if truncated:
        writer.writerow(["Note", cap_sentence(len(rows), total)])
    return out.getvalue().encode("utf-8")


async def build(db, tenant_id: str, *, bucket: str, days: str, fmt: str, viewer_is_platform_staff: bool,
                now: Optional[datetime] = None) -> ExportResult:
    """The export for one tenant, one Activity bucket and one period (``days``: "7", "30", "90" or "all")."""
    if days not in PERIODS or fmt not in MEDIA_TYPES:
        raise ValueError("unknown period or format")
    now = now or datetime.now(timezone.utc)
    flt = views.activity_filter(tenant_id, bucket)
    if days != "all":
        flt = {"$and": [flt, {"createdAt": {"$gte": now - timedelta(days=int(days))}}]}
    ledger_rows = raw(db).autonomy_actions
    total = await ledger_rows.count_documents(flt)
    name, media_type = file_name(tenant_id, fmt, now), MEDIA_TYPES[fmt]
    if total == 0:
        return ExportResult(None, name, media_type, 0, 0, False)
    found = ledger_rows.find(flt, {"_id": 0}).sort([("createdAt", -1), ("id", -1)]).limit(EXPORT_ROW_CAP)
    docs = [ledger._normalize(doc) async for doc in found]
    hosts = await views._host_names(db, tenant_id, docs)
    rows = [table_row(doc, views.present_row(doc, viewer_is_platform_staff=viewer_is_platform_staff, now=now,
                                             host=hosts.get(str(doc["targets"][0])) if doc.get("targets") else None),
                      viewer_is_platform_staff) for doc in docs]
    truncated = total > len(rows)
    if fmt == "pdf":
        content = await _pdf_bytes(db, tenant_id, bucket=bucket, days=days, now=now, rows=rows,
                                   cap_note=cap_sentence(len(rows), total) if truncated else None)
    else:
        content = csv_bytes(rows, total, truncated)
    return ExportResult(content, name, media_type, len(rows), total, truncated, rows)


async def _pdf_bytes(db, tenant_id: str, *, bucket: str, days: str, now: datetime, rows: List[List[str]],
                     cap_note: Optional[str]) -> bytes:
    """The PDF: the summary page uses the statistics of the same window (stats.compute, fold, time_saved)."""
    from . import export_pdf
    groups = await stats.compute(db, tenant_id, days=None if days == "all" else int(days), now=now)
    folded = stats.fold(groups)
    tenant = await raw(db).tenants.find_one({"id": tenant_id}, {"_id": 0, "name": 1}) or {}
    state = "All" if bucket == "all" else STATE_WORDS[bucket]
    return export_pdf.render_pdf(
        organization=tenant.get("name") or tenant_id, generated_at=now,
        filter_line=f"Activity: {state}. Period: {PERIOD_WORDS[days]}. Newest first, up to {EXPORT_ROW_CAP:,} rows.",
        summary=folded["totals"], rules=folded["rules"], time_saved=stats.time_saved(groups), rows=rows,
        cap_note=cap_note)
