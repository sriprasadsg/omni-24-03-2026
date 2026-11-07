"""Putting a halted ring back (Phase 84, PTCH-04, D-14, D-15): the revert is the undo of each computer's own install row.

When a ring halts, every computer of that ring that installed at least one patch is reverted where the computer
can do it, healthy-looking ones included (D-14); the rings that already passed keep their patches. The revert
runs on its own and at once (D-15): the install row moves from executed, verified or failed to ``undone`` with
an undo block ``{action: rollback_patches, params: {patch_ids, job_id, revert_of}}``, and ``gate.execute`` writes
the stamped instruction as kind ``undo``. An undo has no ``expiresAt`` and is exempt from every stop, so it works
during a platform or tenant stop and outside the maintenance window. The patch ids are the ones the computer's
own install job recorded as installed (``installed_ids_for``), never anything from a request (T-84-41).

A computer is only ever shown Reverted from its agent's own success result (PROH-84-02c, T-84-40). A Linux
computer whose agent does not report ``patch_revert_by_job`` is sent nothing and reads Not reverted with the
reason; a Windows computer is reverted by its KB list. A result that says a restart is needed raises a Revert
restart line (an approval, frozen by a stop like any other). Every Not reverted reason is stored as the code the
agent sent (or one of ours); the views map the three known codes to words and read any other as the plain
"Not reverted. The patch is still installed." sentence, so no code can raise there.

``start_ring_revert`` is idempotent: it reverts only install rows that are not yet ``undone`` on computers that
are not already being or done being reverted, so the halt and every later pass of the controller may call it
(a result that arrives after the halt is reverted by the next pass). Raw Mongo handle with an explicit tenantId.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .. import agent_support, gate, ledger, messages
from ..scope import raw
from . import (COMMAND_INSTALL, COMMAND_UNDO, SYSTEM_ACTOR, TOKEN_REVERT_BY_JOB, inflight, messages as rm, reboots,
               start, store)
from .settle import result_key

logger = logging.getLogger(__name__)

REVERTABLE = ("executed", "verified", "failed")          # an install row that can be put back (a partial install fails)
_SKIP_STATES = ("installing", "restarting", "reverting", "reverted", "not_reverted")
_KNOWN_FIRST = ("not_uninstallable", "version_not_offered")      # the reasons the screen has words for, shown first
_AGENT_FIELDS = {"_id": 0, "id": 1, "tenantId": 1, "lastSeen": 1, "platform": 1, "meta.response_actions": 1,
                 "meta.response_state": 1}


def _best_reason(reasons: List[str]) -> str:
    """The reason to show for a computer: a known one first, else the first recorded."""
    for known in _KNOWN_FIRST:
        if known in reasons:
            return known
    return reasons[0] if reasons else "failed"


def _why(rollout: Dict[str, Any], ring: int) -> str:
    """The Why of a revert row: which ring halted and the reason (UI-SPEC section 7)."""
    rings = rollout.get("rings") or []
    name = str(rings[ring].get("name") or "") if 0 <= ring < len(rings) else ""
    halt = rollout.get("haltReason") if isinstance(rollout.get("haltReason"), dict) else {}
    reason = str(halt.get("text") or "").strip().rstrip(".")
    if not reason:
        return rm.fill(rm.ACTIVITY["revert_why_unknown"], ring=name)
    return rm.fill(rm.ACTIVITY["revert_why"], ring=name, reason=reason)


def _not_reverted_text(code: Optional[str]) -> str:
    """The Not reverted sentence for a reason code; a code the screen has no words for reads the plain one."""
    return rm.NOT_REVERTED.get(str(code), rm.NOT_REVERTED_OTHER)


async def _say(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any], action_id: str,
               result: str) -> None:
    """Keep what happened to one install row on the row itself, so Activity says it in words. Never raises: the
    words are a courtesy, the computer's state is what counts."""
    try:
        await ledger.set_display(db, tenant_id, action_id, reasonText=_why(rollout, int(host.get("ring") or 0)),
                                 activityResult=result)
    except Exception as exc:
        logger.error("autonomous_ops: the words of %s were not kept: %s", action_id, exc)


# ---------------------------------------------------------------- starting a revert

def _install_row_ids(host: Dict[str, Any]) -> List[str]:
    """The ids of the ledger rows that installed on this computer: the canary's automatic row and every
    approval row of the install line."""
    ids = [host["installActionId"]] if host.get("installActionId") else []
    ids += list((host.get("lineActionIds") or {}).get("install") or [])
    return list(dict.fromkeys(ids))


async def _targets(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The computer's install rows that still need putting back, each with its job id and the ids that job's
    result recorded as installed. Rows that installed nothing, and rows already undone, are left out."""
    from patch_core_endpoints import installed_ids_for           # the manual revert route reads the same ids
    found = []
    for action_id in _install_row_ids(host):
        row = await ledger.get(db, tenant_id, action_id)
        if row is None or row.get("state") not in REVERTABLE or row.get("command") != COMMAND_INSTALL:
            continue
        job_id = (row.get("params") or {}).get("job_id")
        if not job_id:
            continue
        job = await raw(db).patch_deployment_jobs.find_one(
            {"id": job_id, "tenantId": tenant_id, "rolloutId": rollout["id"]},
            {"_id": 0, "id": 1, "agentResults": 1, "dispatchedAgents": 1})
        ids = installed_ids_for(job, host["agentId"]) if job else []
        if ids:
            found.append({"row": row, "jobId": job_id, "ids": list(dict.fromkeys(ids))})
    return found


async def _revert_row(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any], target: Dict[str, Any],
                      with_token: bool, now: datetime) -> Dict[str, Any]:
    """Put one install row back: its own revert job, the row to ``undone`` with the undo block, then the
    stamped undo instruction. Returns ``{"status": "started", "actionId", "jobId"}``, ``{"status": "taken"}``
    when someone else moved the row first, or ``{"status": "refused"}`` when the gate refused (the row is then
    restored exactly as it was and the revert job removed)."""
    from patch_core_endpoints import ROLLBACK_JOB_TYPE, new_patch_job
    row, ids, agent_id = target["row"], target["ids"], host["agentId"]
    revert_job = f"revert-{uuid.uuid4().hex}"
    params: Dict[str, Any] = {"patch_ids": ids, "job_id": revert_job}
    if with_token:                    # an agent that can revert by job puts back exactly what that job installed
        params["revert_of"] = target["jobId"]
    job = new_patch_job(revert_job, tenant_id, ids, [agent_id], [agent_id], "Autonomous Ops", "Rollout", None,
                        now.isoformat(), "In Progress")
    job.update({"type": ROLLBACK_JOB_TYPE, "rolloutId": rollout["id"], "revertOf": target["jobId"],
                "rollbackOf": target["jobId"]})
    await raw(db).patch_deployment_jobs.insert_one(job)
    block = {"available": True, "action": COMMAND_UNDO, "params": params, "undoneAt": now,
             "undoneBy": dict(SYSTEM_ACTOR)}
    fields: Dict[str, Any] = {"undo": block, "reasonText": _why(rollout, int(host.get("ring") or 0))}
    if row.get("state") != "failed":         # a real install failure keeps its code, so the breaker still counts it (T-84-43)
        fields["reasonCode"] = "ring_reverted"
    won = await ledger.transition(db, tenant_id, row["id"], REVERTABLE, "undone", actor=SYSTEM_ACTOR, **fields)
    if won is None:
        await raw(db).patch_deployment_jobs.delete_one({"id": revert_job, "tenantId": tenant_id})
        return {"status": "taken"}
    sent = await gate.execute(db, tenant_id, row["id"], command=COMMAND_UNDO, agent_id=agent_id, params=params,
                              kind="undo")
    if sent.get("status") == "queued":
        return {"status": "started", "actionId": row["id"], "jobId": revert_job}
    await ledger.transition(db, tenant_id, row["id"], ("undone",), row["state"], actor=SYSTEM_ACTOR,
                            undo=row.get("undo") or {"available": True, "action": COMMAND_UNDO, "params": params,
                                                     "undoneAt": None, "undoneBy": None},
                            reasonCode=row.get("reasonCode"), reasonText=row.get("reasonText"),
                            finishedAt=row.get("finishedAt"))
    await raw(db).patch_deployment_jobs.delete_one({"id": revert_job, "tenantId": tenant_id})
    logger.error("autonomous_ops: the revert of %s on %s was refused (%s)", row["id"], agent_id, sent.get("reason"))
    return {"status": "refused"}


async def _start_host(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any], now: datetime) -> bool:
    """Start the revert of one computer. True when the computer was decided (reverting or Not reverted)."""
    targets = await _targets(db, tenant_id, rollout, host)
    if not targets:
        return False
    agent = await raw(db).agents.find_one({"id": host["agentId"], "tenantId": tenant_id}, _AGENT_FIELDS)
    has_token = TOKEN_REVERT_BY_JOB in agent_support.tokens_of(agent)
    if host.get("os") != "windows" and not has_token:        # PROH-84-02c: never sent, never shown as reverted
        await store.set_host(db, tenant_id, rollout["id"], host["agentId"], {
            "state": "not_reverted", "notRevertedReason": "agent_unsupported", "waitReason": None,
            "revertStartedAt": now})
        for target in targets:
            await _say(db, tenant_id, rollout, host, target["row"]["id"], _not_reverted_text("agent_unsupported"))
        return True
    started: List[Dict[str, Any]] = []
    failed: Dict[str, Any] = {}
    for target in targets:
        done = await _revert_row(db, tenant_id, rollout, host, target, has_token, now)
        if done["status"] == "started":
            started.append(done)
        elif done["status"] == "refused":                    # the gate refused it: the row is as it was
            failed[target["row"]["id"]] = {"outcome": "not_reverted", "reason": "dispatch_failed", "reboot": False,
                                           "at": now}
            await _say(db, tenant_id, rollout, host, target["row"]["id"], _not_reverted_text("dispatch_failed"))
    if not started and not failed:
        return False                                          # every row was taken by someone else meanwhile
    fields: Dict[str, Any] = {"waitReason": None, "revertStartedAt": now, "revertResult": failed,
                              "revertActionIds": [s["actionId"] for s in started],
                              "revertJobIds": [s["jobId"] for s in started]}
    if started:
        fields.update({"state": "reverting", "revertActionId": started[0]["actionId"],
                       "revertJobId": started[0]["jobId"]})
    else:
        fields.update({"state": "not_reverted", "notRevertedReason": "dispatch_failed"})
    await store.set_host(db, tenant_id, rollout["id"], host["agentId"], fields)
    return True


async def start_ring_revert(db, tenant_id: str, rollout: Dict[str, Any], ring: int, now: datetime) -> Dict[str, int]:
    """Revert every computer of ``ring`` that installed at least one patch (D-14). Returns counts of ``decided``
    (reverting, or Not reverted with its reason) and ``skipped``; a computer that installed nothing is left alone
    and so is any computer of another ring. A computer still installing or restarting is looked at again on the next
    pass. One computer's fault is logged and does not stop the others."""
    counts = {"decided": 0, "skipped": 0}
    for host in await store.host_docs(db, tenant_id, rollout["id"]):
        if host.get("ring") != ring or not host.get("installedIds") or host.get("state") in _SKIP_STATES:
            continue
        try:
            decided = await _start_host(db, tenant_id, rollout, host, now)
        except Exception as exc:
            logger.error("autonomous_ops: rollout %s could not start the revert on %s: %s", rollout["id"],
                         host["agentId"], exc)
            counts["skipped"] += 1
            continue
        counts["decided" if decided else "skipped"] += 1
    return counts


# ---------------------------------------------------------------- settling

def judge(entry: Dict[str, Any], patch_ids: List[str], now: datetime) -> Dict[str, Any]:
    """The outcome of one revert from the agent's result entry: ``{"outcome": reverted | not_reverted, "reason",
    "reboot", "at"}``. Reverted needs a success for at least one id and no id that failed; an id the install job
    did not change (``not_changed_by_job``) is neither. Anything missing from the result is a failure, never a
    revert (PROH-84-02c)."""
    results = [r for r in entry.get("results") or [] if isinstance(r, dict)]
    by_id = {str(r.get("patch_id")): r for r in results}
    ok = unchanged = 0
    reboot = False
    failures: List[str] = []
    for patch_id in patch_ids or list(by_id):
        found = by_id.get(patch_id) or {}
        status = str(found.get("status")).casefold()
        if status == "success":
            ok += 1
            reboot = reboot or bool(found.get("reboot_required"))
        elif status == "skipped" and found.get("code") == "not_changed_by_job":
            unchanged += 1
        else:
            failures.append(str(found.get("code") or "failed"))
    at = store.parse_time(entry.get("reportedAt")) or now
    if failures or not ok:
        reason = _best_reason(failures) if failures else "not_changed_by_job"
        return {"outcome": "not_reverted", "reason": reason, "reboot": reboot, "at": at}
    return {"outcome": "reverted", "reason": None, "reboot": reboot, "at": at}


async def _row_outcome(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any], action_id: str,
                       job_id: str, now: datetime) -> Optional[Dict[str, Any]]:
    """One revert's outcome, or None while the agent is still working on it."""
    job = await raw(db).patch_deployment_jobs.find_one(
        {"id": job_id, "tenantId": tenant_id, "rolloutId": rollout["id"]}, {"_id": 0, "agentResults": 1, "patchIds": 1})
    entry = ((job or {}).get("agentResults") or {}).get(result_key(host["agentId"]))
    if isinstance(entry, dict):
        return judge(entry, list((job or {}).get("patchIds") or []), now)
    row = await ledger.get(db, tenant_id, action_id)
    instruction_id = ((row or {}).get("instructionIds") or [None])[-1]
    task = await inflight.load_instruction(db, tenant_id, instruction_id)
    outcome = inflight.instruction_outcome(task, now, host.get("revertStartedAt"))
    if outcome not in ("not_delivered", "failed", "no_result"):
        return None
    # The computer never had the revert, answered FAILURE, or stayed silent past RESULT_DEADLINE: it is Not reverted
    # (never reverted, never reverting for ever), and the revert job it will not answer is closed.
    await inflight.close_job(db, tenant_id, job_id, now, rm.NOT_REVERTED["no_answer"])
    await inflight.cancel_unfetched(db, tenant_id, instruction_id, now)       # a late fetch must not run it (WR-27)
    refused = inflight.status_of(task) in inflight.NOT_DELIVERED_STATES
    return {"outcome": "not_reverted", "reason": "not_delivered" if refused else "no_answer", "reboot": False,
            "at": now}


async def _result_words(db, tenant_id: str, host: Dict[str, Any], action_id: str, found: Dict[str, Any]) -> str:
    """What one revert did, in words: the package or the Windows-update wording only from the agent's own success,
    else Not reverted with the reason (PROH-84-02c)."""
    if found.get("outcome") != "reverted":
        return _not_reverted_text(found.get("reason"))
    row = await ledger.get(db, tenant_id, action_id)
    ids = ", ".join(((row or {}).get("undo") or {}).get("params", {}).get("patch_ids") or [])
    if host.get("os") == "windows":
        return rm.fill(rm.ACTIVITY["revert_done_update"], patch=ids)
    return rm.fill(rm.ACTIVITY["revert_done_package"], patch=ids, host=host.get("hostname") or host["agentId"])


async def _settle_host(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any], now: datetime) -> str:
    """Move one reverting computer to Reverted or Not reverted once every one of its reverts has an outcome."""
    results = dict(host.get("revertResult") or {})
    pairs = list(zip(host.get("revertActionIds") or [], host.get("revertJobIds") or []))
    for action_id, job_id in pairs:
        if action_id not in results:
            found = await _row_outcome(db, tenant_id, rollout, host, action_id, job_id, now)
            if found is not None:
                results[action_id] = found
    if any(action_id not in results for action_id, _ in pairs):
        if results != (host.get("revertResult") or {}):
            await store.set_host(db, tenant_id, rollout["id"], host["agentId"], {"revertResult": results})
        return "reverting"
    bad = [v for v in results.values() if v["outcome"] == "not_reverted"]
    reboot = any(v.get("reboot") for v in results.values() if v["outcome"] == "reverted")
    fields: Dict[str, Any] = {"revertResult": results, "revertRebootNeeded": reboot}
    if bad:
        fields.update({"state": "not_reverted", "notRevertedReason": _best_reason([v["reason"] for v in bad])})
    else:
        fields.update({"state": "reverted", "revertedAt": max(store.aware(v["at"]) for v in results.values())})
    await store.set_host(db, tenant_id, rollout["id"], host["agentId"], fields)
    for action_id, found in results.items():
        if (host.get("revertResult") or {}).get(action_id) is None:           # a refused one was said when it was refused
            await _say(db, tenant_id, rollout, host, action_id, await _result_words(db, tenant_id, host, action_id, found))
    return str(fields["state"])


async def _raise_restart_lines(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> int:
    """The Revert restart line (D-15): one ``reboot_host`` approval row per computer whose revert needs a restart,
    once. The caller must not call this while a stop is on (a stopped ``decide`` records a refused row each time)."""
    from . import lines            # lines imports dispatcher, which imports this package's other modules
    waiting = [h for h in await store.host_docs(db, tenant_id, rollout["id"])
               if h.get("revertRebootNeeded") and h.get("state") in ("reverted", "not_reverted")
               and not (h.get("lineActionIds") or {}).get("revert_reboot")]
    raised = 0
    for ring in sorted({int(h.get("ring") or 0) for h in waiting}):
        entries = [(h, reboots.COMMAND, reboots.reboot_params()) for h in sorted(waiting, key=reboots._order)
                   if int(h.get("ring") or 0) == ring]
        made = await lines.raise_line(db, tenant_id, rollout, ring, "revert_reboot", entries, now)
        raised += made["raised"]
    return raised


async def _settle_restarts(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> None:
    """A Revert restart that was sent: a new boot ends its row and clears the need; 30 minutes past the due time
    without one fails the row (the need stays on the computer's card)."""
    for host in await store.host_docs(db, tenant_id, rollout["id"]):
        sent = host.get("revertRestart")
        ids = (host.get("lineActionIds") or {}).get("revert_reboot") or []
        if not isinstance(sent, dict) or sent.get("done") or not ids:
            continue
        stand_in = {"baselineBootTime": sent.get("baselineBootTime"), "dispatchedRebootAt": sent.get("dispatchedAt"),
                    "scheduledRestartAt": sent.get("scheduledAt")}
        agent = await raw(db).agents.find_one({"id": host["agentId"], "tenantId": tenant_id}, _AGENT_FIELDS)
        if reboots.is_new_boot(agent, stand_in) is True:
            booted = datetime.fromtimestamp(start.boot_time_of(agent), tz=timezone.utc)
            await ledger.transition(db, tenant_id, ids[-1], ("dispatching",), "executed", reasonCode="rollout_restarted",
                                    **await reboots.restart_words(db, tenant_id, rollout, host, booted))
            await store.set_host(db, tenant_id, rollout["id"], host["agentId"],
                                 {"revertRebootNeeded": False, "revertRestart": {**sent, "done": "restarted"}})
        elif reboots.overdue(stand_in, now):
            await ledger.transition(db, tenant_id, ids[-1], ("dispatching",), "failed", reasonCode="rollout_no_new_boot",
                                    reasonText=messages.REASON_TEXT["rollout_no_new_boot"])
            await store.set_host(db, tenant_id, rollout["id"], host["agentId"],
                                 {"revertRestart": {**sent, "done": "no_new_boot"}})


async def settle_reverts(db, tenant_id: str, rollout: Dict[str, Any], now: datetime, *,
                         may_decide: bool = True) -> Dict[str, int]:
    """Settle every reverting computer from what its agent reported, also while a stop is on. A result that says a
    restart is needed raises the Revert restart line when ``may_decide`` (no stop, tenant not Off); otherwise the
    need stays on the computer and the line is raised on the first pass that may. Returns counts by new state."""
    counts: Dict[str, int] = {}
    for host in await store.host_docs(db, tenant_id, rollout["id"]):
        if host.get("state") != "reverting":
            continue
        try:
            new_state = await _settle_host(db, tenant_id, rollout, host, now)
        except Exception as exc:
            logger.error("autonomous_ops: rollout %s could not settle the revert on %s: %s", rollout["id"],
                         host["agentId"], exc)
            continue
        counts[new_state] = counts.get(new_state, 0) + 1
    try:
        if may_decide:
            counts["restart_lines"] = await _raise_restart_lines(db, tenant_id, rollout, now)
        await _settle_restarts(db, tenant_id, rollout, now)
    except Exception as exc:
        logger.error("autonomous_ops: rollout %s could not settle the revert restarts: %s", rollout["id"], exc)
    return counts


async def tick(db, tenant_id: str, rollout: Dict[str, Any], now: datetime, *, may_decide: bool = True) -> None:
    """One controller pass over a halted rollout: start the revert of anything that installed since the last
    pass (a result that arrived after the halt), then settle what is running."""
    reason = rollout.get("haltReason") if isinstance(rollout.get("haltReason"), dict) else {}
    ring = int(reason.get("ring", rollout.get("currentRing") or 0) or 0)
    await start_ring_revert(db, tenant_id, rollout, ring, now)
    await settle_reverts(db, tenant_id, rollout, now, may_decide=may_decide)
