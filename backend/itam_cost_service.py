"""The one per-asset cost computation (Phase 78, COST-01).

Shared by the ITAM cost routes, the ITAM KPI tile and the Asset value report (Phase 59 D-04
depreciation, Phase 72 reuse rule). Imports no web-framework symbol, so any route or report can
call it. Everything is computed at read time from the stored purchase cost, purchase date and
model policy; nothing is persisted between requests, so a figure always reflects the asset
documents the single read returned.

Money is integer cents end to end. An unknown cost or book value is None with exactly one
reason code, never a fabricated zero (D-10). Depreciation is the finance service's own
function, called unchanged; this module never re-implements the formula and never clamps its
result. A model whose salvage value exceeds the asset's purchase cost is marked, not capped.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import rbac_defaults
from itam_finance_service import (
    REASON_NO_DEPRECIATION_POLICY,
    REASON_NO_PURCHASE_RECORD,
    REASON_SALVAGE_EXCEEDS_COST,
    compute_book_value,
)
from itam_models import DEFAULT_LIFECYCLE_STATUS, LifecycleStatus
from seat_identity import normalize_serial

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
    REASON_SALVAGE_EXCEEDS_COST,
    REASON_UNREADABLE_DATE,
)

FLAG_FUTURE_PURCHASE_DATE = "futurePurchaseDate"
FLAG_POSSIBLE_DUPLICATE = "possibleDuplicate"

ASSET_COST_PROJECTION = {
    "_id": 0, "id": 1, "assetTag": 1, "name": 1, "lifecycleStatus": 1, "modelId": 1,
    "purchaseCostCents": 1, "purchaseDate": 1, "hardwareKey": 1, "serialNumber": 1,
}
MODEL_POLICY_PROJECTION = {"_id": 0, "id": 1, "usefulLifeYears": 1, "salvageValueCents": 1}
AGENT_JOIN_PROJECTION = {"_id": 0, "id": 1, "assetId": 1, "hostname": 1, "status": 1, "lastSeen": 1}


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


def policy_misfit_reason(model_doc: Optional[Dict[str, Any]], purchase_cost: Any) -> Optional[str]:
    """The reason a model's depreciation policy cannot value an asset bought for purchase_cost, or None
    when it fits. The one policy check: the cost rows and the per-asset book-value route both call it.

    Salvage lives on the model, cost on the asset. Salvage above the price paid would value the asset
    above its purchase cost, so the policy does not fit this asset: it is not valued, nothing is capped.
    """
    if not model_doc or not _is_life(model_doc.get("usefulLifeYears")) or not _is_cents(model_doc.get("salvageValueCents")):
        return REASON_NO_DEPRECIATION_POLICY
    if _is_cents(purchase_cost) and model_doc["salvageValueCents"] > purchase_cost:
        return REASON_SALVAGE_EXCEEDS_COST
    return None


def normalize_lifecycle_status(raw_status: Any) -> str:
    """The stored lifecycleStatus as a string: any non-string or empty value (a list or dict would
    not even hash) reads as the default. Every cost, KPI and report population filter uses this."""
    return raw_status if isinstance(raw_status, str) and raw_status else DEFAULT_LIFECYCLE_STATUS.value


def compute_asset_cost(asset: Dict[str, Any], model_doc: Optional[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """One asset's cost row. Pure; never raises for any document shape.

    An asset that is not valued carries exactly one reason (D-10). The asset-level useful life and
    salvage fields are never read: the depreciation policy lives on the model (D-12).
    """
    raw_cost = asset.get("purchaseCostCents")
    raw_date = asset.get("purchaseDate")
    status_value = normalize_lifecycle_status(asset.get("lifecycleStatus"))
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
    elif (misfit := policy_misfit_reason(model_doc, raw_cost)) is not None:
        row["reason"] = misfit
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


async def load_agents_by_asset(db: Any, tenant_id: str, asset_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """The agent of each asset, from one tenant-scoped read joined only on agents.assetId (D-06).

    The asset's own agentStatus is never read (the heartbeat stamps "Online" there and nothing
    resets it) and a hostname match is never used. Several agents on one asset give one summary:
    the latest lastSeen wins (ties by agent id) and agentCount is how many agents name the asset.
    The tenant wrapper hides Pending and Rejected agents, so those are not joined (A-78-10).
    """
    require_tenant(tenant_id)
    ids = sorted({a for a in asset_ids if isinstance(a, str) and a})
    if not ids:
        return {}
    docs = await db.agents.find(
        {"tenantId": tenant_id, "assetId": {"$in": ids}}, AGENT_JOIN_PROJECTION
    ).to_list(length=None)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for doc in docs:
        grouped.setdefault(doc.get("assetId"), []).append(doc)
    joined: Dict[str, Dict[str, Any]] = {}
    for asset_id, agents in grouped.items():
        best = max(agents, key=lambda d: (str(d.get("lastSeen") or ""), str(d.get("id") or "")))
        joined[asset_id] = {
            "agentId": best.get("id"),
            "hostname": best.get("hostname"),
            "status": best.get("status"),
            "lastSeen": best.get("lastSeen"),
            "agentCount": len(agents),
        }
    return joined


def mark_possible_duplicates(assets: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    """D-07: map asset id to the sorted ids it may duplicate. Pure; marks only, never merges (PROH-78-03).

    An agent-discovered asset (hardwareKey "serial:<value>") pairs with every hand-entered asset
    (no hardwareKey) whose normalized serialNumber equals that value. uuid: and mac: keys never take
    part, two hardware-keyed assets are never paired, and normalize_serial rejects placeholder serials.
    """
    agent_side: Dict[str, List[str]] = {}
    hand_side: Dict[str, List[str]] = {}
    for asset in assets:
        asset_id = asset.get("id")
        if not asset_id:
            continue
        key = asset.get("hardwareKey")
        if isinstance(key, str) and key.startswith("serial:"):
            value = normalize_serial(key[len("serial:"):])
            if value:
                agent_side.setdefault(value, []).append(asset_id)
        elif not key:
            value = normalize_serial(asset.get("serialNumber"))
            if value:
                hand_side.setdefault(value, []).append(asset_id)
    pairs: Dict[str, set] = {}
    for value, agent_ids in agent_side.items():
        for hand_id in hand_side.get(value, []):
            for agent_id in agent_ids:
                pairs.setdefault(agent_id, set()).add(hand_id)
                pairs.setdefault(hand_id, set()).add(agent_id)
    return {asset_id: sorted(others) for asset_id, others in pairs.items()}


def sort_cost_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """D-08 order: valued rows by book value descending, unvalued rows last, then name, tag, id."""
    return sorted(
        rows,
        key=lambda r: (
            r["bookValueCents"] is None,
            -(r["bookValueCents"] or 0),
            str(r.get("name") or ""),
            str(r.get("assetTag") or ""),
            str(r.get("assetId") or ""),
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
    """The tenant summary over the in-scope rows. valued plus the reason counts equals total.

    possibleDuplicatePairs counts each pair once when at least one of its two assets is an in-scope
    row (a row names its twin even when the twin is disposed or retired and not in the rows).
    """
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
    with_agents: bool = False,
) -> Dict[str, Any]:
    """Cost rows (D-08 order) and the summary for one tenant, from two collection reads and one clock read.

    with_agents adds one more read (agents by assetId) and an `agent` field on every in-scope row.
    Duplicate markers are computed over all of the tenant's assets, active or not, and only then
    filtered to the in-scope rows, so a row carries the same markers under either scope.
    """
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
    # Markers are computed over every asset of the tenant, then applied to the in-scope rows, so a
    # row shows the same markers whatever the scope: an active asset still names a retired twin.
    marks = mark_possible_duplicates(assets)
    for row in in_scope:
        row["possibleDuplicateOf"] = marks.get(row["assetId"], [])
        if row["possibleDuplicateOf"]:
            row["flags"].append(FLAG_POSSIBLE_DUPLICATE)
    if with_agents:
        agents = await load_agents_by_asset(db, tenant_id, (r["assetId"] for r in in_scope))
        for row in in_scope:
            row["agent"] = agents.get(row["assetId"])
    return {
        "rows": sort_cost_rows(in_scope),
        "summary": summarize_cost_rows(
            in_scope, tenant_id=tenant_id, now=now,
            include_inactive=include_inactive, excluded_by_lifecycle=hidden,
        ),
    }


async def compute_asset_cost_detail(
    db: Any, tenant_id: str, asset_id: str, *, now: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    """One asset's row (disposed and retired included) plus computedAt, or None when the tenant has no such asset.

    The whole tenant set is computed so the duplicate markers and the agent equal the list row's
    (A-78-12): markers span every asset of the tenant under either scope, so the list row (with or
    without includeDisposed) and this row always agree. asset_id is only compared in Python, never
    placed in a query.
    """
    result = await compute_tenant_costs(db, tenant_id, include_inactive=True, with_agents=True, now=now)
    for row in result["rows"]:
        if row["assetId"] == asset_id:
            return {**row, "computedAt": result["summary"]["computedAt"]}
    return None
