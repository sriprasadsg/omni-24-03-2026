"""The rollout controller tick (Phase 84): one pass over every tenant with an active rollout.

Each pass settles agent results first (also while a stop is on, so what the computers already did is
never lost), then moves each running rollout one step: waits for a maintenance window, sends the
canary installs, and later soaks and checks. It never writes an agent queue and never calls
``gate.decide`` while a stop is on or the tenant is Off (a stopped ``decide`` records a refused row on
every call). Plan 84-22 puts the locked background loop around ``tick``.

Raw Mongo handle with an explicit tenantId; ``scope.tenant_scope`` only wraps each tenant's pass.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .. import PLATFORM_TENANT_ID, scope, settings
from ..scope import raw
from . import ACTIVE_STATUSES, health, installs, lifecycle, settle, store, windows as windows_mod

logger = logging.getLogger(__name__)


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)       # BSON datetimes are milliseconds


async def _may_decide(db, tenant_id: str, platform_stopped: bool) -> bool:
    """True when new decisions may be made for the tenant: no platform or tenant stop and not Off."""
    if platform_stopped:
        return False
    tenant = await settings.load(db, tenant_id)
    return not settings.stop_active(tenant.stop) and settings.effective_level(tenant) != "off"


async def _halt(db, tenant_id: str, rollout: Dict[str, Any], index: int, verdict: health.Verdict,
                now: datetime) -> None:
    """Stop the rollout at this ring (plan 84-03 moves this into ``lifecycle``)."""
    await store.set_ring(db, tenant_id, rollout, index, {"state": "halted"})
    await store.set_rollout(db, tenant_id, rollout, {
        "status": "halted", "haltReason": {"code": verdict.code, "ring": index, "host": verdict.host, "at": now}})


async def _check(db, tenant_id: str, rollout: Dict[str, Any], index: int, hosts: List[Dict[str, Any]],
                 now: datetime) -> bool:
    """Soak and check the ring whose installs are all settled. True when the ring passed (go on)."""
    ring = rollout["rings"][index]
    if ring.get("state") not in ("soaking", "checking_health"):
        soak = health.soak_end(hosts, float(ring.get("soakHours") or 0), now)
        await store.set_ring(db, tenant_id, rollout, index, {"state": "soaking", "soakEndsAt": soak})
    agents = {}
    found = raw(db).agents.find({"tenantId": tenant_id, "id": {"$in": [h["agentId"] for h in hosts]}},
                                {"_id": 0, "id": 1, "lastSeen": 1, "meta.system_patching": 1, "meta.os_patches": 1})
    async for agent in found:
        agents[agent["id"]] = agent
    signals = [health.host_signals(agents.get(h["agentId"]), h, now) for h in hosts]
    verdict = health.ring_verdict(signals, ring, now)
    if verdict.kind == "waiting":
        return False
    if verdict.kind == "halt":
        await _halt(db, tenant_id, rollout, index, verdict, now)
        return False
    await lifecycle.advance(db, tenant_id, rollout, now)
    return True


async def _step(db, tenant_id: str, rollout: Dict[str, Any], now: datetime, counts: Dict[str, int]) -> bool:
    """Move the current ring one step. True when the rollout moved on to the next ring, so the caller
    steps again (an empty ring passes at once)."""
    index = int(rollout.get("currentRing") or 0)
    ring = rollout["rings"][index]
    hosts = [h for h in await store.host_docs(db, tenant_id, rollout["id"]) if h.get("ring") == index]
    if not hosts:
        await lifecycle.advance(db, tenant_id, rollout, now)
        return True
    waiting = [h for h in hosts if h.get("state") == "waiting"]
    if waiting:
        open_now = (await windows_mod.load(db, tenant_id)).open_at(now)
        if open_now is None:
            if ring.get("state") != "waiting_for_window":
                await store.set_ring(db, tenant_id, rollout, index, {"state": "waiting_for_window"})
            counts["waiting_for_window"] = counts.get("waiting_for_window", 0) + 1
            return False
        if ring.get("state") != "installing":
            await store.set_ring(db, tenant_id, rollout, index, {"state": "installing"})
        if index == 0:         # later rings wait for a person (plan 84-03)
            sent = await installs.canary_auto(db, tenant_id, rollout, index, hosts, now, open_now[1])
            for key, value in sent.items():
                counts[key] = counts.get(key, 0) + value
        return False
    if any(h.get("state") not in ("installed", "failed") for h in hosts):
        return False           # still installing (or only simulated): nothing to check yet
    return await _check(db, tenant_id, rollout, index, hosts, now)


async def _ring(db, tenant_id: str, rollout: Dict[str, Any], now: datetime, counts: Dict[str, int]) -> None:
    for _ in range(len(rollout["rings"]) + 1):
        if rollout.get("status") != "running" or not await _step(db, tenant_id, rollout, now, counts):
            return


async def _tenant(db, tenant_id: str, now: datetime, platform_stopped: bool, counts: Dict[str, int]) -> None:
    decide = await _may_decide(db, tenant_id, platform_stopped)
    with scope.tenant_scope(tenant_id):
        for rollout in await store.active_rollouts(db, tenant_id, ACTIVE_STATUSES):
            await settle.settle(db, tenant_id, rollout, now)
            if decide and rollout.get("status") == "running":
                await _ring(db, tenant_id, rollout, now, counts)


async def tick(db, *, now: Optional[datetime] = None, lost: Optional[Callable[[], bool]] = None) -> Dict[str, int]:
    """One pass over every tenant with an active rollout, in sorted order. Returns summed counts plus
    ``tenants``. ``lost`` (the lock reports it was lost) is polled between tenants."""
    now = _now(now)
    counts: Dict[str, int] = {"tenants": 0}
    try:
        platform_stopped = settings.stop_active(await settings.platform_stop(db))
    except Exception as exc:
        logger.error("autonomous_ops: rollout tick could not read the platform stop, only settling: %s", exc)
        platform_stopped = True
    tenants: List[str] = [t for t in await store.tenants_with_rollouts(db, ACTIVE_STATUSES) if t != PLATFORM_TENANT_ID]
    for tenant_id in tenants:
        if lost is not None and lost():
            logger.warning("autonomous_ops: rollout tick lost its lock, stopping this pass")
            break
        counts["tenants"] += 1
        try:
            await _tenant(db, tenant_id, now, platform_stopped, counts)
        except Exception as exc:       # one tenant's fault never stops the next tenant's rollout
            logger.error("autonomous_ops: rollout tick failed for tenant %s: %s", tenant_id, exc)
    return counts
