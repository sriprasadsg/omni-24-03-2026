"""How a rollout moves on and ends: pass a ring, complete, halt, resume, cancel, close (PTCH-01, D-16, D-18).

``advance`` marks the current ring passed and moves to the next; past the last ring it completes the rollout.
``complete`` sets the status and releases the claims so another rollout may take the computers. A computer that
was never reached keeps its claim and is tracked for NOT_REACHED_GRACE (7 days, research A11, open question 4):
``notReached`` lists it and ``closesAt`` is the completion plus that time. While the rollout is open a returning
computer is offered the install as an approval line in a window (``offer_returning``, never automatic); at
``closesAt`` ``close_if_due`` closes the rollout, frees the remaining claims and records ``neverReachedCount``.

``halt`` stops the rollout at a ring (R11: a failed check, a denied or an expired approval): the status moves from
running to halted with one compare-and-set, every other open row of the rollout is closed (``rollout_closed``), and
a row whose instruction nobody has fetched yet is ended (``rollout_halted``) so delivery refuses the instruction.
A computer whose instruction was already sent keeps its row, and its later result is still recorded. A halt claims
nothing back from the computers: the rings that passed keep their patches. The ring's computers that installed
something are then put back (``revert.start_ring_revert``, D-14): a failure there is logged and the controller tries
again on its next pass, the halt itself stands.

After a halt a person can only Resume or Cancel (D-16). ``resume`` needs a typed reason, runs the halted ring's
health check again on current data (the controller's own ``signals.ring_signals`` and ``health.ring_verdict``) and
continues only when it is green; a red or still-waiting check keeps the rollout halted. Nothing here removes,
excludes or counts a failed computer as passed (PROH-84-07). ``cancel`` ends the rollout: rings that did not pass are
cancelled, every claim is released, open rows expire (``rollout_closed``) and a revert that is already running is left
to finish (``revertOpen``, settled by the controller). Both leave one control row and one audit event naming the
person; if the record cannot be written the change is put back.

Raw Mongo handle with an explicit tenantId only. Reads an instruction's status; never writes the queue.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .. import agent_support, ledger, messages
from ..scope import raw
from . import DISPATCHER_NAME, NOT_REACHED_GRACE, messages as rm, store
from .messages import plural

logger = logging.getLogger(__name__)

REASON_MAX = 500
REACHED_LATER = ("installed", "restarting", "healthy", "failed")        # a returning computer that was reached after all


class LifecycleError(Exception):
    """Base of the refusals Resume and Cancel raise; the message is the sentence the route returns."""


class RolloutNotFound(LifecycleError):
    pass


class NotHalted(LifecycleError):
    pass


class RevertRunning(LifecycleError):
    pass


class ReasonRequired(LifecycleError):
    pass


def halt_facts(verdict, hosts: List[Dict[str, Any]], found: List[Dict[str, Any]], ring: Dict[str, Any]) -> Dict[str, Any]:
    """The numbers and the computer name a halt sentence needs."""
    named = next((h.get("hostname") for h in hosts if h["agentId"] == verdict.host), None)
    reported = [s for s in found if s.get("reported")]
    return {"host": named or verdict.host or "", "f": sum(1 for s in reported if s.get("failed")),
            "computers": plural(len(reported), "computer", "computers"), "limit": int(ring.get("failPct") or 0)}


async def complete(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> None:
    """The rollout is finished: status completed. Every computer's claim is released except those of computers it
    never reached; they stay listed in ``notReached`` with ``closesAt`` a week out (open question 4)."""
    hosts = await store.host_docs(db, tenant_id, rollout["id"])
    lost = [h["agentId"] for h in hosts if h.get("state") == "not_reached"]
    fields: Dict[str, Any] = {"status": "completed", "completedAt": now}
    if lost:
        fields.update({"notReached": lost, "closesAt": now + NOT_REACHED_GRACE})
    await store.set_rollout(db, tenant_id, rollout, fields)
    if lost:
        await store.release(db, tenant_id, rollout["id"], [h["agentId"] for h in hosts if h["agentId"] not in lost])
    else:
        await store.release(db, tenant_id, rollout["id"])


async def advance(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> None:
    """The current ring passed: record it and move to the next ring, or complete the rollout after the last."""
    index = int(rollout.get("currentRing") or 0)
    await store.set_ring(db, tenant_id, rollout, index, {"state": "passed", "passedAt": now})
    if index + 1 >= len(rollout["rings"]):
        await complete(db, tenant_id, rollout, now)
        return
    await store.set_rollout(db, tenant_id, rollout, {"currentRing": index + 1})


async def _instruction_pending(db, tenant_id: str, instruction_id: Optional[str]) -> bool:
    """True when the row's newest instruction exists and is still waiting for the agent to fetch it."""
    if not instruction_id:
        return False
    doc = await raw(db).agent_instructions.find_one({"id": instruction_id, "tenantId": tenant_id}, {"_id": 0, "status": 1})
    return isinstance((doc or {}).get("status"), str) and doc["status"].strip().lower() == "pending"


async def _close_open_rows(db, tenant_id: str, rollout_id: str) -> int:
    """Every row of the rollout still waiting for a person or for the window is closed, so none can be
    approved or sent after the halt."""
    found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout_id,
         "state": {"$in": ["awaiting_approval", "suggested", "approved"]}}, {"_id": 0, "id": 1})
    closed = 0
    for item in [r async for r in found]:
        done = await ledger.transition(db, tenant_id, item["id"], ("awaiting_approval", "suggested", "approved"),
                                       "expired", reasonCode="rollout_closed",
                                       reasonText=messages.REASON_TEXT["rollout_closed"])
        closed += 1 if done else 0
    return closed


async def _end_unfetched(db, tenant_id: str, rollout_id: str, ring: int) -> None:
    """A dispatching row of the ring whose instruction is still pending is failed ``rollout_halted``: delivery
    then refuses the instruction (its row is not dispatchable), and the computer is marked not reached."""
    found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout_id,
         "reason.inputs.ring": ring, "state": "dispatching"}, {"_id": 0})
    for row in [r async for r in found]:
        if not await _instruction_pending(db, tenant_id, (row.get("instructionIds") or [None])[-1]):
            continue
        done = await ledger.transition(db, tenant_id, row["id"], ("dispatching",), "failed", reasonCode="rollout_halted",
                                       reasonText=messages.REASON_TEXT["rollout_halted"])
        if done:
            await store.set_host(db, tenant_id, rollout_id, (row.get("targets") or [None])[0],
                                 {"state": "not_reached", "waitReason": None})


def halt_reason(code: str, ring: int, host: Optional[str], facts: Optional[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    text = rm.fill(rm.HALT_REASON.get(code, ""), **{"host": host or "", **(facts or {})})
    return {"code": code, "ring": ring, "host": host, "text": text, "at": now}


async def halt(db, tenant_id: str, rollout: Dict[str, Any], ring: int, *, code: str, now: datetime,
               host: Optional[str] = None, facts: Optional[Dict[str, Any]] = None) -> bool:
    """Stop the rollout at ``ring``. Returns False when it was not running (someone halted it first).
    ``facts`` fill the reason sentence (``host`` as a name, ``f``, ``computers``, ``limit``)."""
    reason = halt_reason(code, ring, host, facts, now)
    won = await store.rollouts(db).update_one(
        {"id": rollout["id"], "tenantId": tenant_id, "status": "running"},
        {"$set": {"status": "halted", "haltedAt": now, "haltReason": reason, f"rings.{ring}.state": "halted"}})
    if won.modified_count == 0:
        return False
    rollout.update({"status": "halted", "haltedAt": now, "haltReason": reason})
    rollout["rings"][ring]["state"] = "halted"
    await _close_open_rows(db, tenant_id, rollout["id"])
    await _end_unfetched(db, tenant_id, rollout["id"], ring)
    from . import revert           # revert imports lines, which import modules that import this one
    try:
        await revert.start_ring_revert(db, tenant_id, rollout, ring, now)
    except Exception as exc:
        logger.error("autonomous_ops: rollout %s halted but its revert did not start: %s", rollout["id"], exc)
    return True


# ---------------------------------------------------------------- Resume and Cancel (D-16)

def _who(actor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The actor as the ledger and the audit chain read it: ``username`` and ``display``."""
    who = dict(actor or {})
    name = who.get("display") or who.get("name") or who.get("username") or "unknown"
    who.setdefault("username", name)
    who["display"] = name
    return who


async def _load(db, tenant_id: str, rollout_id: str) -> Dict[str, Any]:
    doc = store.normalise(await store.rollouts(db).find_one({"id": rollout_id, "tenantId": tenant_id}))
    if doc is None:
        raise RolloutNotFound(rm.API_DETAIL["rollout_not_found"])
    return doc


def _halted_ring(rollout: Dict[str, Any]) -> int:
    reason = rollout.get("haltReason") if isinstance(rollout.get("haltReason"), dict) else {}
    index = reason.get("ring", rollout.get("currentRing") or 0)
    count = len(rollout.get("rings") or [])
    return index if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < count else 0


def _record_text(kind: str, rollout: Dict[str, Any], ring_name: str, reason: str = "") -> str:
    return rm.fill(rm.LIFECYCLE_CONTROL[kind], name=rollout.get("name") or "", ring=ring_name, reason=reason)


async def _undo_flip(db, tenant_id: str, rollout: Dict[str, Any], expect: str, restore: Dict[str, Any],
                     unset: List[str], pull_at: Optional[datetime]) -> None:
    """Put the rollout back as it was after its record could not be written (a safeguard is never changed without
    a record, PROH-83-09). Best effort: a failure here is logged and the original error is raised by the caller."""
    update: Dict[str, Any] = {"$set": restore}
    if unset:
        update["$unset"] = {k: "" for k in unset}
    if pull_at is not None:
        update["$pull"] = {"resumeLog": {"at": pull_at}}
    try:
        await store.rollouts(db).update_one({"id": rollout["id"], "tenantId": tenant_id, "status": expect}, update)
    except Exception as exc:
        logger.error("autonomous_ops: rollout %s could not be put back after an unrecorded change: %s", rollout["id"], exc)


async def resume(db, tenant_id: str, rollout_id: str, *, actor: Optional[Dict[str, Any]], reason: Any,
                 now: datetime) -> Dict[str, Any]:
    """Resume a halted rollout (D-16). Returns ``{"status": "resumed" | "still_halted", "reason", "ring"}``.
    Raises ``ReasonRequired`` (no reason, or one over 500 characters), ``RolloutNotFound``, ``NotHalted`` and
    ``RevertRunning`` (a computer is still being put back, R10). The halted ring's health check runs again on
    current data; the rollout continues only when it is green and a red check keeps it halted with the new reason."""
    from . import health, reboots, signals              # signals imports reboots, which imports start
    text = reason.strip() if isinstance(reason, str) else ""
    if not text or len(text) > REASON_MAX:
        raise ReasonRequired(rm.API_DETAIL["reason_required"])
    rollout = await _load(db, tenant_id, rollout_id)
    if rollout.get("status") != "halted":
        raise NotHalted(rm.API_DETAIL["not_halted"])
    hosts = await store.host_docs(db, tenant_id, rollout_id)
    if any(h.get("state") == "reverting" for h in hosts):
        raise RevertRunning(rm.API_DETAIL["revert_running"])
    index = _halted_ring(rollout)
    ring = rollout["rings"][index]
    ring_name = str(ring.get("name") or "")
    in_ring = [h for h in hosts if h.get("ring") == index]
    found = await signals.ring_signals(db, tenant_id, rollout, in_ring, now)
    verdict = health.ring_verdict(found, ring, now, health.required_os(rollout))
    green = verdict.kind == "green" and not any(reboots.pending(h) for h in in_ring)
    who = _who(actor)
    entry = {"at": now, "by": {"id": who.get("id"), "name": who["display"]}, "reason": text, "ring": index}
    checks = {f"rings.{index}.health": health.health_rows(found, ring, now),
              f"rings.{index}.healthCounts": health.health_counts(found)}
    if green:
        return await _continue(db, tenant_id, rollout, index, ring_name, who, entry, checks, text, now)
    return await _stay(db, tenant_id, rollout, index, ring_name, who, entry, checks, text, verdict,
                       halt_facts(verdict, in_ring, found, ring), now)


async def _stay(db, tenant_id: str, rollout: Dict[str, Any], index: int, ring_name: str, who: Dict[str, Any],
                entry: Dict[str, Any], checks: Dict[str, Any], text: str, verdict, facts: Dict[str, Any],
                now: datetime) -> Dict[str, Any]:
    """The check is not green: the rollout stays halted. A failing check gives the new reason; a check still
    waiting for data keeps the old one."""
    fields: Dict[str, Any] = dict(checks)
    if verdict.kind == "halt":
        fields["haltReason"] = halt_reason(verdict.code, index, verdict.host, facts, now)
    won = await store.rollouts(db).update_one(
        {"id": rollout["id"], "tenantId": tenant_id, "status": "halted"},
        {"$set": fields, "$push": {"resumeLog": {**entry, "outcome": "still_halted"}}})
    if won.modified_count == 0:
        raise NotHalted(rm.API_DETAIL["not_halted"])
    shown = fields.get("haltReason") or rollout.get("haltReason") or {}
    await ledger.record_control(db, tenant_id, "rollout_resume_checked", scope="tenant", actor=who,
                                reason=_record_text("still_halted", rollout, ring_name, text))
    return {"status": "still_halted", "reason": str(shown.get("text") or ""), "ring": ring_name}


async def _continue(db, tenant_id: str, rollout: Dict[str, Any], index: int, ring_name: str, who: Dict[str, Any],
                    entry: Dict[str, Any], checks: Dict[str, Any], text: str, now: datetime) -> Dict[str, Any]:
    """The check is green: the ring passes and the rollout runs on (or completes after the last ring). The status
    flip, the ring and the next ring are one compare-and-set, so two Resumes at once continue it once."""
    last = index + 1 >= len(rollout["rings"])
    fields: Dict[str, Any] = {**checks, "status": "running", f"rings.{index}.state": "passed",
                              f"rings.{index}.passedAt": now}
    if not last:
        fields["currentRing"] = index + 1
    before = {"status": "halted", "haltedAt": rollout.get("haltedAt"), "haltReason": rollout.get("haltReason"),
              f"rings.{index}.state": rollout["rings"][index].get("state"), "currentRing": rollout.get("currentRing")}
    won = await store.rollouts(db).update_one(
        {"id": rollout["id"], "tenantId": tenant_id, "status": "halted"},
        {"$set": fields, "$unset": {"haltReason": "", "haltedAt": ""},
         "$push": {"resumeLog": {**entry, "outcome": "resumed", "haltReason": rollout.get("haltReason")}}})
    if won.modified_count == 0:
        raise NotHalted(rm.API_DETAIL["not_halted"])
    try:
        await ledger.record_control(db, tenant_id, "rollout_resumed", scope="tenant", actor=who,
                                    reason=_record_text("resumed", rollout, ring_name, text))
    except Exception:
        await _undo_flip(db, tenant_id, rollout, "running", before, [f"rings.{index}.passedAt"], entry["at"])
        raise
    if last:
        await complete(db, tenant_id, store.normalise(await store.rollouts(db).find_one(
            {"id": rollout["id"], "tenantId": tenant_id})), now)
    return {"status": "resumed", "reason": None, "ring": ring_name}


async def cancel(db, tenant_id: str, rollout_id: str, *, actor: Optional[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """Cancel a halted rollout (D-16): rings that did not pass are cancelled, the claims are released, open rows
    expire (``rollout_closed``) and a revert already running is left to finish. Computers that were patched keep
    their patches. Raises ``RolloutNotFound`` and ``NotHalted``."""
    rollout = await _load(db, tenant_id, rollout_id)
    if rollout.get("status") != "halted":
        raise NotHalted(rm.API_DETAIL["not_halted"])
    hosts = await store.host_docs(db, tenant_id, rollout_id)
    who = _who(actor)
    rings = rollout.get("rings") or []
    fields: Dict[str, Any] = {"status": "cancelled", "cancelledAt": now, "cancelledBy": {"id": who.get("id"), "name": who["display"]},
                              "revertOpen": any(h.get("state") == "reverting" for h in hosts)}
    before: Dict[str, Any] = {"status": "halted"}
    for i, ring in enumerate(rings):
        if ring.get("state") != "passed":
            fields[f"rings.{i}.state"] = "cancelled"
            before[f"rings.{i}.state"] = ring.get("state")
    won = await store.rollouts(db).update_one({"id": rollout_id, "tenantId": tenant_id, "status": "halted"}, {"$set": fields})
    if won.modified_count == 0:
        raise NotHalted(rm.API_DETAIL["not_halted"])
    ring_name = str(rings[_halted_ring(rollout)].get("name") or "") if rings else ""
    try:
        await ledger.record_control(db, tenant_id, "rollout_cancelled", scope="tenant", actor=who,
                                    reason=_record_text("cancelled", rollout, ring_name))
    except Exception:
        await _undo_flip(db, tenant_id, rollout, "cancelled", before, ["cancelledAt", "cancelledBy", "revertOpen"], None)
        raise
    await store.release(db, tenant_id, rollout_id)
    await _close_open_rows(db, tenant_id, rollout_id)
    return {"status": "cancelled", "reason": None, "ring": ring_name}


async def settle_cancelled(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> None:
    """A cancelled rollout whose revert was still running: settle what the computers report, and stop visiting the
    rollout once no computer is being reverted any more. Nothing new is asked of anyone."""
    from . import revert
    await revert.settle_reverts(db, tenant_id, rollout, now, may_decide=False)
    if not any(h.get("state") == "reverting" for h in await store.host_docs(db, tenant_id, rollout["id"])):
        await store.set_rollout(db, tenant_id, rollout, {"revertOpen": False})


# ---------------------------------------------------------------- computers a finished rollout never reached (D-18)

async def release_reached(db, tenant_id: str, rollout: Dict[str, Any]) -> int:
    """Let go of the claim of every tracked computer that was reached after all (it installed or failed)."""
    tracked = set(rollout.get("notReached") or [])
    done = [h["agentId"] for h in await store.host_docs(db, tenant_id, rollout["id"])
            if h["agentId"] in tracked and h.get("state") in REACHED_LATER and h.get("active")]
    return await store.release(db, tenant_id, rollout["id"], done) if done else 0


async def offer_returning(db, tenant_id: str, rollout: Dict[str, Any], now: datetime, open_window: bool) -> int:
    """A tracked computer that is online again while a window is open is offered the install as an approval line,
    never installed on its own. Returns how many approval rows were raised."""
    from . import installs, lines             # lines imports modules that import this one
    if not open_window or rollout.get("closedAt"):
        return 0
    tracked = set(rollout.get("notReached") or [])
    lost = [h for h in await store.host_docs(db, tenant_id, rollout["id"])
            if h["agentId"] in tracked and h.get("state") == "not_reached" and h.get("active")]
    if not lost:
        return 0
    seen = raw(db).agents.find({"tenantId": tenant_id, "id": {"$in": [h["agentId"] for h in lost]}},
                               {"_id": 0, "id": 1, "status": 1, "lastSeen": 1})
    online = {a["id"] async for a in seen if agent_support.online(a, now)}
    raised = 0
    for h in sorted(lost, key=lambda x: (str(x.get("hostname") or "").casefold(), x["agentId"])):
        if h["agentId"] not in online:
            continue
        await store.set_host(db, tenant_id, rollout["id"], h["agentId"],
                             {"state": "waiting", "waitReason": None, "notReachedWindow": None})
        fresh = {**h, "state": "waiting"}
        ids = installs.unresolved(fresh) + [p for p in installs.deferred_pending(fresh) if p not in installs.unresolved(fresh)]
        made = await lines.raise_line(db, tenant_id, rollout, int(h.get("ring") or 0), "install",
                                      [lines.install_entry(fresh, ids)], now) if ids else {"raised": 0, "simulated": 0}
        if made["raised"] or made["simulated"]:
            raised += made["raised"]
        else:                                  # nothing was asked of anyone: it stays a computer not reached
            await store.set_host(db, tenant_id, rollout["id"], h["agentId"], {"state": "not_reached"})
    return raised


async def close_if_due(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> bool:
    """At ``closesAt`` close the finished rollout: remaining claims are released, open rows expire, and
    ``neverReachedCount`` counts the tracked computers that never installed. True when it closed now."""
    closes = store.parse_time(rollout.get("closesAt"))
    if closes is None or rollout.get("closedAt") or store.aware(now) < closes or rollout.get("status") != "completed":
        return False
    tracked = set(rollout.get("notReached") or [])
    never = sum(1 for h in await store.host_docs(db, tenant_id, rollout["id"])
                if h["agentId"] in tracked and h.get("state") in ("not_reached", "waiting", "would_install"))
    won = await store.rollouts(db).update_one(
        {"id": rollout["id"], "tenantId": tenant_id, "status": "completed", "closedAt": None},
        {"$set": {"closedAt": now, "neverReachedCount": never}})
    if won.modified_count == 0:
        return False
    rollout.update({"closedAt": now, "neverReachedCount": never})
    await store.release(db, tenant_id, rollout["id"])
    await _close_open_rows(db, tenant_id, rollout["id"])
    return True
