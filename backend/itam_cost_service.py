"""The one per-asset cost computation (Phase 78, COST-01).

Shared by the ITAM cost routes, the ITAM KPI tile and the Asset value report (Phase 59 D-04
depreciation, Phase 72 reuse rule). Imports no web-framework symbol, so any route or report can
call it. Everything is computed at read time from the stored purchase cost, purchase date and
model policy; nothing is persisted between requests, so a figure always reflects the asset
documents the single read returned.

Money is integer cents end to end. An unknown cost or book value is None with exactly one
reason code, never a fabricated zero (D-10). Depreciation is the finance service's own
function, called unchanged; this module never re-implements the formula and never clamps its
result.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import rbac_defaults
from itam_finance_service import (
    REASON_NO_DEPRECIATION_POLICY,
    REASON_NO_PURCHASE_RECORD,
    compute_book_value,
)
from itam_models import DEFAULT_LIFECYCLE_STATUS, LifecycleStatus

# D-01: disposed and retired assets are out of the totals unless the caller asks for them.
INACTIVE_STATUSES = frozenset({LifecycleStatus.DISPOSED.value, LifecycleStatus.RETIRED.value})

REASON_DISPOSED = "disposed"
REASON_RETIRED = "retired"
REASON_UNREADABLE_COST = "unreadable_purchase_cost"
REASON_UNREADABLE_DATE = "unreadable_purchase_date"

# Precedence order: an asset carries the first reason that applies.
REASON_CODES = (
    REASON_DISPOSED,
    REASON_RETIRED,
    REASON_UNREADABLE_COST,
    REASON_NO_PURCHASE_RECORD,
    REASON_NO_DEPRECIATION_POLICY,
    REASON_UNREADABLE_DATE,
)

FLAG_FUTURE_PURCHASE_DATE = "futurePurchaseDate"
FLAG_POSSIBLE_DUPLICATE = "possibleDuplicate"

ASSET_COST_PROJECTION = {
    "_id": 0, "id": 1, "assetTag": 1, "name": 1, "lifecycleStatus": 1, "modelId": 1,
    "purchaseCostCents": 1, "purchaseDate": 1, "hardwareKey": 1, "serialNumber": 1,
}
MODEL_POLICY_PROJECTION = {"_id": 0, "id": 1, "usefulLifeYears": 1, "salvageValueCents": 1}


def utc_now() -> datetime:
    """The single clock for cost figures; tests patch this one name. Consumers call it through
    the module (itam_cost_service.utc_now()) so a patch reaches them."""
    return datetime.now(timezone.utc)


def require_tenant(tenant_id: Optional[str]) -> str:
    """Refuse an empty or platform-admin tenant: the database wrapper skips tenant scoping for
    the platform context, so a cost read there would blend every organization."""
    if not tenant_id or tenant_id == rbac_defaults.PLATFORM_TENANT_ID:
        raise ValueError("a cost computation needs one real tenant id")
    return tenant_id


def _is_cents(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_life(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_future(purchase_date: Any, now: datetime) -> bool:
    """True when the date parses the way the depreciation function parses it and lies after now."""
    if not isinstance(purchase_date, str):
        return False
    try:
        parsed = datetime.fromisoformat(purchase_date.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed > now


def compute_asset_cost(asset: Dict[str, Any], model_doc: Optional[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """One asset's cost row. Pure; never raises for any document shape.

    An asset that is not valued carries exactly one reason (D-10). The asset-level useful life and
    salvage fields are never read: the depreciation policy lives on the model (D-12).
    """
    raw_cost = asset.get("purchaseCostCents")
    raw_date = asset.get("purchaseDate")
    status_value = asset.get("lifecycleStatus") or DEFAULT_LIFECYCLE_STATUS.value
    row: Dict[str, Any] = {
        "assetId": asset.get("id"),
        "assetTag": asset.get("assetTag"),
        "name": asset.get("name"),
        "lifecycleStatus": status_value,
        "purchaseCostCents": raw_cost if _is_cents(raw_cost) else None,
        "purchaseDate": raw_date if isinstance(raw_date, str) else None,
        "bookValueCents": None,
        "yearsElapsed": None,
        "reason": None,
        "flags": [],
    }
    if _is_future(raw_date, now):
        row["flags"].append(FLAG_FUTURE_PURCHASE_DATE)

    if status_value in INACTIVE_STATUSES:
        row["reason"] = status_value
    elif raw_cost is not None and not _is_cents(raw_cost):
        row["reason"] = REASON_UNREADABLE_COST
    elif raw_cost is None or raw_date is None:
        row["reason"] = REASON_NO_PURCHASE_RECORD
    elif (
        not model_doc
        or not _is_life(model_doc.get("usefulLifeYears"))
        or not _is_cents(model_doc.get("salvageValueCents"))
    ):
        row["reason"] = REASON_NO_DEPRECIATION_POLICY
    else:
        try:
            result = compute_book_value(
                purchase_date=raw_date,
                purchase_cost_cents=raw_cost,
                useful_life_years=model_doc["usefulLifeYears"],
                salvage_value_cents=model_doc["salvageValueCents"],
                now=now,
            )
        except (ValueError, TypeError):
            row["reason"] = REASON_UNREADABLE_DATE
        else:
            row["bookValueCents"] = result["bookValueCents"]
            row["yearsElapsed"] = result["yearsElapsed"]

    row["priced"] = row["purchaseCostCents"] is not None
    row["valued"] = row["bookValueCents"] is not None
    return row


async def load_tenant_assets(db: Any, tenant_id: str) -> List[Dict[str, Any]]:
    """Every asset of one tenant in a single read, with an explicit tenant filter."""
    require_tenant(tenant_id)
    return await db.assets.find({"tenantId": tenant_id}, ASSET_COST_PROJECTION).to_list(length=None)


async def load_models_by_id(db: Any, tenant_id: str, assets: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The depreciation policy of every model the assets name, in one read (none when no asset has a model)."""
    require_tenant(tenant_id)
    model_ids = sorted({a["modelId"] for a in assets if a.get("modelId")})
    if not model_ids:
        return {}
    docs = await db.asset_models.find(
        {"tenantId": tenant_id, "id": {"$in": model_ids}}, MODEL_POLICY_PROJECTION
    ).to_list(length=None)
    return {m["id"]: m for m in docs}


def sort_cost_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """D-08 order: valued rows by book value descending, unvalued rows last, then name, tag, id."""
    return sorted(
        rows,
        key=lambda r: (
            r["bookValueCents"] is None,
            -(r["bookValueCents"] or 0),
            r.get("name") or "",
            r.get("assetTag") or "",
            r.get("assetId") or "",
        ),
    )


def _total(rows: List[Dict[str, Any]], key: str, present: str) -> Dict[str, Any]:
    contributors = [r[key] for r in rows if r[present]]
    return {"cents": sum(contributors) if contributors else None, "hasData": bool(contributors)}


def summarize_cost_rows(
    rows: List[Dict[str, Any]],
    *,
    tenant_id: str,
    now: datetime,
    include_inactive: bool,
    excluded_by_lifecycle: int,
) -> Dict[str, Any]:
    """The tenant summary over the in-scope rows. valued plus the reason counts equals total."""
    reasons = {code: 0 for code in REASON_CODES}
    flags = {FLAG_FUTURE_PURCHASE_DATE: 0, FLAG_POSSIBLE_DUPLICATE: 0}
    pairs = set()
    for row in rows:
        if row["reason"] in reasons:
            reasons[row["reason"]] += 1
        for flag in row["flags"]:
            if flag in flags:
                flags[flag] += 1
        for other in row.get("possibleDuplicateOf") or []:
            pairs.add(frozenset((row["assetId"], other)))
    return {
        "tenantId": tenant_id,
        "computedAt": now.isoformat(timespec="milliseconds"),
        "includeDisposed": include_inactive,
        "purchaseTotal": _total(rows, "purchaseCostCents", "priced"),
        "bookValueTotal": _total(rows, "bookValueCents", "valued"),
        "coverage": {
            "total": len(rows),
            "priced": sum(1 for r in rows if r["priced"]),
            "valued": sum(1 for r in rows if r["valued"]),
            "excludedByLifecycle": excluded_by_lifecycle,
            "reasons": reasons,
            "flags": flags,
            "possibleDuplicatePairs": len(pairs),
        },
    }


async def compute_tenant_costs(
    db: Any,
    tenant_id: str,
    *,
    include_inactive: bool = False,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Cost rows (D-08 order) and the summary for one tenant, from two collection reads and one clock read."""
    require_tenant(tenant_id)
    now = now if now is not None else utc_now()
    assets = await load_tenant_assets(db, tenant_id)
    models = await load_models_by_id(db, tenant_id, assets)
    all_rows = [compute_asset_cost(a, models.get(a.get("modelId")), now) for a in assets]
    if include_inactive:
        in_scope, hidden = all_rows, 0
    else:
        in_scope = [r for r in all_rows if r["lifecycleStatus"] not in INACTIVE_STATUSES]
        hidden = len(all_rows) - len(in_scope)
    return {
        "rows": sort_cost_rows(in_scope),
        "summary": summarize_cost_rows(
            in_scope, tenant_id=tenant_id, now=now,
            include_inactive=include_inactive, excluded_by_lifecycle=hidden,
        ),
    }
