"""License spend and its allocation to endpoints (Phase 79, COST-04/COST-05).

A license carries an optional cost for the whole license (``costCents``, integer cents) and its billing
basis (``costPeriod``: one_time, monthly or annual). A license without both is not tracked: it adds
nothing to spend and is counted in coverage, never as 0. Bases are never summed naively: recurring
spend is reported per year (annual as stored, monthly x 12) and one-time spend on its own.

Each priced license's amount is split over its seatCount seats in whole cents, the remainder going one
cent each to the first seats, so its seats add up to the amount exactly. Assignments take seats in a
fixed order (assignedAt, then id). A seat on an asset of the tenant is allocated to that asset; a seat
on a user, or on an asset the tenant no longer has, is unattributed; seats nobody holds are idle.
Assignments past seatCount (the seat race's brief overshoot) take no cost. So, per license and in
total: allocated + unattributed + idle == spend. A license with no seats is all idle.

Pure apart from the two loaders; imports no web-framework symbol.
"""
from typing import Any, Dict, Iterable, List, Optional, Set

PERIODS = ("one_time", "monthly", "annual")
RECURRING, ONE_TIME = "recurringAnnual", "oneTime"
BUCKETS = (RECURRING, ONE_TIME)

LICENSE_PROJECTION = {"_id": 0, "id": 1, "name": 1, "seatCount": 1, "costCents": 1, "costPeriod": 1,
                      "expiryDate": 1}
ASSIGNMENT_PROJECTION = {"_id": 0, "id": 1, "licenseId": 1, "targetType": 1, "targetId": 1, "assignedAt": 1}


def _cents(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_priced(lic: Dict[str, Any]) -> bool:
    return _cents(lic.get("costCents")) and lic.get("costPeriod") in PERIODS


def bucket_of(period: str) -> str:
    return ONE_TIME if period == "one_time" else RECURRING


def amount_cents(lic: Dict[str, Any]) -> int:
    """The license's amount in its bucket: per year for a recurring license, as paid for a one-time one."""
    return lic["costCents"] * 12 if lic["costPeriod"] == "monthly" else lic["costCents"]


def split_seats(total: int, seats: int) -> List[int]:
    """total cents over seats seats, the remainder one cent each to the first seats; sums to total."""
    if seats <= 0:
        return []
    base, rem = divmod(total, seats)
    return [base + 1] * rem + [base] * (seats - rem)


def allocate_license(lic: Dict[str, Any], assignments: Iterable[Dict[str, Any]], asset_ids: Set[str]) -> Dict[str, Any]:
    """One priced license: its spend, the cents each of the tenant's assets holds, unattributed and idle."""
    seat_count = lic.get("seatCount") if _cents(lic.get("seatCount")) else 0
    spend = amount_cents(lic)
    parts = split_seats(spend, seat_count)
    ordered = sorted(assignments, key=lambda a: (str(a.get("assignedAt") or ""), str(a.get("id") or "")))
    allocated: Dict[str, int] = {}
    unattributed = 0
    seats = {"total": seat_count, "onAssets": 0, "onUsers": 0, "orphaned": 0, "idle": 0, "over": 0}
    for k, a in enumerate(ordered):
        if k >= seat_count:
            seats["over"] += 1
            continue
        target = a.get("targetId")
        if a.get("targetType") == "asset" and target in asset_ids:
            allocated[target] = allocated.get(target, 0) + parts[k]
            seats["onAssets"] += 1
        else:
            unattributed += parts[k]
            seats["onUsers" if a.get("targetType") == "user" else "orphaned"] += 1
    held = min(len(ordered), seat_count)
    seats["idle"] = seat_count - held
    idle = sum(parts[held:]) if seat_count else spend
    return {"licenseId": lic.get("id"), "name": lic.get("name"), "costPeriod": lic["costPeriod"],
            "bucket": bucket_of(lic["costPeriod"]), "spendCents": spend, "allocated": allocated,
            "unattributedCents": unattributed, "idleCents": idle, "seats": seats}


def _empty_bucket() -> Dict[str, Any]:
    return {"spendCents": None, "allocatedCents": None, "unattributedCents": None, "idleCents": None,
            "allocatedToExcludedCents": None, "licenses": 0, "hasData": False}


def allocate(licenses: List[Dict[str, Any]], assignments: List[Dict[str, Any]], asset_ids: Set[str],
             in_scope_ids: Set[str]) -> Dict[str, Any]:
    """Spend and allocation over a tenant's licenses.

    asset_ids are all of the tenant's assets (a seat on any of them is allocated); in_scope_ids are the
    rows shown, so allocation to a disposed or retired asset outside them is reported, not lost.
    Returns {"summary": the licenses block, "byAsset": asset id -> {bucket cents, lines}}.
    """
    by_license: Dict[str, List[Dict[str, Any]]] = {}
    for a in assignments:
        by_license.setdefault(a.get("licenseId"), []).append(a)
    buckets = {b: _empty_bucket() for b in BUCKETS}
    by_asset: Dict[str, Dict[str, Any]] = {}
    untracked_seats: Dict[str, int] = {}
    priced = 0
    for lic in licenses:
        held = by_license.get(lic.get("id"), [])
        if not is_priced(lic):
            for a in held:
                if a.get("targetType") == "asset" and a.get("targetId") in asset_ids:
                    untracked_seats[a["targetId"]] = untracked_seats.get(a["targetId"], 0) + 1
            continue
        priced += 1
        out = allocate_license(lic, held, asset_ids)
        b = buckets[out["bucket"]]
        if not b["hasData"]:
            b.update(spendCents=0, allocatedCents=0, unattributedCents=0, idleCents=0, allocatedToExcludedCents=0, hasData=True)
        b["licenses"] += 1
        b["spendCents"] += out["spendCents"]
        b["unattributedCents"] += out["unattributedCents"]
        b["idleCents"] += out["idleCents"]
        for asset_id, cents in out["allocated"].items():
            b["allocatedCents"] += cents
            if asset_id not in in_scope_ids:
                b["allocatedToExcludedCents"] += cents
            entry = by_asset.setdefault(asset_id, {RECURRING: None, ONE_TIME: None, "lines": []})
            entry[out["bucket"]] = (entry[out["bucket"]] or 0) + cents
            entry["lines"].append({"licenseId": out["licenseId"], "name": out["name"], "costPeriod": out["costPeriod"],
                                   "bucket": out["bucket"], "cents": cents})
    for asset_id, n in untracked_seats.items():
        by_asset.setdefault(asset_id, {RECURRING: None, ONE_TIME: None, "lines": []})["untrackedSeats"] = n
    return {"summary": {"coverage": {"total": len(licenses), "priced": priced, "notTracked": len(licenses) - priced},
                        **buckets},
            "byAsset": by_asset}


def row_allocation(by_asset: Dict[str, Dict[str, Any]], asset_id: Any) -> Dict[str, Any]:
    """The license fields of one cost row: cents per bucket (None when it holds no priced seat there)."""
    entry = by_asset.get(asset_id) or {}
    lines = sorted(entry.get("lines", []), key=lambda l: (-l["cents"], str(l["name"] or ""), str(l["licenseId"])))
    return {"recurringAnnualCents": entry.get(RECURRING), "oneTimeCents": entry.get(ONE_TIME),
            "pricedSeats": len(lines), "untrackedSeats": entry.get("untrackedSeats", 0), "lines": lines}


async def load_licenses(db: Any, tenant_id: str) -> List[Dict[str, Any]]:
    return await db.licenses.find({"tenantId": tenant_id}, LICENSE_PROJECTION).to_list(length=None)


async def load_assignments(db: Any, tenant_id: str) -> List[Dict[str, Any]]:
    return await db.license_assignments.find({"tenantId": tenant_id}, ASSIGNMENT_PROJECTION).to_list(length=None)
