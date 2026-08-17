"""ITAM pre-built report registry (Phase 72, D-08/D-09).

Five of the six D-08 reports live here so far: warranty_expiring (72-01,
the tracer) and asset_value/checkout_activity/overdue_audits (72-02 Task
1). Task 2 adds the remaining two (license_utilization,
low_stock_consumables). Every report is a new PREBUILT_REPORTS entry plus a
new `builder` callable — this module's public shape
(list_prebuilt_reports/run_prebuilt_report) never changes to add one.

Deliberately imports no FastAPI symbol, matching itam_reporting_service.py's
own no-FastAPI-import convention — this module is unit-testable without a
running app.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from itam_finance_service import (
    REASON_NO_DEPRECIATION_POLICY,
    WARRANTY_STATUS_EXPIRING,
    compute_book_value,
    compute_warranty_status,
    get_warranty_alert_window,
)
from itam_lifecycle_endpoints import (
    AUDIT_INTERVAL_DAYS,
    _audit_cutoff_iso,
    _overdue_query,
    _overdue_row,
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


def _cents_to_dollars(cents: Any) -> Any:
    """Renders an integer cents amount as a decimal currency string, or an
    em dash when there is no amount to render."""
    if cents is None:
        return _EM_DASH
    return f"${cents / 100:,.2f}"


_ASSET_VALUE_COLUMNS = [
    "Asset Tag", "Name", "Purchase Date", "Purchase Cost", "Book Value", "Years Elapsed", "Reason",
]


async def _build_asset_value_rows(db, tenant_id: Optional[str]) -> List[Dict[str, Any]]:
    """Reads db.assets tenant-scoped for documents carrying a purchase
    record, batch-resolves the referenced model documents through ONE
    db.asset_models query (never a per-asset lookup or an aggregation
    join), and reuses itam_finance_service.compute_book_value verbatim per
    asset with the exact same depreciation-input resolution
    itam_finance_endpoints.get_asset_book_value uses — this report never
    re-derives book value itself (must_haves truth). An asset whose model
    carries no usefulLifeYears/salvageValueCents, or whose inputs raise
    ValueError, gets an em-dash value and the endpoint's own
    REASON_NO_DEPRECIATION_POLICY string. Sorted descending by computed
    book value, with rows lacking a computable value last.
    """
    assets = await db.assets.find(
        {
            "purchaseCostCents": {"$exists": True, "$ne": None},
            "purchaseDate": {"$exists": True, "$ne": None},
        },
        {
            "_id": 0, "id": 1, "assetTag": 1, "name": 1, "modelId": 1,
            "purchaseCostCents": 1, "purchaseDate": 1,
        },
    ).to_list(length=None)

    model_ids = sorted({a["modelId"] for a in assets if a.get("modelId")})
    models_by_id: Dict[str, Dict[str, Any]] = {}
    if model_ids:
        model_docs = await db.asset_models.find(
            {"id": {"$in": model_ids}},
            {"_id": 0, "id": 1, "usefulLifeYears": 1, "salvageValueCents": 1},
        ).to_list(length=None)
        models_by_id = {m["id"]: m for m in model_docs}

    now = datetime.now(timezone.utc)
    rows: List[Dict[str, Any]] = []
    for asset in assets:
        purchase_cost = asset.get("purchaseCostCents")
        purchase_date = asset.get("purchaseDate")
        row: Dict[str, Any] = {
            "_sortKey": None,
            "Asset Tag": _dash(asset.get("assetTag")),
            "Name": _dash(asset.get("name")),
            "Purchase Date": _dash(purchase_date),
            "Purchase Cost": _cents_to_dollars(purchase_cost),
            "Book Value": _EM_DASH,
            "Years Elapsed": _EM_DASH,
            "Reason": _EM_DASH,
        }

        model_doc = models_by_id.get(asset.get("modelId"))
        if (
            not model_doc
            or model_doc.get("usefulLifeYears") is None
            or model_doc.get("salvageValueCents") is None
        ):
            row["Reason"] = REASON_NO_DEPRECIATION_POLICY
            rows.append(row)
            continue

        try:
            result = compute_book_value(
                purchase_date=purchase_date,
                purchase_cost_cents=purchase_cost,
                useful_life_years=model_doc["usefulLifeYears"],
                salvage_value_cents=model_doc["salvageValueCents"],
                now=now,
            )
        except ValueError:
            row["Reason"] = REASON_NO_DEPRECIATION_POLICY
            rows.append(row)
            continue

        row["_sortKey"] = result["bookValueCents"]
        row["Book Value"] = _cents_to_dollars(result["bookValueCents"])
        row["Years Elapsed"] = result["yearsElapsed"]
        rows.append(row)

    rows.sort(key=lambda r: (r["_sortKey"] is None, -(r["_sortKey"] if r["_sortKey"] is not None else 0)))
    for row in rows:
        row.pop("_sortKey", None)
    return rows


_CHECKOUT_ACTIVITY_COLUMNS = [
    "When", "Action", "Asset Tag", "Asset Name", "Target Type", "Target", "Actor", "Note",
]


async def _build_checkout_activity_rows(db, tenant_id: Optional[str]) -> List[Dict[str, Any]]:
    """Reads db.assignment_history tenant-scoped — a straight ledger read,
    since the collection is written only by
    itam_lifecycle_service.write_history — sorted ts descending with _id
    descending as the tiebreak, mirroring
    itam_lifecycle_service.list_history's stable ordering but fleet-wide
    instead of per-asset. Batch-resolves the referenced assetId values
    through ONE db.assets query to add the asset tag and name.
    """
    entries = await db.assignment_history.find(
        {}, {"_id": 0},
    ).sort([("ts", -1), ("_id", -1)]).to_list(length=None)

    asset_ids = sorted({e["assetId"] for e in entries if e.get("assetId")})
    assets_by_id: Dict[str, Dict[str, Any]] = {}
    if asset_ids:
        asset_docs = await db.assets.find(
            {"id": {"$in": asset_ids}},
            {"_id": 0, "id": 1, "assetTag": 1, "name": 1},
        ).to_list(length=None)
        assets_by_id = {a["id"]: a for a in asset_docs}

    rows: List[Dict[str, Any]] = []
    for entry in entries:
        asset_doc = assets_by_id.get(entry.get("assetId"))
        rows.append({
            "When": _dash(entry.get("ts")),
            "Action": _dash(entry.get("action")),
            "Asset Tag": _dash(asset_doc.get("assetTag") if asset_doc else None),
            "Asset Name": _dash(asset_doc.get("name") if asset_doc else None),
            "Target Type": _dash(entry.get("targetType")),
            "Target": _dash(entry.get("targetId")),
            "Actor": _dash(entry.get("actorUsername")),
            "Note": _dash(entry.get("note")),
        })
    return rows


_OVERDUE_AUDITS_COLUMNS = [
    "Asset Tag", "Name", "Lifecycle Status", "Last Audited", "Age Basis", "Days Overdue", "Never Audited",
]


async def _build_overdue_audits_rows(db, tenant_id: Optional[str]) -> List[Dict[str, Any]]:
    """Delegates the overdue determination entirely to
    itam_lifecycle_endpoints._overdue_query/_overdue_row — imported and
    used unchanged (must_haves truth); the only new work here is the
    display-row mapping and the export wrapper the existing JSON route
    lacks. Sorted ascending by daysOverdue, with unknown/unparseable-basis
    rows (null daysOverdue) last, matching the existing route's own
    ordering intent.
    """
    cutoff = _audit_cutoff_iso()
    now = datetime.now(timezone.utc)
    query = _overdue_query(cutoff)
    projection = {
        "_id": 0, "id": 1, "name": 1, "assetTag": 1, "lifecycleStatus": 1,
        "lastAuditedAt": 1, "lastAuditedBy": 1, "createdAt": 1,
    }
    docs = await db.assets.find(query, projection).to_list(length=None)
    overdue_rows = [_overdue_row(doc, cutoff, now) for doc in docs]
    overdue_rows.sort(
        key=lambda r: (r["daysOverdue"] is None, r["daysOverdue"] if r["daysOverdue"] is not None else 0)
    )

    rows: List[Dict[str, Any]] = []
    for row in overdue_rows:
        rows.append({
            "Asset Tag": _dash(row.get("assetTag")),
            "Name": _dash(row.get("name")),
            "Lifecycle Status": _dash(row.get("lifecycleStatus")),
            "Last Audited": _dash(row.get("lastAuditedAt")),
            "Age Basis": row.get("ageBasis"),
            "Days Overdue": _dash(row.get("daysOverdue")),
            "Never Audited": row.get("neverAudited"),
        })
    return rows


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
    "asset_value": {
        "key": "asset_value",
        "title": "Asset Value & Depreciation",
        "description": "Straight-line book value for assets with a purchase record.",
        "columns": _ASSET_VALUE_COLUMNS,
        "defaultSort": "Descending by computed book value",
        "builder": _build_asset_value_rows,
    },
    "checkout_activity": {
        "key": "checkout_activity",
        "title": "Check-Out / Check-In Activity",
        "description": "Fleet-wide check-out, check-in and audit events, newest first.",
        "columns": _CHECKOUT_ACTIVITY_COLUMNS,
        "defaultSort": "Descending by event timestamp",
        "builder": _build_checkout_activity_rows,
    },
    "overdue_audits": {
        "key": "overdue_audits",
        "title": "Overdue Physical Audits",
        "description": (
            f"Assets whose last physical audit is more than {AUDIT_INTERVAL_DAYS} "
            "days old, or that have never been audited."
        ),
        "columns": _OVERDUE_AUDITS_COLUMNS,
        "defaultSort": "Ascending by days overdue",
        "builder": _build_overdue_audits_rows,
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
