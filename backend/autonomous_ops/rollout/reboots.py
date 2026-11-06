"""Restarts of a rollout (Phase 84, D-07, D-08, D-17): the Reboot line, the boot baseline, the new-boot check.

Once every computer of a ring has settled its installs, the computers whose result says a restart is needed
(and only those) get a Reboot line: one ``reboot_host`` approval row each, with the agent's longest warning
(5 minutes, D-08). An approved row is sent by ``dispatcher`` (at once inside a window, otherwise when the next
window opens); at that moment ``record_baseline`` stores what the computer looked like before it restarted:
when the restart was sent, when it is due (sent + 300 s) and the boot time and last heartbeat it reported.

A restart is only proven by data newer than itself (PROH-84-06, T-84-26): ``is_new_boot`` needs a heartbeat
later than the due time AND a boot time more than the tolerance (120 s) after the stored baseline AND not
earlier than the moment the restart was sent minus the tolerance. A heartbeat from before the restart, or a
boot time that did not move, is never the new boot; an agent that reports no readable boot time gives no
answer, which is no data. The 30 minute wait (D-17, OQ5) starts at the due time, not at dispatch.

``settle`` reads every computer being restarted each tick (also on a halted rollout, so what the computers
did is never lost): a new boot makes the computer healthy and starts its soak, an undelivered instruction
puts the row back to be asked for again, and a computer still silent 30 minutes after the due time is marked
failed ``no_new_boot`` and handed back so the controller halts the ring.

Raw Mongo handle with an explicit tenantId only. Never writes an agent queue.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .. import ledger, messages
from ..scope import raw
from . import BOOT_TOLERANCE_SECONDS, MAX_ATTEMPTS, NEW_BOOT_WAIT, REBOOT_DELAY_SECONDS, REBOOT_REASON, start, store

logger = logging.getLogger(__name__)

COMMAND = "reboot_host"
LINE = "reboot"
_NOT_DELIVERED = ("refused", "cancelled_by_stop", "cancelled")
_AGENT_FIELDS = {"_id": 0, "id": 1, "lastSeen": 1, "meta.response_state": 1}


def reboot_params() -> Dict[str, Any]:
    """The warning every restart of a rollout gives: 5 minutes and the same message for all computers."""
    return {"delay_seconds": REBOOT_DELAY_SECONDS, "reason": REBOOT_REASON}


def _order(host: Dict[str, Any]):
    return str(host.get("hostname") or "").casefold(), host.get("agentId", "")


# ---------------------------------------------------------------- pure checks

def is_new_boot(agent: Optional[Dict[str, Any]], host: Dict[str, Any],
                tolerance: int = BOOT_TOLERANCE_SECONDS) -> Optional[bool]:
    """True when the agent's heartbeat proves a new boot after the stored restart, False when what it reports
    is still the old boot (or a heartbeat sent before the restart was due), None when the answer cannot be
    given: no readable boot time or heartbeat time, or no baseline stored for the computer."""
    if not isinstance(agent, dict):
        return None
    boot = start.boot_time_of(agent)
    seen = store.parse_time(agent.get("lastSeen"))
    baseline = host.get("baselineBootTime")
    sent = store.parse_time(host.get("dispatchedRebootAt"))
    due = store.parse_time(host.get("scheduledRestartAt"))
    if boot is None or seen is None or sent is None or due is None \
            or isinstance(baseline, bool) or not isinstance(baseline, int):
        return None
    return seen > due and boot > baseline + tolerance and boot >= sent.timestamp() - tolerance


def overdue(host: Dict[str, Any], now: datetime) -> bool:
    """True once ``now`` is past the due time plus the 30 minute wait. A restart that was never sent is not overdue."""
    due = store.parse_time(host.get("scheduledRestartAt"))
    return due is not None and store.aware(now) > due + NEW_BOOT_WAIT


def active_id(host: Dict[str, Any]) -> Optional[str]:
    """The id of the host's newest reboot row when it has not been settled yet, else None."""
    ids = (host.get("lineActionIds") or {}).get(LINE) or []
    last = ids[-1] if ids else None
    return last if last and last not in (host.get("rebootSettled") or []) else None


def needs_line(host: Dict[str, Any]) -> bool:
    """An installed computer that must restart, has no reboot row waiting or running and may still be asked."""
    return (host.get("state") == "installed" and bool(host.get("rebootNeeded")) and active_id(host) is None
            and int(host.get("rebootAttempts") or 0) < MAX_ATTEMPTS)


def pending(host: Dict[str, Any]) -> bool:
    """True while the computer's restart is not finished: waiting for a person or the window, or restarting."""
    return host.get("state") == "restarting" or (host.get("state") == "installed" and bool(host.get("rebootNeeded")))


# ---------------------------------------------------------------- the Reboot line and the baseline

async def raise_reboot_line(db, tenant_id: str, rollout: Dict[str, Any], ring: int, hosts: List[Dict[str, Any]],
                            now: datetime) -> Dict[str, int]:
    """One approval row per computer of the ring that needs a restart, in (hostname, agent id) order. Returns
    the counts of ``lines.raise_line``. The caller must not call this while a stop is on."""
    from . import lines            # lines imports dispatcher, which imports this module
    entries = [(h, COMMAND, reboot_params()) for h in sorted(hosts, key=_order)
               if h.get("ring") == ring and needs_line(h)]
    if not entries:
        return {"raised": 0, "simulated": 0, "skipped": 0}
    return await lines.raise_line(db, tenant_id, rollout, ring, LINE, entries, now)


async def record_baseline(db, tenant_id: str, host: Dict[str, Any], agent: Optional[Dict[str, Any]],
                          dispatched_at: datetime) -> None:
    """Store the restart's baseline on the computer's rollout document and mark it restarting. ``host`` holds
    ``rolloutId`` and ``agentId``; ``agent`` is read when not given. An agent with no readable boot time stores
    None, so the restart can never be proven (fail closed)."""
    if agent is None:
        agent = await raw(db).agents.find_one({"id": host["agentId"], "tenantId": tenant_id}, _AGENT_FIELDS)
    agent = agent or {}
    sent = store.aware(dispatched_at)
    await store.set_host(db, tenant_id, host["rolloutId"], host["agentId"], {
        "state": "restarting", "waitReason": None, "dispatchedRebootAt": sent,
        "scheduledRestartAt": sent + timedelta(seconds=REBOOT_DELAY_SECONDS),
        "baselineBootTime": start.boot_time_of(agent), "baselineLastSeen": store.parse_time(agent.get("lastSeen"))})


async def record_revert_baseline(db, tenant_id: str, host: Dict[str, Any], agent: Optional[Dict[str, Any]],
                                 dispatched_at: datetime) -> None:
    """The same baseline for a Revert restart, kept apart (``revertRestart``) and without touching the computer's
    state: it is Reverted or Not reverted, and a restart does not turn that into Healthy."""
    if agent is None:
        agent = await raw(db).agents.find_one({"id": host["agentId"], "tenantId": tenant_id}, _AGENT_FIELDS)
    sent = store.aware(dispatched_at)
    await store.set_host(db, tenant_id, host["rolloutId"], host["agentId"], {"revertRestart": {
        "dispatchedAt": sent, "scheduledAt": sent + timedelta(seconds=REBOOT_DELAY_SECONDS),
        "baselineBootTime": start.boot_time_of(agent or {}), "done": None}})


# ---------------------------------------------------------------- settling

async def _instruction_status(db, tenant_id: str, instruction_id: Optional[str]) -> Optional[str]:
    if not instruction_id:
        return None
    doc = await raw(db).agent_instructions.find_one({"id": instruction_id, "tenantId": tenant_id}, {"_id": 0, "status": 1})
    status = (doc or {}).get("status")
    return status.strip().lower() if isinstance(status, str) else None


async def _not_delivered(db, tenant_id: str, rollout_id: str, host: Dict[str, Any], action_id: str) -> None:
    """The restart never reached the computer: ask again as a new card, at most MAX_ATTEMPTS in all."""
    attempts = int(host.get("rebootAttempts") or 0) + 1
    fields: Dict[str, Any] = {"rebootSettled": list(host.get("rebootSettled") or []) + [action_id],
                              "rebootAttempts": attempts, "state": "installed"}
    if attempts >= MAX_ATTEMPTS:
        fields.update({"state": "failed", "failureMessage": messages.REASON_TEXT["rollout_not_delivered"]})
    await store.set_host(db, tenant_id, rollout_id, host["agentId"], fields)


async def _settle_host(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any], now: datetime) -> bool:
    """Settle one computer's newest reboot row. True when the computer is overdue and was marked failed."""
    action_id = active_id(host)
    row = await ledger.get(db, tenant_id, action_id) if action_id else None
    if row is None:
        return False
    state = row.get("state")
    if state in ("failed", "cancelled_by_stop", "cancelled", "refused"):
        await _not_delivered(db, tenant_id, rollout["id"], host, action_id)
        return False
    if state != "dispatching":
        return False                    # waiting for a person or the window; denied and expired rows halt the ring
    if await _instruction_status(db, tenant_id, (row.get("instructionIds") or [None])[-1]) in _NOT_DELIVERED:
        await ledger.transition(db, tenant_id, action_id, ("dispatching",), "failed", reasonCode="rollout_not_delivered",
                                reasonText=messages.REASON_TEXT["rollout_not_delivered"])
        await _not_delivered(db, tenant_id, rollout["id"], host, action_id)
        return False
    if host.get("state") != "restarting":
        return False                    # the baseline is not stored yet: nothing can be compared
    agent = await raw(db).agents.find_one({"id": host["agentId"], "tenantId": tenant_id}, _AGENT_FIELDS)
    settled = list(host.get("rebootSettled") or []) + [action_id]
    if is_new_boot(agent, host) is True:
        due = store.parse_time(host.get("scheduledRestartAt"))
        booted = datetime.fromtimestamp(start.boot_time_of(agent), tz=timezone.utc)
        await store.set_host(db, tenant_id, rollout["id"], host["agentId"], {
            "state": "healthy", "rebootSettled": settled, "newBootTime": start.boot_time_of(agent),
            "newBootAt": max(booted, due)})        # the restart was never earlier than it was due
        await ledger.transition(db, tenant_id, action_id, ("dispatching",), "executed", reasonCode="rollout_restarted",
                                reasonText=messages.REASON_TEXT["rollout_restarted"])
        return False
    if overdue(host, now):
        await store.set_host(db, tenant_id, rollout["id"], host["agentId"], {
            "state": "failed", "rebootSettled": settled, "failureCode": "no_new_boot",
            "failureMessage": messages.REASON_TEXT["rollout_no_new_boot"], "waitReason": None})
        await ledger.transition(db, tenant_id, action_id, ("dispatching",), "failed", reasonCode="rollout_no_new_boot",
                                reasonText=messages.REASON_TEXT["rollout_no_new_boot"])
        return True
    return False


async def settle(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> Optional[Dict[str, Any]]:
    """Settle every computer of the rollout that has a reboot row in flight. Returns the first computer
    (hostname, agent id) that is now overdue, as its host document, else None. One computer's fault is logged
    and does not stop the others."""
    late: List[Dict[str, Any]] = []
    for host in await store.host_docs(db, tenant_id, rollout["id"]):
        if host.get("state") not in ("installed", "restarting") or active_id(host) is None:
            continue
        try:
            if await _settle_host(db, tenant_id, rollout, host, now):
                late.append(host)
        except Exception as exc:
            logger.error("autonomous_ops: rollout %s could not settle the restart of %s: %s", rollout["id"],
                         host["agentId"], exc)
    return sorted(late, key=_order)[0] if late else None
