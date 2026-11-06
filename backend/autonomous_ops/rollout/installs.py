"""The canary install: the one step of a rollout that runs on its own (PTCH-06), and the lines around it.

Only ring 0 installs automatically, only on a computer whose agent reports the reversibility check
(``patch_reversible_check``) and whose tenant has the patch installer capability, and only for patches
that do not usually need a restart. An agent that cannot check is never treated as reversible
(PROH-84-04), and a patch that usually needs a restart (D-06) or that the agent reported deferred
``not_reversible`` (D-05) goes to an approval line for that computer (``lines.raise_line``). Every later ring
is all approval lines (``raise_ring``). One computer can hold an automatic row for its reversible patches
and an approval row for its other patches in the same ring; it counts as installed only when both settled.

Every install is one ledger row decided by ``gate.decide`` and sent by ``gate.execute`` with
``expires_at`` set to the end of the window occurrence in force, so a late instruction is never
delivered (PTCH-05). Nothing in this module writes an agent queue or builds an instruction.

Raw Mongo handle with an explicit tenantId only.
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import agent_capabilities

from .. import RATE_LIMIT_PER_WINDOW, RATE_LIMIT_WINDOW, agent_support, gate, ledger, messages
from ..scope import raw
from . import (CAPABILITY, COMMAND_INSTALL, DISPATCHER_NAME, MAX_ATTEMPTS, TOKEN_REVERSIBLE, lines,
               messages as rm, needs_restart_by_name, store)

logger = logging.getLogger(__name__)

_AGENT_FIELDS = {"_id": 0, "id": 1, "tenantId": 1, "hostname": 1, "status": 1, "lastSeen": 1, "platform": 1,
                 "meta.response_actions": 1}


def dedupe_key(tenant_id: str, rollout_id: str, ring: int, line: str, agent_id: str, attempt: int) -> str:
    """One key per host, line and attempt, so an undone row never suppresses a later attempt."""
    return f"{tenant_id}|{DISPATCHER_NAME}|{rollout_id}|{ring}|{line}|{agent_id}|{attempt}"


def install_request(tenant_id: str, rollout: Dict[str, Any], ring: int, host: Dict[str, Any], job_id: str,
                    attempt: int, patch_ids: List[str]) -> gate.ActionRequest:
    return gate.ActionRequest(
        tenant_id=tenant_id, kind="patching", origin="rollout", actions=[COMMAND_INSTALL],
        targets=[host["agentId"]],
        params={"patch_ids": patch_ids, "job_id": job_id, "require_reversible": True},
        dedupe_key=dedupe_key(tenant_id, rollout["id"], ring, "install", host["agentId"], attempt),
        reason={"ruleId": "rollout:canary_install",
                "inputs": {"rolloutId": rollout["id"], "ring": ring, "line": "install", "attempt": attempt,
                           "patchIds": patch_ids}},
        reason_text=rm.fill(rm.ACTIVITY["canary_why"], rollout=rollout.get("name") or "", patch=", ".join(patch_ids)),
        dispatcher=DISPATCHER_NAME)


def unresolved(host: Dict[str, Any]) -> List[str]:
    """The host's patches that no approval row has been raised for yet."""
    raised = set(host.get("linePatchIds") or [])
    return [p for p in host.get("patchIds") or [] if p not in raised]


def deferred_pending(host: Dict[str, Any]) -> List[str]:
    """Patches the agent deferred as not reversible that still have no approval row."""
    raised = set(host.get("linePatchIds") or [])
    return [p for p in host.get("deferredIds") or [] if p not in raised]


def needs_decision(host: Dict[str, Any], ring_index: int) -> bool:
    """True when a waiting computer still needs the controller to decide something for it: the canary's
    automatic row or an approval row, or an approval row for later rings."""
    if host.get("state") != "waiting":
        return False
    if deferred_pending(host):
        return True
    if ring_index == 0 and host.get("installActionId"):
        return False
    return bool(unresolved(host))


async def host_agent(db, tenant_id: str, host: Dict[str, Any], permitted, now: datetime) -> Optional[Dict[str, Any]]:
    """The host's agent when the tenant has the patch installer capability and it is online, else None."""
    agent = await raw(db).agents.find_one({"id": host["agentId"], "tenantId": tenant_id}, _AGENT_FIELDS)
    if agent is None or CAPABILITY not in permitted or not agent_support.online(agent, now):
        return None
    return agent


def split_canary(host: Dict[str, Any], reversible: bool) -> Dict[str, List[str]]:
    """(D-05, D-06) The canary host's patches that need a person and those that may install on their own.
    Without the reversibility check everything needs a person; a name from the usually-restart-needing list,
    or a patch the agent deferred as not reversible, always does."""
    deferred = set(host.get("deferredIds") or [])
    pending = unresolved(host)
    by_person = [p for p in pending if p in deferred or not reversible or needs_restart_by_name(p)]
    for p in deferred_pending(host):
        if p not in by_person:
            by_person.append(p)
    automatic = [p for p in pending if p not in by_person]
    return {"person": by_person, "automatic": automatic}


async def _fail_undelivered(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any], action_id: str,
                            attempt: int) -> None:
    await ledger.transition(db, tenant_id, action_id, ("dispatching",), "failed", reasonCode="rollout_not_delivered",
                            reasonText=messages.REASON_TEXT["rollout_not_delivered"])
    await store.set_host(db, tenant_id, rollout["id"], host["agentId"], retry_fields(host, attempt))


def retry_fields(host: Dict[str, Any], attempt: int) -> Dict[str, Any]:
    """Put a host back to waiting after an install that never reached it, or stop trying after
    MAX_ATTEMPTS (the host then reads failed with the reason)."""
    base = {"installActionId": None, "installJobId": None, "installInstructionId": None, "attempt": attempt,
            "autoSettled": False}
    if attempt >= MAX_ATTEMPTS:
        return {**base, "state": "failed", "failureMessage": messages.REASON_TEXT["rollout_not_delivered"]}
    return {**base, "state": "waiting"}


async def canary_auto(db, tenant_id: str, rollout: Dict[str, Any], ring_index: int, hosts: List[Dict[str, Any]],
                      now: datetime, window_close: datetime) -> Dict[str, int]:
    """Decide the canary ring for the computers that need a decision, in (hostname, agent id) order: one
    approval row for the patches that need a person, one automatic install for the rest. Returns counts of
    ``sent``, ``simulated``, ``held`` (the gate asked for a person), ``raised`` (approval rows) and
    ``skipped``. The automatic installs of one pass are bounded by the hourly limit (20 minus the automatic
    actions in the last hour), so the 21st is never turned into a rate-limit card by accident; the computers
    beyond it stay waiting for a later pass."""
    counts = {"sent": 0, "simulated": 0, "held": 0, "skipped": 0, "raised": 0}
    if ring_index != 0:
        return counts
    permitted = await agent_capabilities.allowed_for(raw(db), tenant_id)
    try:
        recent = await ledger.count_auto_since(db, tenant_id, now - RATE_LIMIT_WINDOW)
    except Exception as exc:
        logger.error("autonomous_ops: rollout %s could not read the hourly count: %s", rollout["id"], exc)
        return counts
    budget = max(0, RATE_LIMIT_PER_WINDOW - recent)
    waiting = [h for h in hosts if h.get("ring") == ring_index and needs_decision(h, ring_index)]
    for host in sorted(waiting, key=lambda h: (str(h.get("hostname") or "").casefold(), h["agentId"])):
        agent = await host_agent(db, tenant_id, host, permitted, now)
        if agent is None:
            counts["skipped"] += 1
            continue
        split = split_canary(host, TOKEN_REVERSIBLE in agent_support.tokens_of(agent))
        if split["person"]:
            made = await lines.raise_line(db, tenant_id, rollout, ring_index, "install",
                                          [lines.install_entry(host, split["person"])], now)
            counts["raised"] += made["raised"]
            counts["simulated"] += made["simulated"]
            counts["skipped"] += made["skipped"]
        if not split["automatic"] or host.get("installActionId"):
            continue
        if budget <= 0:
            counts["skipped"] += 1
            continue
        attempt = int(host.get("attempt") or 0) + 1
        job_id = uuid.uuid4().hex
        request = install_request(tenant_id, rollout, ring_index, host, job_id, attempt, split["automatic"])
        decision = await gate.decide(db, request, now=now)
        if not decision.recorded or not decision.action_id:
            counts["skipped"] += 1
            continue
        if decision.shadow:
            await store.set_host(db, tenant_id, rollout["id"], host["agentId"],
                                 {"state": "would_install", "installActionId": decision.action_id, "attempt": attempt})
            counts["simulated"] += 1
        elif decision.state == "dispatching":
            budget -= 1
            await _send(db, tenant_id, rollout, host, decision.action_id, job_id, attempt, now, window_close, counts,
                        split["automatic"])
        else:       # the gate wants a person (limits, a stop on the tenant's side): remember the row, do nothing
            await store.set_host(db, tenant_id, rollout["id"], host["agentId"],
                                 {"installActionId": decision.action_id, "attempt": attempt})
            counts["held"] += 1
    return counts


async def raise_ring(db, tenant_id: str, rollout: Dict[str, Any], ring_index: int, hosts: List[Dict[str, Any]],
                     now: datetime) -> Dict[str, int]:
    """Every install after the canary waits for a person (PTCH-06): one approval row per waiting computer
    that has the capability and is online, in (hostname, agent id) order. Nothing is sent."""
    counts = {"raised": 0, "simulated": 0, "skipped": 0}
    permitted = await agent_capabilities.allowed_for(raw(db), tenant_id)
    entries = []
    waiting = [h for h in hosts if h.get("ring") == ring_index and needs_decision(h, ring_index)]
    for host in sorted(waiting, key=lambda h: (str(h.get("hostname") or "").casefold(), h["agentId"])):
        if await host_agent(db, tenant_id, host, permitted, now) is None:
            counts["skipped"] += 1
            continue
        entries.append(lines.install_entry(host, unresolved(host) + [p for p in deferred_pending(host) if p not in unresolved(host)]))
    made = await lines.raise_line(db, tenant_id, rollout, ring_index, "install", entries, now)
    for key, value in made.items():
        counts[key] += value
    return counts


async def _send(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any], action_id: str, job_id: str,
                attempt: int, now: datetime, window_close: datetime, counts: Dict[str, int],
                patch_ids: List[str]) -> None:
    from patch_core_endpoints import new_patch_job
    job = new_patch_job(job_id, tenant_id, patch_ids, [host["agentId"]], [host["agentId"]], "Autonomous Ops",
                        "Rollout", None, now.isoformat(), "In Progress")
    job["rolloutId"] = rollout["id"]
    await raw(db).patch_deployment_jobs.insert_one(job)
    params = {"patch_ids": patch_ids, "job_id": job_id, "require_reversible": True}
    sent = await gate.execute(db, tenant_id, action_id, command=COMMAND_INSTALL, agent_id=host["agentId"],
                              params=params, kind="action", expires_at=window_close)
    if sent.get("status") != "queued":
        await _fail_undelivered(db, tenant_id, rollout, host, action_id, attempt)
        counts["skipped"] += 1
        return
    await store.set_host(db, tenant_id, rollout["id"], host["agentId"], {
        "state": "installing", "waitReason": None, "installActionId": action_id, "installJobId": job_id,
        "installInstructionId": sent["task_id"], "installDispatchedAt": now, "attempt": attempt, "autoSettled": False})
    counts["sent"] += 1
