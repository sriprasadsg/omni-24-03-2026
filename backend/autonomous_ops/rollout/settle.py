"""Settling installs from what the agent actually reported (PTCH-01).

An agent answers an install instruction as "accepted" and posts the real outcome to the deployment
result route, which stores it on the host's own ``patch_deployment_jobs`` document under
``agentResults.<agent id with dots and dollars replaced>``. The reconciler cannot read that, so the
rollout controller does: every tick, before any new decision (also while a stop is on), it moves each
installing host to installed or failed from its own job, and ends the ledger row to match.

An instruction the delivery hook refused (it expired) or the stop cancelled, with no result, was never
installed: the row ends failed ``rollout_not_delivered`` and the host goes back to waiting for another
try (an approval row asks again, as a new card).

A result may defer a patch as ``not_reversible`` (D-05): that patch was not installed, the automatic row
ends for nothing, and the host remembers the patch in ``deferredIds`` so the controller raises an approval
row for it. A computer is ``installed`` only when its automatic row and every approval row it holds have
settled (PTCH-06 adjacency); until then it reads installing, or waiting with ``waitReason`` approval.

Raw Mongo handle with an explicit tenantId only. Reads an instruction's status; never writes the queue.
"""
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .. import ledger, messages
from ..scope import raw
from . import COMMAND_INSTALL, DISPATCHER_NAME, MAX_ATTEMPTS, inflight, messages as rm, store
from .installs import deferred_pending, retry_fields, unresolved

logger = logging.getLogger(__name__)


def result_key(agent_id: str) -> str:
    """The key the result route files an agent's result under."""
    return agent_id.replace(".", "_").replace("$", "_")


def verdict_of(entry: Dict[str, Any], patch_ids: List[str]) -> Dict[str, Any]:
    """{"ok", "message", "rebootNeeded", "installed", "deferred"} from one agent result. Settled ok only when
    every applicable id has a result with status success, or was deferred as ``not_reversible`` (D-05: not
    installed, to be approved); anything else, including a missing id, is a failure."""
    results = [r for r in entry.get("results") or [] if isinstance(r, dict)]
    by_id = {str(r.get("patch_id")): r for r in results}

    def status_of(patch_id: str) -> str:
        return str((by_id.get(patch_id) or {}).get("status")).casefold()

    deferred = [p for p in patch_ids if status_of(p) == "deferred" and by_id[p].get("code") == "not_reversible"]
    installed = [p for p in patch_ids if status_of(p) == "success"]
    bad = [p for p in patch_ids if p not in deferred and p not in installed]
    reboot = bool(entry.get("rebootRequired")) or any(r.get("reboot_required") for r in results)
    if not bad and patch_ids:
        return {"ok": True, "message": None, "rebootNeeded": reboot, "installed": installed, "deferred": deferred}
    detail = next((str(by_id[p].get("message")) for p in bad if p in by_id and by_id[p].get("message")), None)
    message = detail or entry.get("error") or "The computer did not report success for every patch."
    return {"ok": False, "message": str(message)[:500], "rebootNeeded": reboot, "installed": installed,
            "deferred": deferred}


async def _entry_of(db, tenant_id: str, job_id: Optional[str], agent_id: str):
    """(job, this computer's result entry or None)."""
    job = await raw(db).patch_deployment_jobs.find_one({"id": job_id, "tenantId": tenant_id},
                                                       {"_id": 0, "agentResults": 1, "patchIds": 1})
    entry = ((job or {}).get("agentResults") or {}).get(result_key(agent_id))
    return job, entry if isinstance(entry, dict) else None


def _words(kind: str, installed: List[str], deferred: List[str], host: Dict[str, Any]) -> Dict[str, str]:
    """The words an Activity row keeps for an install the agent answered (UI-SPEC section 7). The row keeps the Why
    it was made with (``reasonText``) and gains the Result (``activityResult``). Only an automatic row that ended for
    nothing because every patch was deferred as not reversible says why it needs a person."""
    if kind == "done":
        return {"activityResult": rm.fill(rm.ACTIVITY["canary_done"], patch=", ".join(installed))}
    if kind == "idle":
        return {"reasonText": rm.fill(rm.ACTIVITY["not_reversible_why"], patch=", ".join(deferred),
                                      host=host.get("hostname") or host["agentId"]),
                "activityResult": rm.ACTIVITY["not_reversible_result"]}
    return {"activityResult": rm.ACTIVITY["canary_failed"]}


@dataclass
class Progress:
    """What one pass learned about one computer."""
    inflight: bool = False
    outstanding: bool = False                 # an approval row is waiting for a person or for the window
    failed: Optional[str] = None
    failure_code: Optional[str] = None        # set when the computer is failed without a result (no answer)
    closed: bool = False                      # an approval row was denied or ran out: the computer is not approved
    reported: List[Any] = field(default_factory=list)
    reboot: bool = False
    installed: List[str] = field(default_factory=list)
    deferred: List[str] = field(default_factory=list)
    retry: Optional[Dict[str, Any]] = None    # retry_fields for an automatic row that never arrived
    reraise: List[str] = field(default_factory=list)   # patch ids whose approval row never arrived
    settled_lines: List[str] = field(default_factory=list)
    auto_done: bool = False


async def _settle_auto(db, tenant_id: str, host: Dict[str, Any], now: datetime, prog: Progress) -> None:
    """The automatic canary row: from its own job's result, else from what happened to its instruction."""
    action_id = host.get("installActionId")
    job, entry = await _entry_of(db, tenant_id, host.get("installJobId"), host["agentId"])
    if entry is not None:
        verdict = verdict_of(entry, list((job or {}).get("patchIds") or host.get("patchIds") or []))
        reported = store.parse_time(entry.get("reportedAt")) or store.aware(now)
        prog.auto_done = True
        prog.reboot = prog.reboot or verdict["rebootNeeded"]
        prog.installed += verdict["installed"]
        prog.deferred += verdict["deferred"]
        if verdict["ok"]:
            if verdict["installed"]:
                prog.reported.append(reported)
            idle = not verdict["installed"]
            code = "rollout_not_reversible" if idle else "rollout_installed"
            words = _words("idle" if idle else "done", verdict["installed"], verdict["deferred"], host)
            to_state = "executed"
        else:
            prog.reported.append(reported)
            prog.failed = verdict["message"]
            code, to_state = "rollout_install_failed", "failed"
            words = _words("failed", [], [], host)
        if action_id:
            await ledger.transition(db, tenant_id, action_id, ("dispatching",), to_state, reasonCode=code,
                                    result={"jobId": host.get("installJobId"), "agentStatus": entry.get("status")}, **words)
        return
    task = await inflight.load_instruction(db, tenant_id, host.get("installInstructionId"))
    outcome = inflight.instruction_outcome(task, now, host.get("installDispatchedAt"))
    if outcome == "not_delivered":
        if action_id:
            await ledger.transition(db, tenant_id, action_id, ("dispatching",), "failed",
                                    reasonCode="rollout_not_delivered",
                                    reasonText=messages.REASON_TEXT["rollout_not_delivered"])
        await inflight.close_job(db, tenant_id, host.get("installJobId"), now,
                                 messages.REASON_TEXT["rollout_not_delivered"])
        prog.retry = retry_fields(host, int(host.get("attempt") or 1))
        return
    if outcome in ("failed", "no_result"):
        code = "rollout_install_failed" if outcome == "failed" else "rollout_no_result"
        prog.failed = inflight.failure_words(task, messages.REASON_TEXT[code]) if outcome == "failed" \
            else messages.REASON_TEXT[code]
        prog.failure_code = code
        prog.auto_done = True
        if action_id:
            await ledger.transition(db, tenant_id, action_id, ("dispatching",), "failed", reasonCode=code,
                                    reasonText=messages.REASON_TEXT[code], **_words("failed", [], [], host))
        await inflight.close_job(db, tenant_id, host.get("installJobId"), now, messages.REASON_TEXT[code])
        return
    prog.inflight = True


async def _settle_lines(db, tenant_id: str, host: Dict[str, Any], now: datetime, prog: Progress,
                        stopped_since: Optional[datetime] = None) -> None:
    """The host's approval rows of the install line, each by the state of its own ledger row. A row that expired
    while a stop was on (``stopped_since``) was never a "no": the computer is offered the install again."""
    done = set(host.get("lineSettled") or [])
    for action_id in (host.get("lineActionIds") or {}).get("install") or []:
        if action_id in done:
            continue
        row = await ledger.get(db, tenant_id, action_id)
        if row is None:
            continue
        state = row.get("state")
        params = row.get("params") or {}
        ids = list(params.get("patch_ids") or [])
        if state in ("awaiting_approval", "suggested", "approved"):
            prog.outstanding = True
        elif state == "dispatching":
            job, entry = await _entry_of(db, tenant_id, params.get("job_id"), host["agentId"])
            if entry is not None:
                verdict = verdict_of(entry, ids)
                prog.reported.append(store.parse_time(entry.get("reportedAt")) or store.aware(now))
                prog.reboot = prog.reboot or verdict["rebootNeeded"]
                prog.installed += verdict["installed"]
                ok = verdict["ok"]
                prog.failed = prog.failed or (None if ok else verdict["message"])
                await ledger.transition(
                    db, tenant_id, action_id, ("dispatching",), "executed" if ok else "failed",
                    reasonCode="rollout_installed" if ok else "rollout_install_failed",
                    result={"jobId": params.get("job_id"), "agentStatus": entry.get("status")},
                    **_words("done" if ok else "failed", verdict["installed"], [], host))
                prog.settled_lines.append(action_id)
                continue
            instruction = (row.get("instructionIds") or [None])[-1]
            task = await inflight.load_instruction(db, tenant_id, instruction)
            outcome = inflight.instruction_outcome(task, now, row.get("updatedAt"))
            if outcome == "not_delivered":
                await ledger.transition(db, tenant_id, action_id, ("dispatching",), "failed",
                                        reasonCode="rollout_not_delivered",
                                        reasonText=messages.REASON_TEXT["rollout_not_delivered"])
                await inflight.close_job(db, tenant_id, params.get("job_id"), now,
                                         messages.REASON_TEXT["rollout_not_delivered"])
                prog.reraise += ids
                prog.settled_lines.append(action_id)
            elif outcome in ("failed", "no_result"):
                code = "rollout_install_failed" if outcome == "failed" else "rollout_no_result"
                prog.failed = prog.failed or (inflight.failure_words(task, messages.REASON_TEXT[code])
                                              if outcome == "failed" else messages.REASON_TEXT[code])
                prog.failure_code = prog.failure_code or code
                await ledger.transition(db, tenant_id, action_id, ("dispatching",), "failed", reasonCode=code,
                                        reasonText=messages.REASON_TEXT[code], **_words("failed", [], [], host))
                await inflight.close_job(db, tenant_id, params.get("job_id"), now, messages.REASON_TEXT[code])
                prog.settled_lines.append(action_id)
            else:
                prog.inflight = True
        elif state in ("executed", "verified"):
            prog.settled_lines.append(action_id)
        elif state in ("failed", "cancelled_by_stop"):
            prog.reraise += ids              # it never reached the computer: ask again, as a new card
            prog.settled_lines.append(action_id)
        elif state == "refused":
            prog.failed = prog.failed or str(row.get("reasonText") or "The step was refused.")
            prog.settled_lines.append(action_id)
        elif state == "expired" and _expired_in_stop(row, stopped_since):
            prog.reraise += ids              # GATE-06: the clock ran during the stop; ask again, as a new card
            prog.settled_lines.append(action_id)
        elif state in ("denied", "expired"):
            # The controller halts the rollout at the ring; until then, and afterwards, the computer was not
            # approved: it must never fall through to installed (WR-04).
            prog.closed = True


def _expired_in_stop(row: Dict[str, Any], stopped_since: Optional[datetime]) -> bool:
    """True when the expired row ran out at or after the moment the stop began."""
    finished = store.parse_time(row.get("finishedAt"))
    return stopped_since is not None and finished is not None and finished >= stopped_since


async def _settle_host(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any], now: datetime) -> str:
    prog = Progress()
    if host.get("state") == "installing" and host.get("installActionId") and not host.get("autoSettled"):
        await _settle_auto(db, tenant_id, host, now, prog)
    await _settle_lines(db, tenant_id, host, now, prog, store.parse_time(rollout.get("stoppedSince")))
    after = dict(host)
    after["deferredIds"] = list(dict.fromkeys(list(host.get("deferredIds") or []) + prog.deferred))
    after["linePatchIds"] = [p for p in host.get("linePatchIds") or [] if p not in prog.reraise]
    after["lineSettled"] = list(host.get("lineSettled") or []) + prog.settled_lines
    auto_settled = bool(host.get("autoSettled")) or prog.auto_done
    fields: Dict[str, Any] = {"deferredIds": after["deferredIds"], "linePatchIds": after["linePatchIds"],
                              "lineSettled": after["lineSettled"], "autoSettled": auto_settled}
    reported = [t for t in prog.reported + [store.parse_time(host.get("installReportedAt"))] if t is not None]
    if reported:
        fields["installReportedAt"] = max(reported)
    if prog.installed:
        fields["installedIds"] = list(dict.fromkeys(list(host.get("installedIds") or []) + prog.installed))
    if prog.reboot or host.get("rebootNeeded"):
        fields["rebootNeeded"] = True
    if prog.reraise:
        fields["attempt"] = int(host.get("attempt") or 0) + 1
    if prog.retry is not None:
        fields.update(prog.retry)
        auto_settled = False
    attempt = int(fields.get("attempt", host.get("attempt") or 0))
    if prog.failed:
        fields.update({"state": "failed", "failureMessage": prog.failed, "waitReason": None})
        if prog.failure_code:
            fields["failureCode"] = prog.failure_code
    elif prog.reraise and attempt >= MAX_ATTEMPTS:
        fields.update({"state": "failed", "waitReason": None,
                       "failureMessage": messages.REASON_TEXT["rollout_not_delivered"]})
    elif prog.retry is not None and prog.retry.get("state") == "failed":
        fields["waitReason"] = None
    elif prog.inflight:
        fields.update({"state": "installing", "waitReason": None})
    else:
        fresh = dict(host, **fields)
        wants_decision = (bool(deferred_pending(fresh)) or bool(prog.reraise) or prog.retry is not None
                          or (not auto_settled and bool(unresolved(fresh))))
        if prog.outstanding:
            fields.update({"state": "waiting", "waitReason": "approval"})
        elif wants_decision:
            fields.update({"state": "waiting", "waitReason": None})
        elif prog.closed:
            fields.update({"state": "waiting", "waitReason": "not_approved"})
        else:
            fields.update({"state": "installed", "waitReason": None})
    changed = {k: v for k, v in fields.items() if host.get(k) != v}
    if changed:
        await store.set_host(db, tenant_id, rollout["id"], host["agentId"], changed)
    return str(fields.get("state") or host.get("state"))


async def _has_instruction(db, tenant_id: str, ids: List[Optional[str]]) -> bool:
    for instruction_id in ids:
        if await inflight.load_instruction(db, tenant_id, instruction_id) is not None:
            return True
    return False


async def recover_unsent(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> int:
    """WR-06: an install row claimed for dispatch (``dispatching``) that still has no instruction after
    ``DISPATCH_CLAIM_BOUND`` was left by a process that died or raised before it wrote one. It ends failed
    ``rollout_not_delivered``, its job is closed and the computer is tried again (an approval row asks again, as a
    new card, through the normal settle pass). Returns how many rows were recovered."""
    cutoff = store.aware(now) - inflight.DISPATCH_CLAIM_BOUND
    found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout["id"],
         "state": "dispatching", "command": COMMAND_INSTALL, "updatedAt": {"$lte": cutoff}}, {"_id": 0})
    hosts = {h["agentId"]: h for h in await store.host_docs(db, tenant_id, rollout["id"])}
    recovered = 0
    for row in [r async for r in found]:
        host = hosts.get((row.get("targets") or [None])[0])
        ids = list(row.get("instructionIds") or [])
        if host is not None and host.get("installActionId") == row["id"]:
            ids.append(host.get("installInstructionId"))
        if await _has_instruction(db, tenant_id, ids):
            continue
        text = messages.REASON_TEXT["rollout_not_delivered"]
        if await ledger.transition(db, tenant_id, row["id"], ("dispatching",), "failed",
                                   reasonCode="rollout_not_delivered", reasonText=text) is None:
            continue
        recovered += 1
        await inflight.close_job(db, tenant_id, (row.get("params") or {}).get("job_id"), now, text)
        is_line = host is not None and row["id"] in ((host.get("lineActionIds") or {}).get("install") or [])
        if host is not None and not is_line and host.get("installActionId") in (None, row["id"]) \
                and host.get("state") in ("waiting", "installing"):
            attempt = int(((row.get("reason") or {}).get("inputs") or {}).get("attempt") or 1)
            await store.set_host(db, tenant_id, rollout["id"], host["agentId"],
                                 retry_fields(host, max(attempt, int(host.get("attempt") or 0))))
    return recovered


async def settle(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> Dict[str, int]:
    """Settle every computer of the rollout that has something in flight: installing, or waiting on an
    approval row. Returns counts by new state. A failure on one computer is logged and does not stop the
    others."""
    counts: Dict[str, int] = {}
    try:
        await recover_unsent(db, tenant_id, rollout, now)
    except Exception as exc:
        logger.error("autonomous_ops: rollout %s could not recover its unsent rows: %s", rollout["id"], exc)
    for host in await store.host_docs(db, tenant_id, rollout["id"]):
        if host.get("state") != "installing" and not (host.get("state") == "waiting" and host.get("lineActionIds")):
            continue
        try:
            new_state = await _settle_host(db, tenant_id, rollout, host, now)
        except Exception as exc:
            logger.error("autonomous_ops: rollout %s could not settle host %s: %s", rollout["id"], host["agentId"], exc)
            continue
        counts[new_state] = counts.get(new_state, 0) + 1
    return counts
