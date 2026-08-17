"""ITAM dashboard KPI aggregation (Phase 72 Plan 04, ITAM-REP-04).

Computes the four D-16 KPIs the dashboard tile grid consumes — asset value
(with lifecycle-status breakdown), license seat utilisation, warranty
expirations (with a 12-month timeline), and overdue check-in/audit counts —
all tenant-scoped and all derived from the exact functions the Finance,
Licences and Lifecycle tabs already call (`itam_finance_service.compute_book_value`
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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from itam_finance_service import (
    WARRANTY_STATUS_ACTIVE,
    WARRANTY_STATUS_EXPIRED,
    WARRANTY_STATUS_EXPIRING,
    compute_book_value,
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


async def _compute_asset_value_kpi(db, assets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Total book value and lifecycle-status breakdown across every tenant
    asset. Each asset's value is computed with the exact input resolution
    `itam_finance_endpoints.get_asset_book_value` uses (policy from a single
    batched `asset_models` lookup, never a per-asset query). An asset with
    no purchase record, no matching depreciation policy, or whose inputs
    raise ValueError is counted in `assetCount` and `statusBreakdown` but
    contributes nothing to `totalBookValueCents`, and is tallied in
    `withoutPolicyCount` instead — never silently dropped, never failing the
    whole KPI (must_haves truth)."""
    status_breakdown = _status_breakdown(assets)
    asset_count = len(assets)
    if asset_count == 0:
        return {
            "hasData": False,
            "totalBookValueCents": None,
            "assetCount": 0,
            "withoutPolicyCount": None,
            "statusBreakdown": status_breakdown,
            "drilldownReportKey": "asset_value",
        }

    model_ids = sorted({a["modelId"] for a in assets if a.get("modelId")})
    models_by_id: Dict[str, Dict[str, Any]] = {}
    if model_ids:
        model_docs = await db.asset_models.find(
            {"id": {"$in": model_ids}},
            {"_id": 0, "id": 1, "usefulLifeYears": 1, "salvageValueCents": 1},
        ).to_list(length=None)
        models_by_id = {m["id"]: m for m in model_docs}

    now = datetime.now(timezone.utc)
    total_book_value_cents = 0
    without_policy_count = 0
    for asset in assets:
        purchase_cost = asset.get("purchaseCostCents")
        purchase_date = asset.get("purchaseDate")
        if purchase_cost is None or purchase_date is None:
            without_policy_count += 1
            continue

        model_doc = models_by_id.get(asset.get("modelId"))
        if (
            not model_doc
            or model_doc.get("usefulLifeYears") is None
            or model_doc.get("salvageValueCents") is None
        ):
            without_policy_count += 1
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
            without_policy_count += 1
            continue

        total_book_value_cents += result["bookValueCents"]

    return {
        "hasData": True,
        "totalBookValueCents": total_book_value_cents,
        "assetCount": asset_count,
        "withoutPolicyCount": without_policy_count,
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
    overdue_audit_count = await db.assets.count_documents(_overdue_query(cutoff))

    now_iso = now.isoformat(timespec="milliseconds")
    overdue_checkin_count = await db.assets.count_documents({
        "lifecycleStatus": LifecycleStatus.DEPLOYED.value,
        "expectedReturnDate": {"$lt": now_iso},
    })

    return {
        "hasData": True,
        "overdueAuditCount": overdue_audit_count,
        "overdueCheckinCount": overdue_checkin_count,
        "totalCount": overdue_audit_count + overdue_checkin_count,
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
    contribute to these numbers (must_haves truth)."""
    now = datetime.now(timezone.utc)

    assets = await db.assets.find(
        {},
        {
            "_id": 0, "id": 1, "assetTag": 1, "name": 1, "lifecycleStatus": 1,
            "modelId": 1, "purchaseCostCents": 1, "purchaseDate": 1,
            "warrantyMonths": 1, "expectedReturnDate": 1,
        },
    ).to_list(length=None)

    asset_value = await _compute_asset_value_kpi(db, assets)
    license_utilization = await _compute_license_utilization_kpi(db)
    warranty_expirations = await _compute_warranty_kpi(db, tenant_id, assets, now)
    overdue = await _compute_overdue_kpi(db, assets, now)

    return {
        "assetValue": asset_value,
        "licenseUtilization": license_utilization,
        "warrantyExpirations": warranty_expirations,
        "overdue": overdue,
    }
