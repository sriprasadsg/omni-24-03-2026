"""The security stage of the sweep (Phase 83, RESP-01): a corroborated address becomes one gate decision.

For one tenant per tick: observe the signals, and for each address that two different origins named
on the same host within the allowed window (or one, when the tenant turned the two-source rule off)
ask the gate to decide a ``block_ip`` for that host. The gate records the decision first; only a row
it records as ``dispatching`` is sent, through the ``security_response`` dispatcher.

Only structured fields decide anything. This module calls no model and reads no free text from an
alert, finding or ticket (PROH-83-01). A host that cannot carry the action right now (capability not
ticked, offline, no token) gets no row at all.

The sweep's memory of a block it dispatched (``signals.remember``) keeps later ticks silent while the
block lasts; it is the verify step and the person's undo that end or confirm a block, never a repeat.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from . import agent_support, gate, ledger, response_dispatch, signals
from .settings import TenantSettings

logger = logging.getLogger(__name__)

RULE_ID = "sweep:block_ip"
HOUR = 3600


def _remembered_block_holds(candidate: signals.Candidate, now: datetime) -> bool:
    """True while the sweep's own memory says a block it dispatched is still in force."""
    decision = candidate.decision
    if not decision:
        return False
    until = decision.get("blockedUntil")
    if not isinstance(until, datetime) and isinstance(decision.get("at"), datetime):
        until = decision["at"] + timedelta(hours=24)       # no recorded window: hold for the default length
    return isinstance(until, datetime) and now < until


def _request(tenant_id: str, candidate: signals.Candidate, response) -> gate.ActionRequest:
    ip = candidate.indicator
    return gate.ActionRequest(
        tenant_id=tenant_id, kind="security", origin="sweep", actions=["block_ip"], targets=[candidate.agent_id],
        params={"ip_address": ip, "ttl_seconds": response.block_hours * HOUR},
        dedupe_key=f"{tenant_id}|sweep|block_ip|{candidate.agent_id}|{ip}",
        reason={"ruleId": RULE_ID, "inputs": {"origins": sorted(candidate.origins), "indicator": ip}},
        dispatcher=response_dispatch.DISPATCHER_NAME)


async def run(db, tenant_id: str, tenant: TenantSettings, response, now: datetime) -> Dict[str, int]:
    """One tenant's pass. Returns counts {observed, blocked, shadow, skipped}."""
    counts = {"observed": 0, "blocked": 0, "shadow": 0, "skipped": 0}
    agents = await signals.agents_of(db, tenant_id)
    by_id = {a["id"]: a for a in agents}
    for candidate in await signals.observe(db, tenant_id, agents, now):
        counts["observed"] += 1
        if candidate.kind != "ip" or not signals.corroborated(candidate, two_signal=response.two_signal):
            continue
        if _remembered_block_holds(candidate, now):
            counts["skipped"] += 1
            continue
        agent = by_id.get(candidate.agent_id)
        if await agent_support.check(db, tenant_id, agent, "block_ip", now=now):
            counts["skipped"] += 1
            continue
        decision = await gate.decide(db, _request(tenant_id, candidate, response), now=now)
        if decision.state == "shadow":
            counts["shadow"] += 1
            continue
        if decision.state != "dispatching" or not decision.action_id:
            continue
        row = await ledger.get(db, tenant_id, decision.action_id)
        if row is None:
            continue
        sent = await response_dispatch.send(db, row)
        if sent.get("status") != "queued":
            continue
        counts["blocked"] += 1
        after = await ledger.get(db, tenant_id, decision.action_id) or {}
        key = {"tenantId": tenant_id, "agentId": candidate.agent_id, "kind": candidate.kind,
               "indicator": candidate.indicator}
        memory: Dict[str, Any] = {"actionId": decision.action_id, "at": now, "outcome": "blocked"}
        for field in ("blockedFrom", "blockedUntil"):
            if after.get(field) is not None:
                memory[field] = after[field]
        await signals.remember(db, key, memory)
    return counts
