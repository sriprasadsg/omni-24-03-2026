"""What follows a quarantine that ended badly (Phase 83, RESP-03 / RESP-05, D-06 and D-27).

``after`` runs for a ``security_response`` row once the reconciler has settled it, with the row and the agent's
stored instruction document. Two endings of a ``quarantine_file`` row lead to a person, never to an action:

* it failed ``locked`` (the file is in use): ONE ``kill_process`` approval line is added to the same incident,
  mode ``retry``. When a person approves it and the agent reports the processes gone, one more automatic
  ``quarantine_file`` decision follows, with ``reason.inputs.parentActionId`` set to the kill row (D-06);
* it moved the file but the process keeps running (``stillRunning``): the quarantine row stays Done and ONE
  ``kill_process`` approval line is added, mode ``kill_only``. At verified it clears ``stillRunning`` on the
  quarantine row, which then stops saying the process is running (D-27).

The chain is two rows, never one multi-step row, so undo and the reconciler stay simple; the incident route
folds them into one line from ``reason.inputs.chain`` = {mode, quarantineActionId, path, sha256, process}.

Bounds. A retry (a row with ``parentActionId``) never opens a card, whatever it reports: the chain stops after
one try. The sweep is told to hold the finding for a day after the retry settles, so it does not start the
chain again an hour later. A kill row that failed, was refused or survived adds nothing. A kill card a person
denied or let expire is not raised again for 24 hours.

PROH-83-15: nothing here ends a process. The kill line is decided through ``gate.decide``, which makes it an
approval card (the registry class of ``kill_process``); this module never sends it. Only the quarantine retry is
sent, through ``response_dispatch.send``, and this module writes no agent instruction itself.

The kill parameters bind an approval, which can be a day old, to the processes the host listed: the program
(``expected_exe``, the quarantined path), the ``pid`` and ``start_time`` of each listed process and, once the file
moved, the quarantine's id so the agent works out the stored image itself (the backend never sends that path).

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import COOLDOWN, gate, ledger, response_dispatch, response_messages as rm, signals, verify
from .scope import raw

logger = logging.getLogger(__name__)

KILL_RULE_ID = "sweep:kill_process"
RETRY_RULE_ID = "sweep:quarantine_file"
RETRY = "retry"
KILL_ONLY = "kill_only"
_DECLINED = ("denied", "expired")
_SECURITY = response_dispatch.DISPATCHER_NAME


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _inputs(row: Dict[str, Any]) -> Dict[str, Any]:
    return _dict(_dict(row.get("reason")).get("inputs"))


def _agent_of(row: Dict[str, Any]) -> Optional[str]:
    targets = row.get("targets")
    return targets[0] if isinstance(targets, list) and targets and isinstance(targets[0], str) else None


def _listed(processes: List[Dict[str, Any]]) -> List[Dict[str, int]]:
    """Only the pair that tells one process from a later one that reused its pid."""
    return [{"pid": p["pid"], "start_time": p["start_time"]} for p in processes]


async def _declined_recently(db, tenant_id: str, key: str, now: datetime) -> bool:
    """A person said no (or let the card lapse) to this very kill line in the last 24 hours."""
    found = await raw(db).autonomy_actions.find_one(
        {"tenantId": tenant_id, "dedupeKey": key, "state": {"$in": list(_DECLINED)},
         "createdAt": {"$gt": now - COOLDOWN}}, {"_id": 1})
    return found is not None


async def _propose_kill(db, tenant_id: str, row: Dict[str, Any], processes: List[Dict[str, Any]], mode: str,
                        now: Optional[datetime]) -> Optional[str]:
    """Add the one kill approval line for a quarantine row. Returns "kill_card" when the gate recorded it."""
    params, agent, ids = _dict(row.get("params")), _agent_of(row), row.get("instructionIds") or []
    path, sha = params.get("path"), params.get("sha256")
    if not (agent and isinstance(path, str) and path and isinstance(sha, str) and sha and processes):
        return None
    if mode == KILL_ONLY and not ids:
        return None
    key = f"{tenant_id}|sweep|kill_process|{agent}|{sha}"
    if await _declined_recently(db, tenant_id, key, now or datetime.now(timezone.utc)):
        return None
    kill = {"target": str(processes[0]["pid"]), "expected_exe": path, "processes": _listed(processes)}
    if mode == KILL_ONLY:
        kill["quarantine_id"] = ids[0]                  # the quarantine's own instruction id: the agent finds the stored image
    inputs = _inputs(row)
    first = processes[0]
    chain = {"mode": mode, "quarantineActionId": row["id"], "path": path, "sha256": sha,
             "process": {"pid": first["pid"], "name": first["name"], "start_time": first["start_time"]}}
    detail = {k: inputs[k] for k in ("incidentId", "origins", "indicator", "twoSignal") if k in inputs}
    text = rm.REASON_TEXT["locked"] if mode == RETRY else rm.NOTICES["kill_only"]
    decision = await gate.decide(db, gate.ActionRequest(
        tenant_id=tenant_id, kind="security", origin="sweep", actions=["kill_process"], targets=[agent],
        params=kill, dedupe_key=key, reason={"ruleId": KILL_RULE_ID, "inputs": {**detail, "chain": chain}},
        reason_text=text, dispatcher=_SECURITY), now=now)
    return "kill_card" if decision.recorded else None


async def _after_quarantine(db, tenant_id: str, row: Dict[str, Any], doc: Optional[Dict[str, Any]],
                            now: Optional[datetime]) -> Optional[str]:
    if _inputs(row).get("parentActionId"):
        await _hold_finding(db, tenant_id, row, now)
        return None                                     # the retry is the last try: no second card, no third try
    state, code = row.get("state"), row.get("reasonCode")
    if state == "failed" and code == "locked":
        listed = verify.process_entries(_dict(_dict(doc).get("result")).get("still_running"))
        mode = RETRY
    elif state == "verified":
        listed, mode = verify.process_entries(row.get("stillRunning")), KILL_ONLY
    else:
        return None
    return await _propose_kill(db, tenant_id, row, listed, mode, now) if listed else None


async def _hold_finding(db, tenant_id: str, retry: Dict[str, Any], now: Optional[datetime]) -> None:
    """The retry settled: tell the sweep this finding was just handled, so it waits a day (a finished retry
    holds it as a done action does, a failed one for the cooldown) instead of starting again in an hour."""
    sha, agent = _dict(retry.get("params")).get("sha256"), _agent_of(retry)
    if not (isinstance(sha, str) and agent):
        return
    now = now or datetime.now(timezone.utc)
    memory = {"actionId": retry["id"], "at": now, "origins": _inputs(retry).get("origins") or []}
    if retry.get("state") in ("executed", "verified"):
        memory["outcome"] = "blocked"
    else:
        memory.update(outcome="failed", holdUntil=now + COOLDOWN)
    try:
        await signals.remember(db, {"tenantId": tenant_id, "agentId": agent, "kind": "file", "indicator": sha}, memory)
    except Exception as exc:
        logger.error("autonomous_ops: the retry of %s could not be remembered: %s", retry.get("id"), exc)


async def _retry(db, tenant_id: str, kill: Dict[str, Any], now: Optional[datetime]) -> Optional[str]:
    """The kill ended the processes: decide the quarantine once more, automatically, under the same gate,
    rate limit and breaker as any automatic quarantine (D-06), and send it when the gate says so."""
    chain = _dict(_inputs(kill).get("chain"))
    original = await ledger.get(db, tenant_id, chain.get("quarantineActionId") or "")
    agent, path, sha = _agent_of(kill), chain.get("path"), chain.get("sha256")
    if original is None or not (agent and isinstance(path, str) and path and isinstance(sha, str) and sha):
        return None
    params: Dict[str, Any] = {"path": path, "sha256": sha}
    if _dict(original.get("params")).get("allow_protected") is True:
        params["allow_protected"] = True                # the person who approved the card for a system file approved this too
    inputs = {k: v for k, v in _inputs(original).items() if k not in ("suggestion", "suggestionOnly")}
    inputs["parentActionId"] = kill["id"]
    decision = await gate.decide(db, gate.ActionRequest(
        tenant_id=tenant_id, kind="security", origin="sweep", actions=["quarantine_file"], targets=[agent],
        params=params, dedupe_key=f"{tenant_id}|sweep|quarantine_file|{agent}|{sha}|retry",
        reason={"ruleId": RETRY_RULE_ID, "inputs": inputs}, reason_text=original.get("reasonText"),
        dispatcher=_SECURITY), now=now)
    if not decision.recorded or not decision.action_id:
        return None
    if decision.state == "dispatching":
        retry = await ledger.get(db, tenant_id, decision.action_id)
        if retry is not None:
            await response_dispatch.send(db, retry)
    return "retry"


async def _clear_still_running(db, tenant_id: str, quarantine_id: Any, now: Optional[datetime]) -> None:
    """The process is gone: the quarantine row stops saying it runs. No state change, so no audit event."""
    if isinstance(quarantine_id, str) and quarantine_id:
        await raw(db).autonomy_actions.update_one(
            {"id": quarantine_id, "tenantId": tenant_id},
            {"$set": {"stillRunning": [], "updatedAt": now or datetime.now(timezone.utc)}})


async def _after_kill(db, tenant_id: str, row: Dict[str, Any], now: Optional[datetime]) -> Optional[str]:
    chain = _dict(_inputs(row).get("chain"))
    state = row.get("state")
    if state not in ("executed", "verified"):
        return None                                     # failed, refused or survived: nothing follows
    if chain.get("mode") == KILL_ONLY:
        if state == "verified":
            await _clear_still_running(db, tenant_id, chain.get("quarantineActionId"), now)
            return "cleared"
        return None
    if chain.get("mode") == RETRY:
        return await _retry(db, tenant_id, row, now)
    return None


async def after(db, tenant_id: str, row: Dict[str, Any], doc: Optional[Dict[str, Any]], *,
                now: Optional[datetime] = None) -> Optional[str]:
    """Follow up one settled ``security_response`` row. Returns "kill_card", "retry", "cleared" or None.
    Every decision goes through ``gate.decide``; the caller keeps a failure here from undoing the row change."""
    if not isinstance(row, dict) or row.get("dispatcher") != _SECURITY:
        return None
    if row.get("command") == "quarantine_file":
        return await _after_quarantine(db, tenant_id, row, doc, now)
    if row.get("command") == "kill_process":
        return await _after_kill(db, tenant_id, row, now)
    return None
