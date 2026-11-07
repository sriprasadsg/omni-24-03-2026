"""The rollout controller tick (Phase 84): one pass over every tenant with an active rollout.

Each pass (also over a completed rollout that still tracks computers it never reached, and a cancelled one whose
revert is still running) settles agent results first (also while a stop is on, so what the computers already did is
never lost), halts a rollout whose approval line was denied or went unanswered, then moves each running
rollout one step: waits for a maintenance window, sends approved rows and the canary installs, raises the
approval lines, and later soaks and checks. It never writes an agent queue and never calls
``gate.decide`` while a stop is on or the tenant is Off (a stopped ``decide`` records a refused row on
every call). A running rollout with ``cancelRequested`` is only settled and then ended by ``cancelling.tick``: no decision, no ring
verdict, no halt (plan 84-28). A running rollout is marked ``stoppedSince`` while a stop is on, so a card that ran out meanwhile is not
read as a denial; settle gives the computers of cancelled or stop-expired rows back to waiting, and the first pass after
the stop clears clears the mark and decides for them again as a new attempt. A simulation rollout (``shadow``) records
what it would do and is never sent, restarted or reverted. Plan 84-22 puts the locked background loop around ``tick``.

Raw Mongo handle with an explicit tenantId; ``scope.tenant_scope`` only wraps each tenant's pass.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .. import PLATFORM_TENANT_ID, agent_support, scope, settings
from ..scope import raw
from . import (ACTIVE_STATUSES, cancelling, dispatcher, health, installs, lifecycle, lines, reboots, revert, settle,
               signals, store, windows as windows_mod)

logger = logging.getLogger(__name__)

SETTLED = ("installed", "failed", "restarting", "healthy", "not_reached")     # a computer the ring need not wait on to install
SIMULATED = ("would_install", "would_restart")          # a computer with a shadow row ("would have done")


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


async def _stopped_since(db, tenant_id: str, platform_since: Optional[datetime], now: datetime) -> Optional[datetime]:
    """When the stop in force for the tenant began (the earlier of the platform and tenant stops), else None. A stop
    document with no readable press time counts from ``now``."""
    found = [platform_since] if platform_since is not None else []
    stop = (await settings.load(db, tenant_id)).stop
    if settings.stop_active(stop):
        found.append(store.parse_time(stop.get("pressedAt")) or now)
    return min(found) if found else None


async def _shadow_on(db, tenant_id: str) -> bool:
    """True while shadow mode is in force for the tenant (the deployment switch or the organization's own)."""
    return settings.shadow_state(await settings.load(db, tenant_id))[0]


async def _release_shadow(db, tenant_id: str, rollout: Dict[str, Any]) -> None:
    """A live rollout whose organization was in shadow mode and no longer is: the computers that only have a shadow
    row go back to what they were before it, so the next pass decides for them again as a new attempt (the shadow row
    already counted the attempt, so the dedupe key is new). A simulation is never released (research pitfall 5)."""
    gone = "not_reached" if rollout.get("status") == "completed" else "waiting"
    base = {"tenantId": tenant_id, "rolloutId": rollout["id"], "active": True}
    await store.hosts(db).update_many({**base, "state": "would_install"}, {"$set": {
        "state": gone, "installActionId": None, "installJobId": None, "waitReason": None}})
    await store.hosts(db).update_many({**base, "state": "would_restart"}, {"$set": {"state": "installed"}})


async def _simulate(db, tenant_id: str, rollout: Dict[str, Any], index: int, hosts: List[Dict[str, Any]],
                    now: datetime) -> bool:
    """One step of a simulation ring (81 D-02): record the would-restart rows, and once every computer has a shadow row
    soak for the ring's soak hours on the real clock, then pass without health data (a simulation has none to read).
    True when the ring passed."""
    ring = rollout["rings"][index]
    if any(reboots.simulated_due(h) for h in hosts):
        await reboots.simulate_restarts(db, tenant_id, rollout, index, hosts, now)
        hosts = [h for h in await store.host_docs(db, tenant_id, rollout["id"]) if h.get("ring") == index]
    if any(h.get("state") not in SIMULATED + ("not_reached",) for h in hosts) \
            or not any(h.get("state") in SIMULATED for h in hosts):
        await _ring_state(db, tenant_id, rollout, index)
        return False
    if ring.get("state") != "soaking":
        await store.set_ring(db, tenant_id, rollout, index, {
            "state": "soaking", "soakEndsAt": now + timedelta(hours=float(ring.get("soakHours") or 0))})
        ring = rollout["rings"][index]
    ends = store.parse_time(ring.get("soakEndsAt"))
    if ends is None or store.aware(now) < ends:
        return False
    await lifecycle.advance(db, tenant_id, rollout, now)
    return True


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
    found = await signals.ring_signals(db, tenant_id, rollout, hosts, now)
    rows = health.health_rows(found, ring, now)
    counts = health.health_counts(found)
    if rows != ring.get("health") or counts != ring.get("healthCounts"):       # the card's failure-rate line reads these
        await store.set_ring(db, tenant_id, rollout, index, {"health": rows, "healthCounts": counts})
    verdict = health.ring_verdict(found, ring, now, health.required_os(rollout))
    if verdict.kind == "halt":               # a failure halts at once: no restart is asked for, no soak is waited out
        await lifecycle.halt(db, tenant_id, rollout, index, code=verdict.code, host=verdict.host, now=now,
                             facts=lifecycle.halt_facts(verdict, hosts, found, ring))
        return False
    if await _restarts(db, tenant_id, rollout, index, hosts, now):
        return False
    if ring.get("state") not in ("soaking", "checking_health"):
        soak = health.soak_end(hosts, float(ring.get("soakHours") or 0), now)
        await store.set_ring(db, tenant_id, rollout, index, {"state": "soaking", "soakEndsAt": soak})
        rows = health.health_rows(found, rollout["rings"][index], now)
        await store.set_ring(db, tenant_id, rollout, index, {"health": rows})
        verdict = health.ring_verdict(found, rollout["rings"][index], now, health.required_os(rollout))
    if verdict.kind == "waiting":
        return False
    await lifecycle.advance(db, tenant_id, rollout, now)
    return True


async def _online_ids(db, tenant_id: str, agent_ids: List[str], now: datetime) -> set:
    found = raw(db).agents.find({"tenantId": tenant_id, "id": {"$in": agent_ids}},
                                {"_id": 0, "id": 1, "status": 1, "lastSeen": 1})
    return {a["id"] async for a in found if agent_support.online(a, now)}


async def _reach(db, tenant_id: str, rollout: Dict[str, Any], index: int, hosts: List[Dict[str, Any]],
                 now: datetime) -> List[Dict[str, Any]]:
    """Computers that are never reached (D-18). While a window is open, note which computers still waiting for
    their first install were online (``lastOnlineInWindowAt``). When that window occurrence has ended, a computer
    that was not online at any tick of it is ``not_reached``: shown as such and counted in neither the reported
    nor the failed numbers. In the canary ring, a not-reached computer is tried again in a later window while an
    operating system of the rollout still has no installed computer. Returns the ring's hosts, re-read when
    anything changed."""
    ring = rollout["rings"][index]
    waiting = [h for h in hosts if installs.needs_decision(h, index)]
    window = ring.get("installWindow") if isinstance(ring.get("installWindow"), dict) else None
    lost = [h for h in hosts if h.get("state") == "not_reached"] if index == 0 else []
    if not waiting and window is None and not lost:
        return hosts
    now = store.aware(now)
    open_now = (await windows_mod.load(db, tenant_id)).open_at(now)
    changed = False
    if window is not None:
        begin, end = store.parse_time(window.get("start")), store.parse_time(window.get("end"))
        if end is None or now >= end or (open_now is not None and open_now[0] != begin):
            for h in list(waiting):
                seen = store.parse_time(h.get("lastOnlineInWindowAt"))
                if begin is not None and (seen is None or seen < begin):
                    await store.set_host(db, tenant_id, rollout["id"], h["agentId"],
                                         {"state": "not_reached", "waitReason": None, "notReachedWindow": begin,
                                          "notReachedAt": now})
                    waiting.remove(h)
                    changed = True
            await store.set_ring(db, tenant_id, rollout, index, {"installWindow": None})
            window = None
    if open_now is not None and waiting:
        if window is None:
            await store.set_ring(db, tenant_id, rollout, index, {"installWindow": {"start": open_now[0], "end": open_now[1]}})
        for agent_id in await _online_ids(db, tenant_id, [h["agentId"] for h in waiting], now):
            await store.set_host(db, tenant_id, rollout["id"], agent_id, {"lastOnlineInWindowAt": now})
    if index == 0 and open_now is not None:
        reached = {h.get("os") for h in hosts if h.get("state") in ("installed", "restarting", "healthy")}
        missing = set(health.required_os(rollout)) - reached
        for h in (h for h in hosts if h.get("state") == "not_reached" and h.get("os") in missing):
            if store.parse_time(h.get("notReachedWindow")) != open_now[0]:      # a window after the one it missed
                await store.set_host(db, tenant_id, rollout["id"], h["agentId"],
                                     {"state": "waiting", "waitReason": None, "lastOnlineInWindowAt": None,
                                      "notReachedWindow": None})
                await store.set_ring(db, tenant_id, rollout, index, {"state": "installing", "soakEndsAt": None})
                changed = True
    if not changed:
        return hosts
    return [h for h in await store.host_docs(db, tenant_id, rollout["id"]) if h.get("ring") == index]


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
    hosts = await _reach(db, tenant_id, rollout, index, hosts, now)
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
        if not rollout.get("shadow"):
            await _ring_state(db, tenant_id, rollout, index)
            return False
        hosts = [h for h in await store.host_docs(db, tenant_id, rollout["id"]) if h.get("ring") == index]
    if rollout.get("shadow"):
        return await _simulate(db, tenant_id, rollout, index, hosts, now)
    if any(h.get("state") not in SETTLED for h in hosts):
        await _ring_state(db, tenant_id, rollout, index)
        return False           # installing, waiting for a person, or only simulated: nothing to check yet
    return await _check(db, tenant_id, rollout, index, hosts, now)


async def _halt_on_lines(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> bool:
    """A person denied the current ring's line, or nobody answered in 24 hours: stop the rollout at the ring. A card
    that ran out while a stop was on is not an answer (``stoppedSince``), and neither is one the settle pass already
    gave back to its computer after such a stop; both are offered again instead."""
    index = int(rollout.get("currentRing") or 0)
    docs = await store.host_docs(db, tenant_id, rollout["id"])
    handled = [a for h in docs for a in h.get("lineSettled") or []]
    closed = await lines.closed_line(db, tenant_id, rollout["id"], index, since=rollout.get("stoppedSince"),
                                     handled=handled)
    if closed is None:
        return False
    named = next((h.get("hostname") for h in docs if h["agentId"] == closed["host"]), None)
    return await lifecycle.halt(db, tenant_id, rollout, index, code=closed["code"], host=closed["host"], now=now,
                                facts={"host": named or closed["host"] or ""})


async def _ring(db, tenant_id: str, rollout: Dict[str, Any], now: datetime, counts: Dict[str, int]) -> None:
    for _ in range(len(rollout["rings"]) + 1):
        if rollout.get("status") != "running" or not await _step(db, tenant_id, rollout, now, counts):
            return


async def _tail(db, tenant_id: str, rollout: Dict[str, Any], now: datetime, decide: bool, counts: Dict[str, int]) -> None:
    """A finished rollout that is still looked after. A cancelled one only settles the revert it left running. A
    completed one with computers it never reached (D-18, open question 4): settle what came back, free the claims
    of those that were reached, offer a returning computer the install as an approval inside an open window (never
    on its own), send approved ones, and close the rollout at ``closesAt``."""
    if rollout.get("status") == "cancelled":
        await lifecycle.settle_cancelled(db, tenant_id, rollout, now)
        return
    await settle.settle(db, tenant_id, rollout, now)
    await lifecycle.release_reached(db, tenant_id, rollout)
    closes = store.parse_time(rollout.get("closesAt"))
    if decide and closes is not None and now < closes:
        open_now = (await windows_mod.load(db, tenant_id)).open_at(now) is not None
        counts["raised"] = counts.get("raised", 0) + await lifecycle.offer_returning(db, tenant_id, rollout, now, open_now)
        sent = await dispatcher.dispatch_approved(db, tenant_id, rollout, now)
        counts["dispatched"] = counts.get("dispatched", 0) + sent["sent"]
    if await lifecycle.close_if_due(db, tenant_id, rollout, now):
        counts["closed"] = counts.get("closed", 0) + 1


async def _tenant(db, tenant_id: str, now: datetime, platform_since: Optional[datetime],
                  counts: Dict[str, int]) -> None:
    decide = await _may_decide(db, tenant_id, platform_since is not None)
    stopped_since = await _stopped_since(db, tenant_id, platform_since, now)
    shadow_on = await _shadow_on(db, tenant_id)
    with scope.tenant_scope(tenant_id):
        for rollout in await store.active_rollouts(db, tenant_id, ACTIVE_STATUSES):
            if stopped_since is not None and rollout.get("status") == "running" and not rollout.get("stoppedSince"):
                await store.set_rollout(db, tenant_id, rollout, {"stoppedSince": stopped_since})     # GATE-06: frozen from now on
            await settle.settle(db, tenant_id, rollout, now)
            late = await reboots.settle(db, tenant_id, rollout, now)
            if rollout.get("status") == "running" and rollout.get("cancelRequested"):
                await cancelling.tick(db, tenant_id, rollout, now)    # Cancel (D-16): settle only, decide and halt nothing
                continue
            if rollout.get("status") == "running" and late is not None:
                await lifecycle.halt(db, tenant_id, rollout, int(late.get("ring") or 0), code="no_new_boot",
                                     host=late["agentId"], now=now, facts={"host": late.get("hostname") or late["agentId"]})
            if rollout.get("status") == "running":
                await _halt_on_lines(db, tenant_id, rollout, now)       # needs no decision, so it works under a stop
            if stopped_since is None and rollout.get("stoppedSince"):
                await store.set_rollout(db, tenant_id, rollout, {"stoppedSince": None})    # the stop is over: decide again
            if rollout.get("status") == "halted" and not rollout.get("shadow"):      # PROH-84-08: a simulation reverts nothing
                await revert.tick(db, tenant_id, rollout, now, may_decide=decide)    # undo is exempt from every stop
            if decide and rollout.get("status") == "halted" and not rollout.get("shadow"):      # only the Revert restart line
                sent = await dispatcher.dispatch_approved(db, tenant_id, rollout, now)
                counts["dispatched"] = counts.get("dispatched", 0) + sent["sent"]
            if decide and rollout.get("status") == "running":
                if not rollout.get("shadow"):
                    if not shadow_on:
                        await _release_shadow(db, tenant_id, rollout)
                    sent = await dispatcher.dispatch_approved(db, tenant_id, rollout, now)
                    counts["dispatched"] = counts.get("dispatched", 0) + sent["sent"]
                await _ring(db, tenant_id, rollout, now, counts)
        for rollout in await store.tail_rollouts(db, tenant_id):
            try:
                await _tail(db, tenant_id, rollout, now, decide, counts)
            except Exception as exc:           # one finished rollout's fault never stops the next
                logger.error("autonomous_ops: rollout %s could not be tended after it finished: %s", rollout["id"], exc)


async def tick(db, *, now: Optional[datetime] = None, lost: Optional[Callable[[], bool]] = None) -> Dict[str, int]:
    """One pass over every tenant with an active rollout, in sorted order. Returns summed counts plus
    ``tenants``. ``lost`` (the lock reports it was lost) is polled between tenants."""
    now = _now(now)
    counts: Dict[str, int] = {"tenants": 0}
    platform_since: Optional[datetime] = None
    try:
        platform = await settings.platform_stop(db)
        if settings.stop_active(platform):
            platform_since = store.parse_time((platform or {}).get("pressedAt")) or now
    except Exception as exc:
        logger.error("autonomous_ops: rollout tick could not read the platform stop, only settling: %s", exc)
        platform_since = now
    found = set(await store.tenants_with_rollouts(db, ACTIVE_STATUSES)) | set(await store.tenants_with_tails(db))
    tenants: List[str] = sorted(t for t in found if t != PLATFORM_TENANT_ID)
    for tenant_id in tenants:
        if lost is not None and lost():
            logger.warning("autonomous_ops: rollout tick lost its lock, stopping this pass")
            break
        counts["tenants"] += 1
        try:
            await _tenant(db, tenant_id, now, platform_since, counts)
        except Exception as exc:       # one tenant's fault never stops the next tenant's rollout
            logger.error("autonomous_ops: rollout tick failed for tenant %s: %s", tenant_id, exc)
    return counts
