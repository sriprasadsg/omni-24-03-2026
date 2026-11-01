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
  decision is a later plan (83-11).
* A range (a network a feed lists and a host has talked to) follows the same rules as an address but with
  params ``{cidr, ttl_seconds}``: one origin suggests it, and two corroborating origins reach the gate,
  which always turns a network into an approval card (``range_block``, RESP-02). The sweep never writes an
  instruction for a range, and a host without the range token stays silent.
* After a block has run out (``blockedUntil`` passed) evidence dated before the block began no longer
  counts (D-14). Expiry is never treated as an undo and writes no ledger state.
* Nothing repeats (RESP-07): every recorded decision is remembered on the signal (``signals.remember``)
  and ``sweep_memory.skip_reason`` keeps the finding quiet for the outcome's window before the gate is
  asked again. Inside 24 hours of an undo the sweep records one refused row saying so and sends nothing.
  The fourth automatic block or quarantine on one computer in a rolling hour becomes an approval card.

Only structured fields decide anything. This module calls no model and reads no free text from an alert,
finding or ticket (PROH-83-01). A host that cannot carry the action right now (capability not ticked,
offline, no token) gets no row at all.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
from dataclasses import replace
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import (APPROVAL_TTL, COOLDOWN, RATE_LIMIT_WINDOW, agent_support, gate, incidents, ledger, messages,
               response_dispatch, response_messages as rm, signals, sweep_memory)
from .settings import TenantSettings

logger = logging.getLogger(__name__)

RULE_ID = "sweep:block_ip"
SUGGEST_RULE_ID = "sweep:single_signal"
HOUR = 3600
HOST_AUTO_LIMIT = 3                  # research default R2: automatic block or quarantine actions per computer per hour
_HOST_COMMANDS = ("block_ip", "quarantine_file")        # restarts do not count toward it
_COMMANDS = {"ip": "block_ip", "range": "block_ip", "file": "quarantine_file"}


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


def _block_params(candidate: signals.Candidate, response) -> Dict[str, Any]:
    """A block names one address, or for a range its normalised network (never both)."""
    key = "cidr" if candidate.kind == "range" else "ip_address"
    return {key: candidate.indicator, "ttl_seconds": response.block_hours * HOUR}


def _suggest_request(tenant_id, candidate, command, origins, response, key) -> gate.ActionRequest:
    if command == "block_ip":
        params = _block_params(candidate, response)
    else:
        params = {"path": candidate.path, "sha256": candidate.indicator}
    inputs = {"suggestionOnly": True, "origins": origins, "indicator": candidate.indicator,
              "twoSignal": response.two_signal, "suggestion": {"kind": "single_signal"}}
    return gate.ActionRequest(
        tenant_id=tenant_id, kind="security", origin="sweep", actions=[command], targets=[candidate.agent_id],
        params=params, dedupe_key=key, reason={"ruleId": SUGGEST_RULE_ID, "inputs": inputs},
        reason_text=_words(rm.why_one_source, origins[0]), dispatcher=response_dispatch.DISPATCHER_NAME)


def _act_request(tenant_id, candidate, origins, response, key, incident_id) -> gate.ActionRequest:
    ip = candidate.indicator
    text = _words(rm.why_two_sources, origins) if len(origins) > 1 else _words(rm.why_rule_off, origins[0])
    return gate.ActionRequest(
        tenant_id=tenant_id, kind="security", origin="sweep", actions=["block_ip"], targets=[candidate.agent_id],
        params=_block_params(candidate, response), dedupe_key=key,
        reason={"ruleId": RULE_ID, "inputs": {"origins": origins, "indicator": ip, "twoSignal": response.two_signal,
                                              "incidentId": incident_id}},
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


async def _remember(db, tenant_id, candidate, decision, origins, now, outcome, **extra) -> None:
    key = {"tenantId": tenant_id, "agentId": candidate.agent_id, "kind": candidate.kind, "indicator": candidate.indicator}
    await signals.remember(db, key, {"actionId": decision.action_id, "at": now, "outcome": outcome,
                                     "origins": origins, **extra})


async def _dispatch(db, tenant_id, candidate, decision, origins, now, counts) -> None:
    """Send a row the gate recorded as dispatching, and remember every recorded outcome."""
    if not decision.recorded or not decision.action_id:
        return
    outcome = {"shadow": "shadow", "refused": "refused", "awaiting_approval": "card", "suggested": "suggested"}.get(decision.state)
    if outcome:
        counts["shadow" if outcome == "shadow" else "refused" if outcome == "refused" else "cards"] += 1
        return await _remember(db, tenant_id, candidate, decision, origins, now, outcome)
    if decision.state != "dispatching":
        return
    row = await ledger.get(db, tenant_id, decision.action_id)
    if row is None:
        return
    sent = await response_dispatch.send(db, row)
    if sent.get("status") != "queued":
        return await _remember(db, tenant_id, candidate, decision, origins, now, "failed")
    counts["blocked"] += 1
    after = await ledger.get(db, tenant_id, decision.action_id) or {}
    window = {f: after[f] for f in ("blockedFrom", "blockedUntil") if after.get(f) is not None}
    await _remember(db, tenant_id, candidate, decision, origins, now, "blocked", **window)


def _undone_at(row: Dict[str, Any]) -> Optional[datetime]:
    """When the person's undo took effect: the latest of the stamps the gate's own cooldown looks at."""
    stamps = [v for v in ((row.get("undo") or {}).get("undoneAt"), row.get("finishedAt"), row.get("createdAt"))
              if isinstance(v, datetime)]
    return max(stamps) if stamps else None


async def _act(db, tenant_id, candidate, origins, live, response, agent, now, counts, incident_id) -> None:
    key, suggest_key = _keys(tenant_id, candidate, "block_ip")
    row = await sweep_memory.latest_state(db, tenant_id, candidate.decision)
    if sweep_memory.skip_reason(candidate.decision, row, sorted(live), now) \
            or await agent_support.check(db, tenant_id, agent, "block_ip", now=now,
                                         params=_block_params(candidate, response)):
        counts["skipped"] += 1
        return
    req, hold = _act_request(tenant_id, candidate, origins, response, key, incident_id), None
    undone = await ledger.latest_undone(db, tenant_id, key)
    at = _undone_at(undone) if undone else None
    if at is not None and at > now - COOLDOWN:
        # Inside 24 hours of a person's undo: one refused row saying so, nothing sent (the gate records it).
        hold, shown = at + COOLDOWN, (undone.get("undo") or {}).get("undoneAt") or at
        inputs = {**req.reason["inputs"], "undoneAt": shown.isoformat()}
        req = replace(req, record_suppressed=True, reason={**req.reason, "inputs": inputs},
                      reason_text=rm.fill(rm.WHY_TEMPLATES["undone_earlier"], date=rm.short_date(shown)))
    elif await ledger.count_host_auto_since(db, tenant_id, candidate.agent_id, _HOST_COMMANDS,
                                            now - RATE_LIMIT_WINDOW) >= HOST_AUTO_LIMIT:
        req = replace(req, playbook_raise=True, reason_text=rm.WHY_TEMPLATES["host_cap"])
    decision = await gate.decide(db, req, now=now)
    if decision.recorded:
        await _supersede(db, tenant_id, suggest_key)
        if hold is not None:
            return await _remember_refusal(db, tenant_id, candidate, decision, origins, now, hold, counts)
    await _dispatch(db, tenant_id, candidate, decision, origins, now, counts)


async def _remember_refusal(db, tenant_id, candidate, decision, origins, now, hold, counts) -> None:
    counts["refused"] += 1
    await _remember(db, tenant_id, candidate, decision, origins, now, "refused", holdUntil=hold)


async def _record_incidents(db, tenant_id: str, new_evidence) -> None:
    """Each origin first seen in this pass is one piece of evidence on its host's incident, dated by when
    the evidence happened (RESP-09). A failed write is logged; the decisions below fail closed on it."""
    for item in sorted(new_evidence, key=lambda e: (e["evidenceAt"], e["agentId"], e["indicator"], e["origin"])):
        try:
            await incidents.attach(db, tenant_id, item["agentId"], item["evidenceAt"])
        except Exception as exc:
            logger.error("autonomous_ops: incident evidence for %s not recorded: %s", item.get("agentId"), exc)


async def _incident_of(db, tenant_id: str, candidate, live, now) -> Optional[str]:
    """The id of the incident a decision on this candidate belongs to, or None when it cannot be read."""
    stamps = [v["evidenceAt"] for v in live.values() if isinstance(v.get("evidenceAt"), datetime)]
    try:
        return (await incidents.current(db, tenant_id, candidate.agent_id, max(stamps, default=now)))["id"]
    except Exception as exc:
        logger.error("autonomous_ops: incident for %s unreadable, skipping the decision: %s", candidate.agent_id, exc)
        return None


async def run(db, tenant_id: str, tenant: TenantSettings, response, now: datetime) -> Dict[str, int]:
    """One tenant's pass. Returns counts {observed, blocked, suggested, shadow, skipped}."""
    counts = {"observed": 0, "blocked": 0, "suggested": 0, "shadow": 0, "skipped": 0, "refused": 0, "cards": 0}
    agents = await signals.agents_of(db, tenant_id)
    by_id = {a["id"]: a for a in agents}
    observed = await signals.observe(db, tenant_id, agents, now)
    await _record_incidents(db, tenant_id, observed.new_evidence)
    for candidate in observed:
        counts["observed"] += 1
        command = _COMMANDS.get(candidate.kind)
        if command is None:
            continue
        row = await sweep_memory.latest_state(db, tenant_id, candidate.decision)
        began, until = sweep_memory.block_window(candidate.decision, row)
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
            probe = _block_params(candidate, response) if command == "block_ip" else None
            if await agent_support.check(db, tenant_id, agent, command, now=now, params=probe):
                counts["skipped"] += 1
                continue
            await _suggest(db, tenant_id, candidate, command, _ordered(live)[:1], response, now, counts)
        else:
            incident_id = await _incident_of(db, tenant_id, candidate, live, now)
            if incident_id is None:
                counts["skipped"] += 1
                continue
            await _act(db, tenant_id, candidate, _agreeing(live), live, response, agent, now, counts, incident_id)
    return counts
