"""The rollout controller tick (Phase 84): one pass over every tenant with an active rollout.

Each pass settles agent results first (also while a stop is on, so what the computers already did is
never lost), halts a rollout whose approval line was denied or went unanswered, then moves each running
rollout one step: waits for a maintenance window, sends approved rows and the canary installs, raises the
approval lines, and later soaks and checks. It never writes an agent queue and never calls
``gate.decide`` while a stop is on or the tenant is Off (a stopped ``decide`` records a refused row on
every call). Plan 84-22 puts the locked background loop around ``tick``.

Raw Mongo handle with an explicit tenantId; ``scope.tenant_scope`` only wraps each tenant's pass.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .. import PLATFORM_TENANT_ID, scope, settings
from ..scope import raw
from .messages import plural
from . import (ACTIVE_STATUSES, dispatcher, health, installs, lifecycle, lines, reboots, settle, store,
               windows as windows_mod)

logger = logging.getLogger(__name__)

SETTLED = ("installed", "failed", "restarting", "healthy", "not_reached")     # a computer the ring need not wait on to install


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


def _halt_facts(verdict: health.Verdict, hosts: List[Dict[str, Any]], signals: List[Dict[str, Any]],
                ring: Dict[str, Any]) -> Dict[str, Any]:
    """The numbers and the computer name a halt sentence needs."""
    named = next((h.get("hostname") for h in hosts if h["agentId"] == verdict.host), None)
    reported = [s for s in signals if s.get("reported")]
    return {"host": named or verdict.host or "", "f": sum(1 for s in reported if s.get("failed")),
            "computers": plural(len(reported), "computer", "computers"), "limit": int(ring.get("failPct") or 0)}


async def _restarts(db, tenant_id: str, rollout: Dict[str, Any], index: int, hosts: List[Dict[str, Any]],
                    now: datetime) -> bool:
    """True while the ring's restarts are not finished (D-07): raise the Reboot line for the installed
    computers that need one, and name what the ring is waiting for. False when no computer needs a restart or
    every restart is done, so the soak can start."""
    if not any(reboots.pending(h) for h in hosts):
        return False
    if any(reboots.needs_line(h) for h in hosts):
        await reboots.raise_reboot_line(db, tenant_id, rollout, index, hosts, now)
    if any(h.get("state") == "restarting" for h in hosts):
        new = "restarting"
    else:
        new = "waiting_for_window" if await lines.has_approved(db, tenant_id, rollout["id"], index) \
            else "waiting_for_approval"
    if rollout["rings"][index].get("state") != new:
        await store.set_ring(db, tenant_id, rollout, index, {"state": new})
    return True


async def _check(db, tenant_id: str, rollout: Dict[str, Any], index: int, hosts: List[Dict[str, Any]],
                 now: datetime) -> bool:
    """Restart, soak and check the ring whose installs are all settled. True when the ring passed (go on)."""
    ring = rollout["rings"][index]
    agents = {}
    found = raw(db).agents.find({"tenantId": tenant_id, "id": {"$in": [h["agentId"] for h in hosts]}},
                                {"_id": 0, "id": 1, "lastSeen": 1, "meta.system_patching": 1, "meta.os_patches": 1,
                                 "meta.response_state": 1})
    async for agent in found:
        agents[agent["id"]] = agent
    signals = [health.host_signals(agents.get(h["agentId"]), h, now) for h in hosts]
    verdict = health.ring_verdict(signals, ring, now)
    if verdict.kind == "halt":               # a failure halts at once: no restart is asked for, no soak is waited out
        await lifecycle.halt(db, tenant_id, rollout, index, code=verdict.code, host=verdict.host, now=now,
                             facts=_halt_facts(verdict, hosts, signals, ring))
        return False
    if await _restarts(db, tenant_id, rollout, index, hosts, now):
        return False
    if ring.get("state") not in ("soaking", "checking_health"):
        soak = health.soak_end(hosts, float(ring.get("soakHours") or 0), now)
        await store.set_ring(db, tenant_id, rollout, index, {"state": "soaking", "soakEndsAt": soak})
        verdict = health.ring_verdict(signals, rollout["rings"][index], now)
    if verdict.kind == "waiting":
        return False
    await lifecycle.advance(db, tenant_id, rollout, now)
    return True


async def _ring_state(db, tenant_id: str, rollout: Dict[str, Any], index: int) -> None:
    """Name what the ring is doing while it installs: sending, waiting for a person, or waiting for the
    window to send what a person approved. A ring in its soak, passed or halted keeps that state."""
    ring = rollout["rings"][index]
    if ring.get("state") in ("soaking", "checking_health", "halted", "passed"):
        return
    states = [(h.get("state"), h.get("waitReason")) for h in await store.host_docs(db, tenant_id, rollout["id"])
              if h.get("ring") == index]
    if any(state == "installing" for state, _ in states):
        new = "installing"
    elif any(state == "waiting" and reason == "approval" for state, reason in states):
        new = "waiting_for_window" if await lines.has_approved(db, tenant_id, rollout["id"], index) \
            else "waiting_for_approval"
    else:
        new = "installing"
    if ring.get("state") != new:
        await store.set_ring(db, tenant_id, rollout, index, {"state": new})


async def _step(db, tenant_id: str, rollout: Dict[str, Any], now: datetime, counts: Dict[str, int]) -> bool:
    """Move the current ring one step. True when the rollout moved on to the next ring, so the caller
    steps again (an empty ring passes at once)."""
    index = int(rollout.get("currentRing") or 0)
    ring = rollout["rings"][index]
    hosts = [h for h in await store.host_docs(db, tenant_id, rollout["id"]) if h.get("ring") == index]
    if not hosts:
        await lifecycle.advance(db, tenant_id, rollout, now)
        return True
    if any(installs.needs_decision(h, index) for h in hosts):
        open_now = (await windows_mod.load(db, tenant_id)).open_at(now)
        if open_now is None:
            if ring.get("state") != "waiting_for_window":
                await store.set_ring(db, tenant_id, rollout, index, {"state": "waiting_for_window"})
            counts["waiting_for_window"] = counts.get("waiting_for_window", 0) + 1
            return False
        if index == 0:
            made = await installs.canary_auto(db, tenant_id, rollout, index, hosts, now, open_now[1])
        else:                  # every install after the canary waits for a person (PTCH-06)
            made = await installs.raise_ring(db, tenant_id, rollout, index, hosts, now)
        for key, value in made.items():
            counts[key] = counts.get(key, 0) + value
        await _ring_state(db, tenant_id, rollout, index)
        return False
    if any(h.get("state") not in SETTLED for h in hosts):
        await _ring_state(db, tenant_id, rollout, index)
        return False           # installing, waiting for a person, or only simulated: nothing to check yet
    return await _check(db, tenant_id, rollout, index, hosts, now)


async def _halt_on_lines(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> bool:
    """A person denied the current ring's line, or nobody answered in 24 hours: stop the rollout at the ring."""
    index = int(rollout.get("currentRing") or 0)
    closed = await lines.closed_line(db, tenant_id, rollout["id"], index)
    if closed is None:
        return False
    named = next((h.get("hostname") for h in await store.host_docs(db, tenant_id, rollout["id"])
                  if h["agentId"] == closed["host"]), None)
    return await lifecycle.halt(db, tenant_id, rollout, index, code=closed["code"], host=closed["host"], now=now,
                                facts={"host": named or closed["host"] or ""})


async def _ring(db, tenant_id: str, rollout: Dict[str, Any], now: datetime, counts: Dict[str, int]) -> None:
    for _ in range(len(rollout["rings"]) + 1):
        if rollout.get("status") != "running" or not await _step(db, tenant_id, rollout, now, counts):
            return


async def _tenant(db, tenant_id: str, now: datetime, platform_stopped: bool, counts: Dict[str, int]) -> None:
    decide = await _may_decide(db, tenant_id, platform_stopped)
    with scope.tenant_scope(tenant_id):
        for rollout in await store.active_rollouts(db, tenant_id, ACTIVE_STATUSES):
            await settle.settle(db, tenant_id, rollout, now)
            late = await reboots.settle(db, tenant_id, rollout, now)
            if rollout.get("status") == "running" and late is not None:
                await lifecycle.halt(db, tenant_id, rollout, int(late.get("ring") or 0), code="no_new_boot",
                                     host=late["agentId"], now=now, facts={"host": late.get("hostname") or late["agentId"]})
            if rollout.get("status") == "running":
                await _halt_on_lines(db, tenant_id, rollout, now)       # needs no decision, so it works under a stop
            if decide and rollout.get("status") == "running":
                sent = await dispatcher.dispatch_approved(db, tenant_id, rollout, now)
                counts["dispatched"] = counts.get("dispatched", 0) + sent["sent"]
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
