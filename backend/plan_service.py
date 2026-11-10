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
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

import licensing
import plan_trial

PLAN_KEYS = ("Free", "Pro", "Enterprise", "Custom")
PLATFORM_TENANT_ID = "platform-admin"
COLLECTION = "plans"

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
