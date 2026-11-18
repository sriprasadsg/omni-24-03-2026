"""ITAM pre-built report registry (Phase 72, D-08/D-09).

All six D-08 reports live here: warranty_expiring (72-01, the tracer),
asset_value/checkout_activity/overdue_audits (72-02 Task 1), and
license_utilization/low_stock_consumables (72-02 Task 2). Every report is a
new PREBUILT_REPORTS entry plus a new `builder` callable — this module's
public shape (list_prebuilt_reports/run_prebuilt_report) never changes to
add one.

Deliberately imports no FastAPI symbol, matching itam_reporting_service.py's
own no-FastAPI-import convention — this module is unit-testable without a
running app.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import itam_cost_service
from itam_cost_service import INACTIVE_STATUSES, compute_asset_cost, sort_cost_rows
from itam_finance_service import (
    WARRANTY_STATUS_EXPIRING,
    compute_warranty_status,
    get_warranty_alert_window,
)
from itam_lifecycle_endpoints import (
    AUDIT_INTERVAL_DAYS,
    _audit_cutoff_iso,
    _overdue_query,
    _overdue_row,
)
from itam_license_endpoints import _enrich_license_seats_and_expiry

_EM_DASH = "—"

# D-19 fallback: a consumable with no admin-set reorderThreshold is flagged
# by low_stock_consumables when its availableQuantity is at or below this
# fixed heuristic — so the report works day one with no data migration.
DEFAULT_LOW_STOCK_QUANTITY = 5

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
    """Asset value report rows from the shared per-asset cost computation
    (Phase 78, COST-01): one tenant-scoped assets read, one model read and one
    clock read, then itam_cost_service.compute_asset_cost per asset, so every
    row's Book Value equals the cost view's figure for that asset.

    Population is unchanged: assets whose stored purchase cost and purchase
    date are both present. Disposed and retired assets are left out (D-04).
    Rows follow itam_cost_service.sort_cost_rows (D-08): book value high to
    low, not-tracked rows last, then name, asset tag, asset id. A malformed
    cost or date shows an em dash with its reason code instead of failing.
    """
    assets = await itam_cost_service.load_tenant_assets(db, tenant_id)
    population = [
        a for a in assets
        if a.get("purchaseCostCents") is not None
        and a.get("purchaseDate") is not None
        and itam_cost_service.normalize_lifecycle_status(a.get("lifecycleStatus")) not in INACTIVE_STATUSES
    ]
    models = await itam_cost_service.load_models_by_id(db, tenant_id, population)
    now = itam_cost_service.utc_now()
    costs = sort_cost_rows(
        compute_asset_cost(a, models.get(a.get("modelId")), now) for a in population
    )
    return [
        {
            "Asset Tag": _dash(c["assetTag"]),
            "Name": _dash(c["name"]),
            "Purchase Date": _dash(c["purchaseDate"]),
            "Purchase Cost": _cents_to_dollars(c["purchaseCostCents"]),
            "Book Value": _cents_to_dollars(c["bookValueCents"]),
            "Years Elapsed": _dash(c["yearsElapsed"]),
            "Reason": _dash(c["reason"]),
        }
        for c in costs
    ]


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


_LICENSE_UTILIZATION_COLUMNS = [
    "License", "Manufacturer", "Seats Total", "Seats Assigned", "Seats Available",
    "Utilization %", "Expiry Date", "Status",
]


async def _build_license_utilization_rows(db, tenant_id: Optional[str]) -> List[Dict[str, Any]]:
    """Reads db.licenses tenant-scoped; for each licence obtains the
    assigned-seat count with db.license_assignments.count_documents and
    calls itam_license_endpoints._enrich_license_seats_and_expiry — the same
    function GET /api/itam/licenses uses, so this report and the Licences
    tab can never disagree (must_haves truth). A zero seatCount reports
    zero percent utilisation rather than raising a division error. Sorted
    descending by utilisation percentage.
    """
    licenses = await db.licenses.find({}, {"_id": 0}).to_list(length=None)
    now = datetime.now(timezone.utc)

    rows: List[Dict[str, Any]] = []
    for lic in licenses:
        seats_assigned = await db.license_assignments.count_documents({"licenseId": lic["id"]})
        enriched = _enrich_license_seats_and_expiry(dict(lic), seats_assigned, now)
        seat_count = enriched.get("seatCount") or 0
        utilization_pct = round((seats_assigned / seat_count) * 100, 1) if seat_count else 0.0

        if enriched.get("isExpired"):
            license_status = "Expired"
        elif enriched.get("expiryDate"):
            license_status = "Active"
        else:
            license_status = "No Expiry"

        rows.append({
            "_sortKey": utilization_pct,
            "License": _dash(enriched.get("name")),
            "Manufacturer": _dash(enriched.get("manufacturerId")),
            "Seats Total": seat_count,
            "Seats Assigned": seats_assigned,
            "Seats Available": enriched.get("seatsAvailable"),
            "Utilization %": utilization_pct,
            "Expiry Date": _dash(enriched.get("expiryDate")),
            "Status": license_status,
        })

    rows.sort(key=lambda r: r["_sortKey"], reverse=True)
    for row in rows:
        row.pop("_sortKey", None)
    return rows


_LOW_STOCK_CONSUMABLES_COLUMNS = [
    "Consumable", "Unit Type", "Available", "Initial", "Reorder Threshold", "Basis",
]


async def _build_low_stock_consumables_rows(db, tenant_id: Optional[str]) -> List[Dict[str, Any]]:
    """Reads db.itam_consumables tenant-scoped. Flags a consumable whose
    availableQuantity is at or below its own reorderThreshold when that
    field is set (D-19's chosen value), otherwise at or below the module
    fallback DEFAULT_LOW_STOCK_QUANTITY (D-19's derived heuristic) — so the
    report works with no data migration. Per RESEARCH.md Pitfall 3,
    consumable ids are raw ObjectId hex strings with no prefix, unlike
    every sibling entity — `name` is the identifying display column, never
    id, and no join-by-id to assets is attempted. Sorted ascending by
    availableQuantity.
    """
    consumables = await db.itam_consumables.find({}, {"_id": 0}).to_list(length=None)

    rows: List[Dict[str, Any]] = []
    for con in consumables:
        available = con.get("availableQuantity")
        if available is None:
            continue
        threshold = con.get("reorderThreshold")
        if threshold is not None:
            if available > threshold:
                continue
            basis = "Configured threshold"
        else:
            if available > DEFAULT_LOW_STOCK_QUANTITY:
                continue
            basis = f"Default ({DEFAULT_LOW_STOCK_QUANTITY})"

        rows.append({
            "_sortKey": available,
            "Consumable": _dash(con.get("name")),
            "Unit Type": _dash(con.get("unitType")),
            "Available": available,
            "Initial": _dash(con.get("initialQuantity")),
            "Reorder Threshold": _dash(threshold),
            "Basis": basis,
        })

    rows.sort(key=lambda r: r["_sortKey"])
    for row in rows:
        row.pop("_sortKey", None)
    return rows


# Keyed by report key. Each value carries key/title/description/columns
# (declared display headers)/defaultSort (human-readable order description)
# and `builder` (the async row-building callable) — list_prebuilt_reports
# strips `builder` before returning metadata to the Reports tab.
_ENDPOINT_COSTS_COLUMNS = [
    "Asset Tag", "Name", "Endpoint", "Lifecycle", "Purchase Cost", "Book Value",
    "License Cost per Year", "One-Time License Cost", "Reason",
]
_NOT_TRACKED = "Not tracked"


def _tracked(cents: Any) -> Any:
    return _NOT_TRACKED if cents is None else f"${cents / 100:,.2f}"


def _license_cell(license_row: Dict[str, Any], key: str) -> Any:
    """A license figure as the Costs tab shows it: the amount, "Not tracked" when the asset's seats are on
    licenses without a cost, an em dash when it holds no seat."""
    if license_row.get(key) is not None:
        return f"${license_row[key] / 100:,.2f}"
    return _NOT_TRACKED if license_row.get("untrackedSeats") else _EM_DASH


async def _build_endpoint_costs_rows(db, tenant_id: Optional[str]) -> List[Dict[str, Any]]:
    """Costs by endpoint (Phase 80, COST-08): exactly the rows of the ITAM Costs tab, from the same
    itam_cost_service.compute_tenant_costs call as GET /api/itam/costs/assets (active assets, D-08 order),
    with purchase cost, book value and the license cost allocated from seats on each asset."""
    result = await itam_cost_service.compute_tenant_costs(db, tenant_id, with_agents=True, with_licenses=True)
    return [
        {
            "Asset Tag": _dash(r["assetTag"]),
            "Name": _dash(r["name"]),
            "Endpoint": _dash((r.get("agent") or {}).get("hostname")),
            "Lifecycle": _dash(r["lifecycleStatus"]),
            "Purchase Cost": _tracked(r["purchaseCostCents"]),
            "Book Value": _tracked(r["bookValueCents"]),
            "License Cost per Year": _license_cell(r["license"], "recurringAnnualCents"),
            "One-Time License Cost": _license_cell(r["license"], "oneTimeCents"),
            "Reason": _dash(r["reason"]),
        }
        for r in result["rows"]
    ]


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
    "endpoint_costs": {
        "key": "endpoint_costs",
        "title": "Costs by Endpoint",
        "description": "Purchase cost, book value and allocated license cost per active asset, as on the Costs tab.",
        "columns": _ENDPOINT_COSTS_COLUMNS,
        "defaultSort": "Descending by computed book value",
        "builder": _build_endpoint_costs_rows,
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
    "license_utilization": {
        "key": "license_utilization",
        "title": "License Seat Utilization",
        "description": "Seat assignment and utilisation percentage per software license.",
        "columns": _LICENSE_UTILIZATION_COLUMNS,
        "defaultSort": "Descending by utilization percentage",
        "builder": _build_license_utilization_rows,
    },
    "low_stock_consumables": {
        "key": "low_stock_consumables",
        "title": "Low-Stock Consumables",
        "description": (
            f"Consumables at or below their reorder threshold, or the default "
            f"fallback of {DEFAULT_LOW_STOCK_QUANTITY} when no threshold is set."
        ),
        "columns": _LOW_STOCK_CONSUMABLES_COLUMNS,
        "defaultSort": "Ascending by available quantity",
        "builder": _build_low_stock_consumables_rows,
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
