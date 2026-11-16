"""ITAM dashboard KPI aggregation (Phase 72 Plan 04, ITAM-REP-04).

Computes the four D-16 KPIs the dashboard tile grid consumes — asset value
(with lifecycle-status breakdown), license seat utilisation, warranty
expirations (with a 12-month timeline), and overdue check-in/audit counts —
all tenant-scoped and all derived from the exact functions the Finance,
Licences and Lifecycle tabs already call (`itam_cost_service.compute_asset_cost`
(the Phase 78 shared per-asset computation over `itam_finance_service.compute_book_value`)
/`compute_warranty_status`/`get_warranty_alert_window`,
`itam_lifecycle_endpoints._overdue_query`), never re-derived, so a KPI tile
and its source tab can never disagree.

Deliberately imports no FastAPI symbol, matching the service/endpoint split
`itam_finance_service.py`/`itam_reporting_service.py` already use — this
module stays unit-testable without a running app.

Every KPI object carries `hasData` (bool) and `drilldownReportKey` (the
`itam_reporting_prebuilt.PREBUILT_REPORTS` key its tile opens, D-18). When
`hasData` is False every numeric field on that KPI is None — never a
fabricated 0 or 100% that would read as a real measurement (ITAM-REP-04
prohibition).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

import itam_cost_service
from itam_cost_service import INACTIVE_STATUSES, compute_asset_cost, load_models_by_id
from itam_finance_service import (
    WARRANTY_STATUS_ACTIVE,
    WARRANTY_STATUS_EXPIRED,
    WARRANTY_STATUS_EXPIRING,
    compute_warranty_status,
    get_warranty_alert_window,
)
from itam_lifecycle_endpoints import _audit_cutoff_iso, _overdue_query
from itam_models import DEFAULT_LIFECYCLE_STATUS, LifecycleStatus


def _status_breakdown(assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every LifecycleStatus member, in its declared enum order, including
    zero-count statuses — never re-sorted by count (must_haves truth). An
    asset document with no `lifecycleStatus` key is counted under
    DEFAULT_LIFECYCLE_STATUS, matching asset_endpoints.py's own read-time
    default for pre-existing agent-discovered assets."""
    counts = {status.value: 0 for status in LifecycleStatus}
    for asset in assets:
        status_value = asset.get("lifecycleStatus") or DEFAULT_LIFECYCLE_STATUS.value
        counts[status_value] = counts.get(status_value, 0) + 1
    return [
        {"status": status.value, "label": status.value.capitalize(), "count": counts[status.value]}
        for status in LifecycleStatus
    ]


async def _compute_asset_value_kpi(
    db, tenant_id: str, assets: List[Dict[str, Any]], now: datetime,
) -> Dict[str, Any]:
    """Total book value and lifecycle-status breakdown for one tenant.

    Every per-asset value comes from `itam_cost_service.compute_asset_cost`
    (models from one `load_models_by_id` read), the same function the cost
    summary and the Asset value report use, so for the same tenant and `now`
    the tile equals `bookValueTotal` (Phase 78 SC3, COST-01).

    `statusBreakdown` and `assetCount` count every asset of every status (the
    lifecycle pie is an inventory count, D-04). Disposed and retired assets
    are out of scope for money (D-01): they add nothing to
    `totalBookValueCents` and are left out of `inScopeAssetCount`. Of the
    in-scope assets, `valuedCount` have a book value and `withoutPolicyCount`
    (= inScopeAssetCount - valuedCount) do not. When nothing is valued the
    total is None, never a fabricated 0 (D-10); `hasData` stays True whenever
    the tenant has any asset so the tile can show Not tracked."""
    status_breakdown = _status_breakdown(assets)
    asset_count = len(assets)
    if asset_count == 0:
        return {
            "hasData": False,
            "totalBookValueCents": None,
            "assetCount": 0,
            "inScopeAssetCount": None,
            "valuedCount": None,
            "withoutPolicyCount": None,
            "statusBreakdown": status_breakdown,
            "drilldownReportKey": "asset_value",
        }

    models_by_id = await load_models_by_id(db, tenant_id, assets)
    rows = [compute_asset_cost(a, models_by_id.get(a.get("modelId")), now) for a in assets]
    in_scope = [r for r in rows if r["lifecycleStatus"] not in INACTIVE_STATUSES]
    valued = [r["bookValueCents"] for r in in_scope if r["valued"]]

    return {
        "hasData": True,
        "totalBookValueCents": sum(valued) if valued else None,
        "assetCount": asset_count,
        "inScopeAssetCount": len(in_scope),
        "valuedCount": len(valued),
        "withoutPolicyCount": len(in_scope) - len(valued),
        "statusBreakdown": status_breakdown,
        "drilldownReportKey": "asset_value",
    }


async def _compute_license_utilization_kpi(db) -> Dict[str, Any]:
    """Assigned-over-total seat percentage across every tenant licence.
    Counts assigned seats with `db.license_assignments.count_documents`
    per licence, exactly as `itam_license_endpoints.list_licenses` does, so
    this KPI and the Licences tab can never disagree. `hasData` is False —
    and every numeric field is None, never a fabricated 0% or 100% — when
    there are no licences or the total seat count is zero."""
    licenses = await db.licenses.find({}, {"_id": 0}).to_list(length=None)
    if not licenses:
        return {
            "hasData": False,
            "seatsTotal": None,
            "seatsAssigned": None,
            "seatsAvailable": None,
            "utilizationPercent": None,
            "drilldownReportKey": "license_utilization",
        }

    seats_total = 0
    seats_assigned = 0
    for lic in licenses:
        assigned = await db.license_assignments.count_documents({"licenseId": lic["id"]})
        seats_total += lic.get("seatCount") or 0
        seats_assigned += assigned

    if seats_total == 0:
        return {
            "hasData": False,
            "seatsTotal": 0,
            "seatsAssigned": None,
            "seatsAvailable": None,
            "utilizationPercent": None,
            "drilldownReportKey": "license_utilization",
        }

    seats_available = max(seats_total - seats_assigned, 0)
    utilization_percent = round((seats_assigned / seats_total) * 100, 1)
    return {
        "hasData": True,
        "seatsTotal": seats_total,
        "seatsAssigned": seats_assigned,
        "seatsAvailable": seats_available,
        "utilizationPercent": utilization_percent,
        "drilldownReportKey": "license_utilization",
    }


def _next_twelve_month_keys(now: datetime) -> List[str]:
    """The 12 consecutive `YYYY-MM` month keys starting at `now`'s own
    month, used as the timeline's fixed bucket order (so a month with zero
    expirations still appears)."""
    keys = []
    year, month = now.year, now.month
    for offset in range(12):
        total = month - 1 + offset
        bucket_year = year + total // 12
        bucket_month = total % 12 + 1
        keys.append(f"{bucket_year:04d}-{bucket_month:02d}")
    return keys


async def _compute_warranty_kpi(
    db, tenant_id: Optional[str], assets: List[Dict[str, Any]], now: datetime,
) -> Dict[str, Any]:
    """Warranty expiry counts and a 12-month timeline, both derived from
    `itam_finance_service.compute_warranty_status`/`get_warranty_alert_window`
    verbatim — the alert-window boundary is inherited, never restated
    (must_haves truth). `hasData` is False when no asset in the tenant
    carries both a purchase date and a warranty length."""
    window_days = await get_warranty_alert_window(db, tenant_id)

    with_warranty_data = [
        asset for asset in assets
        if asset.get("purchaseDate") and asset.get("warrantyMonths") is not None
    ]
    if not with_warranty_data:
        return {
            "hasData": False,
            "alertWindowDays": window_days,
            "expiringSoonCount": None,
            "expiredCount": None,
            "timeline": [],
            "drilldownReportKey": "warranty_expiring",
        }

    month_keys = _next_twelve_month_keys(now)
    timeline_counts = {key: 0 for key in month_keys}
    expiring_count = 0
    expired_count = 0

    for asset in with_warranty_data:
        status_result = compute_warranty_status(
            asset.get("purchaseDate"), asset.get("warrantyMonths"), now, window_days,
        )
        warranty_status = status_result["warrantyStatus"]
        if warranty_status == WARRANTY_STATUS_EXPIRING:
            expiring_count += 1
        elif warranty_status == WARRANTY_STATUS_EXPIRED:
            expired_count += 1

        expires_at = status_result.get("warrantyExpiresAt")
        if expires_at and warranty_status in (WARRANTY_STATUS_ACTIVE, WARRANTY_STATUS_EXPIRING):
            expires_dt = datetime.fromisoformat(expires_at)
            key = f"{expires_dt.year:04d}-{expires_dt.month:02d}"
            if key in timeline_counts:
                timeline_counts[key] += 1

    timeline = [{"month": key, "count": timeline_counts[key]} for key in month_keys]

    return {
        "hasData": True,
        "alertWindowDays": window_days,
        "expiringSoonCount": expiring_count,
        "expiredCount": expired_count,
        "timeline": timeline,
        "drilldownReportKey": "warranty_expiring",
    }


async def _compute_overdue_kpi(db, assets: List[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """Overdue physical-audit and overdue check-in counts. The audit count
    reuses `itam_lifecycle_endpoints._overdue_query` unchanged (imported,
    never re-derived, must_haves truth); the check-in count is a deployed
    asset whose `expectedReturnDate` is in the past. `hasData` is False when
    the tenant has zero assets."""
    if not assets:
        return {
            "hasData": False,
            "overdueAuditCount": None,
            "overdueCheckinCount": None,
            "totalCount": None,
            "drilldownReportKey": "overdue_audits",
        }

    cutoff = _audit_cutoff_iso()
    audit_docs = await db.assets.find(
        _overdue_query(cutoff), {"_id": 0, "id": 1}
    ).to_list(length=None)
    audit_ids = {d["id"] for d in audit_docs}

    now_iso = now.isoformat(timespec="milliseconds")
    checkin_docs = await db.assets.find(
        {
            "lifecycleStatus": LifecycleStatus.DEPLOYED.value,
            "expectedReturnDate": {"$lt": now_iso},
        },
        {"_id": 0, "id": 1},
    ).to_list(length=None)
    checkin_ids = {d["id"] for d in checkin_docs}

    return {
        "hasData": True,
        "overdueAuditCount": len(audit_ids),
        "overdueCheckinCount": len(checkin_ids),
        "totalCount": len(audit_ids | checkin_ids),
        "drilldownReportKey": "overdue_audits",
    }


async def compute_itam_kpis(db, tenant_id) -> Dict[str, Any]:
    """The single entry point the KPI route calls. Reads `db.assets` exactly
    once via a batched `find` — never a per-KPI re-query, never an
    aggregation join — and fans that one asset list out to the assetValue,
    warrantyExpirations and overdue KPIs; licenseUtilization reads
    `db.licenses`/`db.license_assignments` independently since it shares no
    input with the asset-derived KPIs. All reads go through the caller-
    supplied tenant-isolated `db` handle, so a second tenant's data can never
    contribute to these numbers (must_haves truth). The clock is read once
    here (itam_cost_service.utc_now, a single call) and that one `now` feeds every KPI
    (Phase 78 Pitfall 9); the assets read carries an explicit tenantId filter
    next to the wrapper's own scoping."""
    now = itam_cost_service.utc_now()

    assets = await db.assets.find(
        {"tenantId": tenant_id},
        {
            "_id": 0, "id": 1, "assetTag": 1, "name": 1, "lifecycleStatus": 1,
            "modelId": 1, "purchaseCostCents": 1, "purchaseDate": 1,
            "warrantyMonths": 1, "expectedReturnDate": 1,
        },
    ).to_list(length=None)

    asset_value = await _compute_asset_value_kpi(db, tenant_id, assets, now)
    license_utilization = await _compute_license_utilization_kpi(db)
    warranty_expirations = await _compute_warranty_kpi(db, tenant_id, assets, now)
    overdue = await _compute_overdue_kpi(db, assets, now)

    return {
        "assetValue": asset_value,
        "licenseUtilization": license_utilization,
        "warrantyExpirations": warranty_expirations,
        "overdue": overdue,
    }
