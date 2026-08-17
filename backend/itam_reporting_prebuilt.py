"""ITAM pre-built report registry (Phase 72, D-08/D-09).

One report today: warranty_expiring. Later plans (72-02) add the remaining
five entries to PREBUILT_REPORTS without touching this module's public
shape (list_prebuilt_reports/run_prebuilt_report) — every future pre-built
report is a new PREBUILT_REPORTS entry plus a new `builder` callable, not a
new dispatch path.

Deliberately imports no FastAPI symbol, matching itam_reporting_service.py's
own no-FastAPI-import convention — this module is unit-testable without a
running app.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from itam_finance_service import (
    WARRANTY_STATUS_EXPIRING,
    compute_warranty_status,
    get_warranty_alert_window,
)

_EM_DASH = "—"

# Declared display headers — used both as the emitted row key order and, per
# build_report_rows's own fallback rule, as the header list a zero-row run
# still returns (so an empty preview/export always has real column headers).
_WARRANTY_EXPIRING_COLUMNS = [
    "Asset Tag", "Name", "Lifecycle Status", "Warranty Expires", "Days To Expiry", "Status",
]


def _dash(value: Any) -> Any:
    """Renders a None field as an em dash rather than a blank cell or the
    literal string 'undefined' (must_haves partial-state truth)."""
    return value if value is not None else _EM_DASH


async def _build_warranty_expiring_rows(db, tenant_id: Optional[str]) -> List[Dict[str, Any]]:
    """Reads db.assets through the tenant-isolated handle, resolves the
    tenant's alert window once, and reuses
    itam_finance_service.compute_warranty_status verbatim per asset — this
    report never re-derives expiry or the alert-window threshold itself
    (Phase 71 boundary-logic reuse, must_haves truth). Rows are sorted
    ascending by warrantyExpiresAt so the preview and the exported file
    always agree on order.
    """
    now = datetime.now(timezone.utc)
    window_days = await get_warranty_alert_window(db, tenant_id)

    assets = await db.assets.find(
        {},
        {
            "_id": 0, "id": 1, "assetTag": 1, "name": 1, "lifecycleStatus": 1,
            "purchaseDate": 1, "warrantyMonths": 1,
        },
    ).to_list(length=None)

    expiring_rows = []
    for asset in assets:
        status_result = compute_warranty_status(
            asset.get("purchaseDate"), asset.get("warrantyMonths"), now, window_days,
        )
        if status_result["warrantyStatus"] != WARRANTY_STATUS_EXPIRING:
            continue
        expiring_rows.append({
            "_sortKey": status_result["warrantyExpiresAt"],
            "Asset Tag": _dash(asset.get("assetTag")),
            "Name": _dash(asset.get("name")),
            "Lifecycle Status": _dash(asset.get("lifecycleStatus")),
            "Warranty Expires": _dash(status_result["warrantyExpiresAt"]),
            "Days To Expiry": _dash(status_result["daysToExpiry"]),
            "Status": status_result["warrantyStatus"],
        })

    expiring_rows.sort(key=lambda r: r["_sortKey"])
    for row in expiring_rows:
        row.pop("_sortKey", None)
    return expiring_rows


# Keyed by report key. Each value carries key/title/description/columns
# (declared display headers)/defaultSort (human-readable order description)
# and `builder` (the async row-building callable) — list_prebuilt_reports
# strips `builder` before returning metadata to the Reports tab.
PREBUILT_REPORTS: Dict[str, Dict[str, Any]] = {
    "warranty_expiring": {
        "key": "warranty_expiring",
        "title": "Warranty Expiring",
        "description": "Assets whose warranty falls inside the tenant's alert window.",
        "columns": _WARRANTY_EXPIRING_COLUMNS,
        "defaultSort": "Ascending by warranty expiry date",
        "builder": _build_warranty_expiring_rows,
    },
}


def list_prebuilt_reports() -> List[Dict[str, Any]]:
    """Registry metadata without the `builder` callable — the shape the
    Reports tab's pre-built section renders."""
    return [
        {k: v for k, v in report.items() if k != "builder"}
        for report in PREBUILT_REPORTS.values()
    ]


async def run_prebuilt_report(
    db, key: str, tenant_id: Optional[str], limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Raises ValueError on an unknown key. Applies the MAX_REPORT_ROWS
    ceiling (imported lazily from itam_reporting_service to avoid a
    module-import cycle — neither module imports the other at module-load
    time) and returns the {key,title,columns,rows,rowCount,truncated} dict
    build_report_rows re-emits."""
    report_def = PREBUILT_REPORTS.get(key)
    if report_def is None:
        raise ValueError(f"Unknown pre-built report key: {key!r}")

    from itam_reporting_service import MAX_REPORT_ROWS

    rows = await report_def["builder"](db, tenant_id)
    truncated = len(rows) > MAX_REPORT_ROWS
    if truncated:
        rows = rows[:MAX_REPORT_ROWS]
    if limit is not None:
        rows = rows[:limit]

    columns = list(rows[0].keys()) if rows else report_def["columns"]

    return {
        "key": report_def["key"],
        "title": report_def["title"],
        "columns": columns,
        "rows": rows,
        "rowCount": len(rows),
        "truncated": truncated,
    }
