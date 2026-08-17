"""ITAM Reporting Service aggregator (Phase 72, ITAM-REP-02/03).

Shared contract every later Phase 72 plan plugs into — mirrors
compliance_reporting_service.py's aggregator role for the ITAM surface.

This module owns:
  - build_report_rows(...) — the single row-shape source of truth all three
    renderers (csv now, pdf/xlsx in later plans) read (D-12/D-20).
  - RENDERERS — a format-name -> renderer-callable registry. Export routes
    validate the requested format against this dict at call time, never
    against a hardcoded literal tuple, so registering a renderer is what
    activates a format.
  - _generate_csv — the tracer's one renderer.
  - _store_report_meta / ItamReportingService — persistence + orchestration,
    matching compliance_reporting_service.ComplianceReportingService's shape.

Deliberately imports no FastAPI symbol — matches the service/endpoint split
used by itam_finance_service.py, so this module stays unit-testable without
a running app.
"""

import csv
import io
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from compliance_reporting_data import _sanitize_cell
from database import get_database

logger = logging.getLogger(__name__)

# Cloned from compliance_report_endpoints.py's own _REPORTS_DIR/_ensure_reports_dir
# pair — both compliance and ITAM report families write into the same
# top-level static/reports directory tree, keyed apart only by filename
# prefix (itam_report_* vs compliance_report_*).
_REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "reports")


def _ensure_reports_dir() -> None:
    os.makedirs(_REPORTS_DIR, exist_ok=True)


# Hard ceiling on rows a single report run/export will ever hold in memory or
# write to a file. `truncated` is only ever set True when this ceiling is
# actually hit — rows are never silently dropped without that flag being set
# (ITAM-REP-03 prohibition; see PLAN.md's must_haves.prohibitions).
MAX_REPORT_ROWS = 10000


async def build_report_rows(
    db,
    kind: str,
    key: str,
    tenant_id: Optional[str],
    definition: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """The single source of truth for report row shape (D-12/D-20).

    `kind="prebuilt"` dispatches to itam_reporting_prebuilt.run_prebuilt_report.
    `kind="custom"` (Plan 72-03, ITAM-REP-01) dispatches to
    itam_reporting_filters.run_custom_report, so preview and export share the
    exact same code path pre-built reports use (D-12/D-20). Any other kind
    raises ValueError.

    Returns {key, title, columns, rows, rowCount, truncated}. `rows` is a
    list of plain dicts keyed by display header; `columns` is
    list(rows[0].keys()) when rows exist, else the report's declared header
    list (so a zero-row preview/export still has real column headers).
    """
    if kind not in ("prebuilt", "custom"):
        raise ValueError(f"Unsupported report kind: {kind!r}")

    if kind == "custom":
        # Lazy import mirrors the prebuilt branch below — neither module
        # imports the other at module-load time, so there is no import cycle
        # regardless of which one is imported first.
        from itam_reporting_filters import run_custom_report

        custom_result = await run_custom_report(db, definition, tenant_id, limit=limit)
        custom_rows = custom_result["rows"]
        custom_columns = list(custom_rows[0].keys()) if custom_rows else custom_result["columns"]
        return {
            "key": custom_result["key"],
            "title": custom_result["title"],
            "columns": custom_columns,
            "rows": custom_rows,
            "rowCount": custom_result["rowCount"],
            "truncated": custom_result["truncated"],
        }

    # Lazy import: itam_reporting_prebuilt.run_prebuilt_report reads
    # MAX_REPORT_ROWS back from this module via its own lazy import — neither
    # module imports the other at module-load time, so there is no import
    # cycle regardless of which one is imported first.
    from itam_reporting_prebuilt import run_prebuilt_report

    result = await run_prebuilt_report(db, key, tenant_id, limit=limit)
    rows = result["rows"]
    columns = list(rows[0].keys()) if rows else result["columns"]
    return {
        "key": result["key"],
        "title": result["title"],
        "columns": columns,
        "rows": rows,
        "rowCount": result["rowCount"],
        "truncated": result["truncated"],
    }


# ── CSV renderer ─────────────────────────────────────────────────────────────

async def _generate_csv(report: Dict[str, Any], reports_dir: str, tenant_id: Optional[str]) -> Dict[str, Any]:
    """Writes report['rows'] to a CSV file, one column per report['columns']
    entry. Every cell passes through _sanitize_cell (CWE-1236 formula
    injection defence). A zero-row report still writes a header-only file —
    never an error (must_haves truth).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    filename = f"itam_report_{report['key']}_{timestamp}.csv"

    output = io.StringIO()
    w = csv.writer(output)
    columns = report["columns"]
    w.writerow(columns)
    for row in report["rows"]:
        w.writerow([_sanitize_cell(row.get(col)) for col in columns])
    if report.get("truncated"):
        w.writerow([f"TRUNCATED at {MAX_REPORT_ROWS} rows"])

    with open(os.path.join(reports_dir, filename), "w", newline="", encoding="utf-8") as f:
        f.write(output.getvalue())

    return {
        "filename": filename,
        "url": f"/static/reports/{filename}",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "rowCount": report["rowCount"],
        "truncated": report.get("truncated", False),
    }


# Format-name -> renderer-callable registry. Export routes validate the
# requested format against RENDERERS at call time, never a hardcoded
# literal tuple — registering a renderer here is what activates a format.
# itam_reporting_pdf/itam_reporting_excel only import compliance_reporting_
# data/compliance_reporting_excel (never this module), so importing them
# here at module scope carries no circular-import risk.
from itam_reporting_pdf import _generate_pdf
from itam_reporting_excel import _generate_excel

RENDERERS: Dict[str, Callable] = {
    "csv": _generate_csv,
    "pdf": _generate_pdf,
    "xlsx": _generate_excel,
}


# ── Report metadata persistence (enables tenant ownership check on download) ──

async def _store_report_meta(
    filename: str,
    tenant_id: Optional[str],
    kind: str,
    key: str,
    fmt: str,
    row_count: int,
    username: Optional[str],
) -> None:
    db = get_database()
    await db.itam_report_exports.update_one(
        {"filename": filename},
        {"$set": {
            "filename": filename,
            "tenantId": tenant_id,
            "kind": kind,
            "reportKey": key,
            "format": fmt,
            "rowCount": row_count,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "generatedBy": username,
        }},
        upsert=True,
    )


# ── Service class ──────────────────────────────────────────────────────────────

class ItamReportingService:
    def __init__(self):
        self.reports_dir = _REPORTS_DIR
        os.makedirs(self.reports_dir, exist_ok=True)

    async def generate(
        self,
        kind: str,
        key: str,
        fmt: str,
        tenant_id: Optional[str],
        username: Optional[str],
        definition: Optional[Dict[str, Any]] = None,
        db=None,
    ) -> Dict[str, Any]:
        report = await build_report_rows(db, kind, key, tenant_id, definition=definition, limit=None)
        renderer = RENDERERS.get(fmt)
        if renderer is None:
            raise ValueError(f"Unregistered export format: {fmt!r}")
        result = await renderer(report, self.reports_dir, tenant_id)
        await _store_report_meta(
            result["filename"], tenant_id, kind, key, fmt, result["rowCount"], username,
        )
        return result


itam_reporting_service = ItamReportingService()
