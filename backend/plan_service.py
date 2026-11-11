"""Plans as stored data (Phase 88, D-03, D-14).

The stored ``plans`` collection (one document per plan key) decides a direct tenant's seats and its
Free trial at creation and at enrollment. The tenant's licence ``maxAgents`` stays the one effective seat
number every reader uses (licensing.py owns every write of it); the plan table is the source it is derived
from for direct tenants, and an explicit seat number or a partner allotment is the named exception
(``license.seatOverride``). The old code constants (billing_service.SUBSCRIPTION_LIMITS,
feature_flags.FEATURE_TIERS) are references only and are not enforced here.

The platform-admin organization is exempt from plan, trial, network and seat limits (D-26, D-41).
A tenant with no ``subscriptionTier`` reads as Free; an empty plans collection reads the D-03
defaults, so a fresh database behaves like a seeded one.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import licensing
import plan_trial

logger = logging.getLogger(__name__)

PLAN_KEYS = ("Free", "Pro", "Enterprise", "Custom")
PLATFORM_TENANT_ID = "platform-admin"
COLLECTION = "plans"
MAX_PLAN_SCREENS = 300
EDITABLE_FIELDS = ("seats", "trialDays", "screens")

DEFAULT_PLANS: Dict[str, Dict[str, Any]] = {
    "Free": {"key": "Free", "seats": 5, "trialDays": 14},
    "Pro": {"key": "Pro", "seats": 50, "trialDays": None},
    "Enterprise": {"key": "Enterprise", "seats": 500, "trialDays": None},
    "Custom": {"key": "Custom", "seats": None, "trialDays": None},
}


def _raw(db):
    return getattr(db, "_db", db)


class PlanError(ValueError):
    """A plan request that cannot be honoured; ``status`` is the HTTP answer, ``args[0]`` its text."""

    def __init__(self, status: int, code: str, message: Optional[str] = None):
        super().__init__(message or code)
        self.status = status
        self.code = code


def normalize_plan(value: Any) -> Optional[str]:
    """The canonical plan key for ``value`` (case-insensitive), or None when it is not a plan."""
    if not isinstance(value, str):
        return None
    wanted = value.strip().lower()
    return next((key for key in PLAN_KEYS if key.lower() == wanted), None)


def plan_key_of(tenant: Optional[Dict[str, Any]]) -> str:
    """The tenant's plan; a missing or unknown value reads as Free."""
    return normalize_plan((tenant or {}).get("subscriptionTier")) or "Free"


def is_exempt(tenant_or_id: Union[Dict[str, Any], str, None]) -> bool:
    """True for the platform-admin organization (D-26)."""
    tenant_id = tenant_or_id.get("id") if isinstance(tenant_or_id, dict) else tenant_or_id
    return tenant_id == PLATFORM_TENANT_ID


async def plans(db) -> Dict[str, Dict[str, Any]]:
    """All four plans: each stored document laid over its D-03 default."""
    out = {key: dict(DEFAULT_PLANS[key]) for key in PLAN_KEYS}
    async for doc in _raw(db)[COLLECTION].find({}, {"_id": 0}):
        key = normalize_plan(doc.get("key"))
        if key:
            out[key].update({**doc, "key": key})
    return out


async def plan_doc(db, key: str) -> Optional[Dict[str, Any]]:
    canonical = normalize_plan(key)
    return (await plans(db))[canonical] if canonical else None


async def ensure_plans(db) -> None:
    """Insert each missing default plan; a plan an administrator has changed is never overwritten."""
    now = datetime.now(timezone.utc).isoformat()
    for key in PLAN_KEYS:
        await _raw(db)[COLLECTION].update_one(
            {"key": key}, {"$setOnInsert": {**DEFAULT_PLANS[key], "updatedAt": now, "updatedBy": "system"}},
            upsert=True)


async def new_tenant_terms(db, plan: Optional[str], max_agents: Optional[int]) -> Dict[str, Any]:
    """Seats, seat override and trial for a tenant created on ``plan`` (D-03, D-09, D-17, D-22, D-23)."""
    key = normalize_plan("Free" if plan is None else plan)
    if key is None:
        raise PlanError(422, "unknown_plan", f"Unknown plan {str(plan)[:40]!r}; use Free, Pro, Enterprise or Custom")
    stored = (await plans(db))[key]
    if max_agents is not None:
        seats, override = max_agents, max_agents
    elif key == "Custom" or not isinstance(stored.get("seats"), int):
        raise PlanError(422, "seats_required", "Custom plans need a seat number")
    else:
        seats, override = stored["seats"], None
    now = datetime.now(timezone.utc)
    days = stored.get("trialDays")
    free_trial = key == "Free" and isinstance(days, int) and not isinstance(days, bool) and days >= 0
    trial = plan_trial.new_trial(now, days) if free_trial else plan_trial.consumed_trial(now)
    return {"plan": key, "max_agents": seats, "seat_override": override, "trial": trial}


async def change_plan(db, tenant_id: str, new_plan: Any, *, actor: Any, via: str,
                      partner_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The one function that changes a tenant's ``subscriptionTier`` (D-13, D-25; plan_writers_scan keeps it so).

    A compare-and-set on the stored value, then the seat rule (D-10, D-11: only a direct tenant without an
    override takes the new plan's seats; a move to Custom keeps the current number as the override, D-17),
    a consumed trial when the tenant has no trial record (D-22), an audit entry and a notice for the tenant's
    admins. The platform organization is refused (D-26). With ``partner_doc`` the tenant must be that
    partner's customer and the plan inside ``partner.planCeiling`` (absent: Free only)."""
    import plan_notices  # lazy: keeps this module's import graph as small as it was
    key = normalize_plan(new_plan)
    if key is None:
        raise PlanError(422, "unknown_plan", f"Unknown plan {str(new_plan)[:40]!r}; use Free, Pro, Enterprise or Custom")
    raw = _raw(db)
    tenant = await raw.tenants.find_one({"id": tenant_id, "type": {"$ne": "partner"}}, {"_id": 0})
    if tenant is None:
        raise PlanError(404, "not_found", "Tenant not found")
    if is_exempt(tenant_id):
        raise PlanError(409, "platform_exempt", "The platform organization has no plan to change")
    if partner_doc is not None:
        if tenant.get("partnerId") != partner_doc.get("id"):
            raise PlanError(404, "not_found", "Tenant not found")
        ceiling = (partner_doc.get("partner") or {}).get("planCeiling") or ["Free"]
        if key not in {normalize_plan(p) for p in ceiling}:
            raise PlanError(422, "plan_outside_ceiling", f"The {key} plan is outside your plan ceiling.")
    old = plan_key_of(tenant)
    if key == old:
        return {"changed": False, "plan": key}

    stored = tenant.get("subscriptionTier")
    now = datetime.now(timezone.utc)
    no_trial = {} if isinstance(tenant.get(plan_trial.FIELD), dict) else {plan_trial.FIELD: plan_trial.consumed_trial(now)}
    won = await raw.tenants.update_one(
        {"id": tenant_id, "subscriptionTier": stored if "subscriptionTier" in tenant else {"$exists": False}},
        {"$set": {"subscriptionTier": key, "updatedAt": now.isoformat(), **no_trial}})
    if won.matched_count == 0:
        raise PlanError(409, "plan_changed", "The plan changed while you were saving. Try again.")

    seats_before = licensing.license_of(tenant)["maxAgents"]
    override = (tenant.get("license") or {}).get("seatOverride")
    if not tenant.get("partnerId") and not (isinstance(override, int) and not isinstance(override, bool)):
        plan_seats = (await plans(db))[key].get("seats")
        if key == "Custom":
            await licensing.set_seat_override(db, tenant_id, seats_before)
        elif isinstance(plan_seats, int):
            await licensing.set_plan_seats(db, tenant_id, plan_seats)
    seats_after = licensing.license_of(await raw.tenants.find_one({"id": tenant_id}, {"_id": 0}))["maxAgents"]

    name = tenant.get("name") or tenant_id
    await plan_notices.announce(db, tenant_id, event="plan.changed", title="Plan changed",
                                message=f"{name} moved from {old} to {key}", actor=actor,
                                before=old, after=key, via=via)
    if seats_after != seats_before:
        await plan_notices.announce(db, tenant_id, event="seats.changed", title="Seat limit changed",
                                    message=f"{name} now has {seats_after} seats (was {seats_before})", actor=actor,
                                    before=seats_before, after=seats_after, via=via)
    if partner_doc is not None:
        import partner_store  # lazy: it imports license_rules, which imports this module
        await partner_store.audit("partner.customer_plan_changed", actor=actor, partner_id=partner_doc["id"],
                                  customerId=tenant_id, before=old, after=key)
    return {"changed": True, "from": old, "to": key, "licence": await licence_view(db, tenant_id)}


async def _tenant_counts(db) -> Dict[str, int]:
    """Tenants per plan (a missing or unknown plan reads as Free); the platform and partner organizations are not counted."""
    counts = {key: 0 for key in PLAN_KEYS}
    rows = _raw(db).tenants.aggregate([
        {"$match": {"type": {"$ne": "partner"}, "id": {"$ne": PLATFORM_TENANT_ID}}},
        {"$group": {"_id": "$subscriptionTier", "n": {"$sum": 1}}}])
    async for row in rows:
        counts[normalize_plan(row["_id"]) or "Free"] += row["n"]
    return counts


def _screens_of(key: str, doc: Dict[str, Any]) -> Union[str, List[str]]:
    import screen_ceiling  # lazy: screen_ceiling imports this module
    if key == "Custom" or doc.get("screens") == "all":
        return "all"
    stored = doc.get("screens")
    return [s for s in stored if isinstance(s, str)] if isinstance(stored, list) else screen_ceiling.seed_screens(key)


def _entry(key: str, doc: Dict[str, Any], count: int) -> Dict[str, Any]:
    return {"key": key, "seats": doc.get("seats"), "trialDays": doc.get("trialDays"), "screens": _screens_of(key, doc),
            "tenantCount": count, "updatedAt": doc.get("updatedAt"), "updatedBy": doc.get("updatedBy")}


async def list_plans(db) -> List[Dict[str, Any]]:
    """The four plans in order for the Super Admin's table (D-14)."""
    stored, counts = await plans(db), await _tenant_counts(db)
    return [_entry(key, stored[key], counts[key]) for key in PLAN_KEYS]


def _clean_screens(value: Any) -> List[str]:
    import tenant_features
    if not isinstance(value, list) or len(value) > MAX_PLAN_SCREENS:
        raise PlanError(422, "invalid_screen", f"screens must be a list of at most {MAX_PLAN_SCREENS} screens")
    for item in value:
        if not isinstance(item, str) or item not in tenant_features.SWITCHABLE:
            raise PlanError(422, "invalid_screen", f"{str(item)[:60]!r} is not a screen that can be sold.")
    return list(dict.fromkeys(value))


def _clean_changes(key: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    """The editable fields of ``changes``, validated; every refusal is a 422 PlanError and nothing is stored."""
    known = {f: changes[f] for f in EDITABLE_FIELDS if f in (changes or {})}
    if not known:
        raise PlanError(422, "nothing_to_update", "Send seats, trialDays or screens.")
    if "trialDays" in known and key != "Free":
        raise PlanError(422, "trial_only_on_free", "Only the Free plan has a trial.")
    if "seats" in known:
        try:
            known["seats"] = licensing._check_seats(known["seats"])
        except ValueError as exc:
            raise PlanError(422, "invalid_seats", str(exc)) from None
    days = known.get("trialDays")
    if "trialDays" in known and (not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365):
        raise PlanError(422, "invalid_trial_days", "trialDays must be a whole number from 1 to 365.")
    if "screens" in known:
        known["screens"] = _clean_screens(known["screens"])
    return known


async def update_plan(db, key: Any, changes: Dict[str, Any], *, actor: Any) -> Dict[str, Any]:
    """Edit one plan's seats, trial days or screens (D-14); returns ``{"plan": entry, "tenantsUpdated": n}``.

    Seats are applied at once to every direct tenant on the plan without an override (licensing.apply_plan_seats;
    partner customers and the platform are never touched) and announced to their admins (D-25). Screens and
    trial days limit only what comes next (D-28): no tenant's screens or stored trial change. Custom is per
    tenant (D-17). A request that changes nothing writes, announces and records nothing."""
    import audit_ledger
    import plan_notices
    canonical = normalize_plan(key)
    if canonical is None:
        raise PlanError(422, "unknown_plan", f"Unknown plan {str(key)[:40]!r}; use Free, Pro or Enterprise")
    if canonical == "Custom":
        raise PlanError(422, "custom_is_per_tenant", "Custom is set per tenant, not here.")
    wanted = _clean_changes(canonical, changes)
    doc = (await plans(db))[canonical]
    current = {"seats": doc.get("seats"), "trialDays": doc.get("trialDays"), "screens": _screens_of(canonical, doc)}
    after = {f: v for f, v in wanted.items() if current[f] != v}
    if not after:
        return {"plan": _entry(canonical, doc, (await _tenant_counts(db))[canonical]), "tenantsUpdated": 0}
    before = {f: current[f] for f in after}

    who = getattr(actor, "username", None) or (actor if isinstance(actor, str) else None) or "system"
    defaults = {f: DEFAULT_PLANS[canonical][f] for f in ("seats", "trialDays") if f not in after}
    await _raw(db)[COLLECTION].update_one(
        {"key": canonical},
        {"$set": {**after, "updatedAt": datetime.now(timezone.utc).isoformat(), "updatedBy": who},
         "$setOnInsert": {"key": canonical, **defaults}}, upsert=True)

    ids: List[str] = []
    if "seats" in after:
        ids = await licensing.apply_plan_seats(db, canonical, after["seats"])
        for tenant_id in ids:
            await plan_notices.announce(
                db, tenant_id, event="seats.changed", title="Agent seat limit changed",
                message=f"The {canonical} plan now allows {after['seats']} agent seats (was {before['seats']}).",
                actor=actor, before=before["seats"], after=after["seats"], via="plan_edit")
    try:
        await audit_ledger.event("plan.updated", PLATFORM_TENANT_ID, actor=plan_notices._actor(actor), plan=canonical,
                                 before=before, after=after, tenantsUpdated=len(ids))
    except Exception as exc:  # the edit is made; a ledger failure must not report it as failed
        logger.warning("audit for plan.updated on %s was not recorded: %s", canonical, exc)
    entry = next(e for e in await list_plans(db) if e["key"] == canonical)
    return {"plan": entry, "tenantsUpdated": len(ids)}


async def licence_view(db, tenant_id: str) -> Dict[str, Any]:
    """The licence route's answer (D-19): the seat summary plus plan, trial and learned networks."""
    summary = await licensing.license_summary(db, tenant_id)
    tenant = await _raw(db).tenants.find_one({"id": tenant_id}) or {}
    key = plan_key_of(tenant)
    exempt = is_exempt(tenant_id)
    override = (tenant.get("license") or {}).get("seatOverride")
    if exempt:  # the platform organization has no seat limit (D-26, D-41)
        summary = {**summary, "maxAgents": None, "seatsAvailable": None, "overBy": 0}
    return {
        **summary,
        "plan": key,
        "planSeats": (await plans(db))[key].get("seats"),
        "seatOverride": override if isinstance(override, int) and not isinstance(override, bool) else None,
        "partnerManaged": bool(tenant.get("partnerId")),
        "exempt": exempt,
        "trial": plan_trial.view(tenant),
        "allowedNetworks": [{"cidr": n.get("cidr"), "source": n.get("source"), "addedAt": n.get("addedAt")}
                            for n in tenant.get("allowedNetworks") or [] if isinstance(n, dict)],
    }
