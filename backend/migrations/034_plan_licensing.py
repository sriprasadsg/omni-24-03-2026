"""Migration 034: plan licensing go-live (Phase 88, D-08, D-18, D-22, D-34, D-41, D-46).

In this order: (a) the four plan documents (seats, trial days, screens from the committed seed); (b) every
tenant's plan stored in its canonical spelling; (c) each DIRECT tenant gets its plan's seats, the old number
recorded first as ``license.maxAgentsBeforePlans`` with one ``plan.seats_adopted`` audit entry, and a number
that is neither the old default 5 nor the plan's (or any Custom tenant's) kept as ``license.seatOverride``;
(d) every tenant without a trial gets one (a 14-day Free trial starting now, else a consumed one);
(e) every tenant without allowed networks gets the public addresses of its admitted agents;
(f) the hardware indexes. The platform organization and partner organizations are skipped everywhere; partner
customers keep their seats (the partner's allotment). No tenant's screen list is touched, nothing is deleted,
and a second run changes nothing.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Plan licensing (Phase 88): plan table, plan seats, trials, allowed networks, hardware indexes."

logger = logging.getLogger(__name__)

ACTOR = "migration 034"
_NOT_PLATFORM_OR_PARTNER = {"type": {"$ne": "partner"}, "id": {"$ne": "platform-admin"}}


async def _seed_plans(raw, now: str) -> int:
    import plan_service
    import screen_ceiling

    added = 0
    for key in plan_service.PLAN_KEYS:
        stored = plan_service.DEFAULT_PLANS[key]
        screens = "all" if key == "Custom" else screen_ceiling.seed_screens(key)
        res = await raw[plan_service.COLLECTION].update_one(
            {"key": key},
            {"$setOnInsert": {"key": key, "seats": stored["seats"], "trialDays": stored["trialDays"],
                              "screens": screens, "updatedAt": now, "updatedBy": ACTOR}},
            upsert=True)
        added += 1 if res.upserted_id else 0
    return added


async def _normalize_plans(raw) -> int:
    import plan_service

    changed = 0
    async for tenant in raw.tenants.find(_NOT_PLATFORM_OR_PARTNER, {"_id": 0, "id": 1, "subscriptionTier": 1}):
        stored = tenant.get("subscriptionTier")
        if "subscriptionTier" not in tenant:
            key, guard = "Free", {"$exists": False}
        else:
            key, guard = plan_service.normalize_plan(stored), stored
        if key is None or key == stored:
            continue
        res = await raw.tenants.update_one({"id": tenant["id"], "subscriptionTier": guard},
                                           {"$set": {"subscriptionTier": key}})
        changed += res.modified_count
    return changed


async def _adopt_seats(db, raw) -> int:
    import audit_ledger
    import licensing
    import plan_service

    stored_plans = await plan_service.plans(db)
    adopted = 0
    async for tenant in raw.tenants.find(licensing._direct_filter(), {"_id": 0}):
        key = plan_service.plan_key_of(tenant)
        previous = licensing.license_of(tenant)["maxAgents"]
        plan_seats = stored_plans[key].get("seats")
        usable = isinstance(plan_seats, int) and not isinstance(plan_seats, bool) and plan_seats >= 0
        keep = key == "Custom" or not usable or previous not in (licensing.DEFAULT_MAX_AGENTS, plan_seats)
        if not await licensing.adopt_plan_seats(db, tenant["id"], seats=plan_seats if usable else previous,
                                                override=previous if keep else None, previous=previous):
            continue
        adopted += 1
        after = licensing.license_of(await raw.tenants.find_one({"id": tenant["id"]}, {"_id": 0}))["maxAgents"]
        try:
            await audit_ledger.event("plan.seats_adopted", tenant["id"], actor={"email": ACTOR}, db=raw,
                                     plan=key, before=previous, after=after)
        except Exception as exc:  # the record is best effort; the old number is on the tenant already
            logger.warning("migration 034: audit entry for %s not written: %s", tenant["id"], exc)
    return adopted


async def _start_trials(raw, now: datetime, stored_plans: Dict[str, Dict[str, Any]]) -> int:
    import plan_service
    import plan_trial

    days = stored_plans["Free"].get("trialDays")
    free_days = days if isinstance(days, int) and not isinstance(days, bool) and days >= 0 else None
    started = 0
    flt = {**_NOT_PLATFORM_OR_PARTNER, plan_trial.FIELD: {"$exists": False}}
    async for tenant in raw.tenants.find(flt, {"_id": 0, "id": 1, "subscriptionTier": 1}):
        free = plan_service.plan_key_of(tenant) == "Free" and free_days is not None
        record = plan_trial.new_trial(now, free_days) if free else plan_trial.consumed_trial(now)
        res = await raw.tenants.update_one({"id": tenant["id"], plan_trial.FIELD: {"$exists": False}},
                                           {"$set": {plan_trial.FIELD: record}})
        started += res.modified_count
    return started


def _public_networks(agents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    import network_rules

    found: Dict[str, Any] = {}
    for agent in agents:
        for field in ("publicIp", "sourceIp"):
            ip = network_rules.normalize_ip(agent.get(field))
            if ip is None or not ip.is_global:
                continue
            cidr = network_rules.network_of(ip)
            found.setdefault(cidr, agent.get("hostname"))
    return [network_rules.entry(cidr, source="migrated", hostname=host)
            for cidr, host in list(found.items())[:network_rules.MAX_NETWORKS]]


async def _allow_networks(raw) -> int:
    seeded = 0
    flt = {**_NOT_PLATFORM_OR_PARTNER, "allowedNetworks": {"$exists": False}}
    async for tenant in raw.tenants.find(flt, {"_id": 0, "id": 1}):
        agents = await raw.agents.find(
            {"tenantId": tenant["id"], "status": {"$nin": ["Pending", "Rejected"]}},
            {"_id": 0, "hostname": 1, "publicIp": 1, "sourceIp": 1}).sort("hostname", 1).to_list(None)
        entries = _public_networks(agents)
        if not entries:
            continue
        res = await raw.tenants.update_one({"id": tenant["id"], "allowedNetworks": {"$exists": False}},
                                           {"$set": {"allowedNetworks": entries}})
        seeded += res.modified_count
    return seeded


async def up(db: AsyncIOMotorDatabase) -> None:
    import cross_tenant
    import plan_service

    raw = getattr(db, "_db", db)
    now = datetime.now(timezone.utc)
    plans_added = await _seed_plans(raw, now.isoformat())
    plans_fixed = await _normalize_plans(raw)
    seats = await _adopt_seats(db, raw)
    trials = await _start_trials(raw, now, await plan_service.plans(db))
    networks = await _allow_networks(raw)
    await cross_tenant.ensure_indexes(db)
    logger.info("migration 034: %d plans added, %d plan names set, %d tenants on plan seats, %d trials, "
                "%d tenants with allowed networks", plans_added, plans_fixed, seats, trials, networks)
