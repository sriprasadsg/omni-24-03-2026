"""The security stage of the sweep (Phase 83, RESP-01 / RESP-08): one source suggests, two sources act.

For one tenant per tick: observe the signals, and for each indicator seen on a host decide what it is
worth.
* Two different origins whose first sightings are at most 24 hours apart (or one, when the tenant turned
  the two-source rule off) mean an automatic ``block_ip`` through the gate (D-03, D-04). The gate records
  the decision first; only a row it records as ``dispatching`` is sent, through ``security_response``.
  An open suggestion for the same indicator then ends ``expired`` with reasonCode ``superseded``.
* One origin only records a suggestion (``gate.suggest``, key ``...|sweep-suggest|...``): no instruction
  is written and nothing is approved by it. While the origin is still being seen the suggestion is kept
  alive (``ledger.refresh_suggestion``), so a second origin that arrives after 24 hours finds a suggestion,
  and leaves it one.
* File candidates (a sha256 with a path) are observed and suggested here; the automatic quarantine
  decision is a later plan (83-11), and ranges are 83-08.
* After a block has run out (``blockedUntil`` passed) evidence dated before the block began no longer
  counts (D-14). Expiry is never treated as an undo and writes no ledger state.

Only structured fields decide anything. This module calls no model and reads no free text from an alert,
finding or ticket (PROH-83-01). A host that cannot carry the action right now (capability not ticked,
offline, no token) gets no row at all.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import APPROVAL_TTL, agent_support, gate, ledger, messages, response_dispatch, response_messages as rm, signals
from .settings import TenantSettings

logger = logging.getLogger(__name__)

RULE_ID = "sweep:block_ip"
SUGGEST_RULE_ID = "sweep:single_signal"
HOUR = 3600
_COMMANDS = {"ip": "block_ip", "file": "quarantine_file"}


async def _block_window(db, tenant_id: str, candidate: signals.Candidate):
    """(began, until) of the block the sweep last dispatched for this signal. The ledger row holds the real
    window and is read first; the sweep's own memory is the fallback (no recorded window: 24 hours from the
    decision, the default length)."""
    decision = candidate.decision or {}
    row = await ledger.get(db, tenant_id, decision["actionId"]) if decision.get("actionId") else None
    began = (row or {}).get("blockedFrom") or decision.get("blockedFrom")
    until = (row or {}).get("blockedUntil") or decision.get("blockedUntil")
    if not isinstance(until, datetime) and isinstance(decision.get("at"), datetime):
        until = decision["at"] + timedelta(hours=24)
    return (began if isinstance(began, datetime) else None), (until if isinstance(until, datetime) else None)


def _ordered(live: Dict[str, Dict[str, Any]]) -> List[str]:
    """Origin ids by first sighting, the earliest first (ties by id)."""
    return sorted(live, key=lambda n: (live[n]["firstSeenAt"], n))


def _agreeing(live: Dict[str, Dict[str, Any]]) -> List[str]:
    """The origins an action is decided on, in sorted order: those first seen within 24 hours of the
    earliest pair that agreed, or just the earliest one when none did (the rule is off)."""
    order = _ordered(live)
    for a, b in zip(order, order[1:]):
        if live[b]["firstSeenAt"] - live[a]["firstSeenAt"] <= signals.CORROBORATION_WINDOW:
            start = live[a]["firstSeenAt"]
            return sorted(n for n in order if live[n]["firstSeenAt"] - start <= signals.CORROBORATION_WINDOW)
    return order[:1]


def _words(builder, *args) -> Optional[str]:
    try:
        return builder(*args)
    except (KeyError, ValueError):
        return None                  # an unknown origin id is never shown raw


def _keys(tenant_id: str, candidate: signals.Candidate, command: str):
    tail = f"{command}|{candidate.agent_id}|{candidate.indicator}"
    return f"{tenant_id}|sweep|{tail}", f"{tenant_id}|sweep-suggest|{tail}"


def _suggest_request(tenant_id, candidate, command, origins, response, key) -> gate.ActionRequest:
    if command == "block_ip":
        params = {"ip_address": candidate.indicator, "ttl_seconds": response.block_hours * HOUR}
    else:
        params = {"path": candidate.path, "sha256": candidate.indicator}
    inputs = {"suggestionOnly": True, "origins": origins, "indicator": candidate.indicator,
              "twoSignal": response.two_signal, "suggestion": {"kind": "single_signal"}}
    return gate.ActionRequest(
        tenant_id=tenant_id, kind="security", origin="sweep", actions=[command], targets=[candidate.agent_id],
        params=params, dedupe_key=key, reason={"ruleId": SUGGEST_RULE_ID, "inputs": inputs},
        reason_text=_words(rm.why_one_source, origins[0]), dispatcher=response_dispatch.DISPATCHER_NAME)


def _act_request(tenant_id, candidate, origins, response, key) -> gate.ActionRequest:
    ip = candidate.indicator
    text = _words(rm.why_two_sources, origins) if len(origins) > 1 else _words(rm.why_rule_off, origins[0])
    return gate.ActionRequest(
        tenant_id=tenant_id, kind="security", origin="sweep", actions=["block_ip"], targets=[candidate.agent_id],
        params={"ip_address": ip, "ttl_seconds": response.block_hours * HOUR}, dedupe_key=key,
        reason={"ruleId": RULE_ID, "inputs": {"origins": origins, "indicator": ip, "twoSignal": response.two_signal}},
        reason_text=text, dispatcher=response_dispatch.DISPATCHER_NAME)


async def _keep_alive(db, tenant_id: str, key: str, origins: List[str], now: datetime) -> None:
    """An open suggestion whose origin is still being seen: extend its expiry once half of it is gone, and
    bring its origins up to date (that also moves it to the top). Nothing is written otherwise, so a tick
    that learned nothing changes no row."""
    row = await ledger.open_row(db, tenant_id, key, ("suggested",))
    if row is None:
        return
    inputs = dict((row.get("reason") or {}).get("inputs") or {})
    fresh = {**inputs, "origins": origins}
    expires = (row.get("approval") or {}).get("expiresAt")
    if fresh == inputs and isinstance(expires, datetime) and expires - now >= APPROVAL_TTL / 2:
        return
    await ledger.refresh_suggestion(db, tenant_id, row["id"], inputs=fresh, expires_at=now + APPROVAL_TTL,
                                    touch_created=fresh != inputs, now=now)


async def _supersede(db, tenant_id: str, suggest_key: str) -> None:
    """A decision was recorded for the indicator: its open suggestion is now an action."""
    row = await ledger.open_row(db, tenant_id, suggest_key, ("suggested",))
    if row is not None:
        await ledger.transition(db, tenant_id, row["id"], ("suggested",), "expired", reasonCode="superseded",
                                reasonText=messages.REASON_TEXT["superseded"])


async def _suggest(db, tenant_id, candidate, command, origins, response, now, counts) -> None:
    _, suggest_key = _keys(tenant_id, candidate, command)
    decision = await gate.suggest(db, _suggest_request(tenant_id, candidate, command, origins, response, suggest_key), now=now)
    if decision.state == "shadow":
        counts["shadow"] += 1
    elif decision.recorded:
        counts["suggested"] += 1
    elif decision.reason == "duplicate":
        await _keep_alive(db, tenant_id, suggest_key, origins, now)


async def _dispatch(db, tenant_id, candidate, decision, origins, now, counts) -> None:
    if decision.state == "shadow":
        counts["shadow"] += 1
        return
    if decision.state != "dispatching" or not decision.action_id:
        return
    row = await ledger.get(db, tenant_id, decision.action_id)
    if row is None:
        return
    sent = await response_dispatch.send(db, row)
    if sent.get("status") != "queued":
        return
    counts["blocked"] += 1
    after = await ledger.get(db, tenant_id, decision.action_id) or {}
    key = {"tenantId": tenant_id, "agentId": candidate.agent_id, "kind": candidate.kind, "indicator": candidate.indicator}
    memory: Dict[str, Any] = {"actionId": decision.action_id, "at": now, "outcome": "blocked", "origins": origins}
    for field in ("blockedFrom", "blockedUntil"):
        if after.get(field) is not None:
            memory[field] = after[field]
    await signals.remember(db, key, memory)


async def _act(db, tenant_id, candidate, origins, response, agent, now, counts, until) -> None:
    key, suggest_key = _keys(tenant_id, candidate, "block_ip")
    if (until is not None and now < until) or await agent_support.check(db, tenant_id, agent, "block_ip", now=now):
        counts["skipped"] += 1
        return
    decision = await gate.decide(db, _act_request(tenant_id, candidate, origins, response, key), now=now)
    if decision.recorded:
        await _supersede(db, tenant_id, suggest_key)
    await _dispatch(db, tenant_id, candidate, decision, origins, now, counts)


async def run(db, tenant_id: str, tenant: TenantSettings, response, now: datetime) -> Dict[str, int]:
    """One tenant's pass. Returns counts {observed, blocked, suggested, shadow, skipped}."""
    counts = {"observed": 0, "blocked": 0, "suggested": 0, "shadow": 0, "skipped": 0}
    agents = await signals.agents_of(db, tenant_id)
    by_id = {a["id"]: a for a in agents}
    for candidate in await signals.observe(db, tenant_id, agents, now):
        counts["observed"] += 1
        command = _COMMANDS.get(candidate.kind)
        if command is None:                                      # ranges wait for 83-08
            continue
        began, until = await _block_window(db, tenant_id, candidate)
        after = began if began is not None and until is not None and until <= now else None      # D-14
        live = {n: v for n, v in signals.counting_origins(candidate, after).items()
                if isinstance(v.get("firstSeenAt"), datetime)}
        if not live:
            continue
        agree = signals.corroborated(candidate, two_signal=response.two_signal, evidence_after=after)
        if agree and candidate.kind == "file":                   # the automatic quarantine decision is 83-11
            continue
        if not agree and candidate.kind == "file" and not candidate.path:
            continue                                             # nothing to point a quarantine at
        agent = by_id.get(candidate.agent_id)
        if not agree:
            if await agent_support.check(db, tenant_id, agent, command, now=now):
                counts["skipped"] += 1
                continue
            await _suggest(db, tenant_id, candidate, command, _ordered(live)[:1], response, now, counts)
        else:
            await _act(db, tenant_id, candidate, _agreeing(live), response, agent, now, counts, until)
    return counts
