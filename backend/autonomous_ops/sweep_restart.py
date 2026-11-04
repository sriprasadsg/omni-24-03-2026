"""The restart stage of the sweep (Phase 83, RESP-04): a listed service that fails is brought back, within a budget.

For one tenant per tick: an agent reports the services it watches that have been failing (``meta.service_failures``,
83-14) and the tenant lists the services it wants watched (``response.watchedServices``, 83-07).

* A failure counts only when its name is on the tenant's list, compared case-insensitively (D-10). An empty list
  means nothing restarts. The two-source rule does not apply: the agent saw the failure itself (D-02).
* The budget is 3 restarts per service per computer in a rolling hour, counted from the ledger (D-11), so a restart
  of the backend, a new failure id or a service that keeps flapping never resets it (PROH-83-16). A row exactly one
  hour old no longer counts. Refused rows and simulations count nothing.
* Tries are spaced by a wait counted from the newest row: 1 minute after the first, 2 after the second, 4 after the
  third (A-83-LADDER). The fourth try is not made: after the 4-minute wait ONE approval card is recorded
  (``playbook_raise``, so the gate answers ``playbook_raised``) and the stage then leaves the service alone while
  that card is open, and for 24 hours after a person denied it or let it lapse (``signals.remember``).
* One open row per service and computer: any open row of any key (an automatic try or a card) keeps the stage
  quiet, so a card answered late can never start a second restart while one is open.
* A card whose service the computer no longer reports failing is ended (``expired``, ``service_recovered``) and
  holds nothing: a later failure starts fresh (WR-03; approving refuses it the same way).
* A restart row offers no Undo (D-12; the registry has none) and does not count toward the per-computer cap on
  blocks and quarantines (``sweep_security._HOST_COMMANDS``). It does count toward the tenant's 20 automatic actions
  an hour, because the gate counts every automatic row.
* Every decision carries ``reason.inputs.incidentId``; the failure is evidence on the computer's incident, dated by
  the failure's own ``since`` time, once per failure id.

A computer that cannot take the restart right now (capability not ticked, offline, no ``restart_service`` token) gets
no row at all and nothing the breaker sees. Only structured fields decide anything: this module calls no model and
reads no free text (PROH-83-01).

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument

from . import (OPEN_STATES, agent_support, gate, incidents, ledger, response_dispatch, response_messages as rm,
               response_settings, signals, sweep_memory)
from .scope import raw
from .settings import TenantSettings

logger = logging.getLogger(__name__)

RULE_ID = "sweep:restart_service"
COMMAND = "restart_service"
RESTART_BUDGET = 3
BUDGET_WINDOW = timedelta(hours=1)
WAITS = (60, 120, 240)                          # seconds after the 1st, 2nd and 3rd row; the last delays the card
MAX_FAILURES = 50                               # reports read per computer (the tenant list is capped at 50 too)
_NOT_COUNTED = ("refused", "shadow")
_HOLDS = ("denied", "expired", "refused", "shadow")      # outcomes of the last card that keep the service quiet
_KIND = "service"
_SERVICE_RE = re.compile(response_settings.SERVICE_NAME_RE)
_ID_CAP = 200


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


def _since(value: Any, now: datetime) -> datetime:
    """When the failure began, from the agent's whole epoch seconds. Anything unusable, and anything in the
    future, reads as now."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return now
    try:
        return min(datetime.fromtimestamp(value, tz=timezone.utc), now)
    except (OverflowError, OSError, ValueError):
        return now


def _watched(response) -> Dict[str, str]:
    """The tenant's list by lower-cased name -> the name as listed. A stored name the agent would refuse is left out."""
    names: Dict[str, str] = {}
    for name in response.watched_services:
        if isinstance(name, str) and _SERVICE_RE.fullmatch(name):
            names.setdefault(name.casefold(), name)
    return names


def _failures(agent: Dict[str, Any], watched: Dict[str, str], now: datetime) -> List[Dict[str, Any]]:
    """The agent's reported failures that are on the list, one per service, in service order. The name sent to the
    agent is always the one the tenant listed, never the reported text."""
    meta = agent.get("meta")
    items = meta.get("service_failures") if isinstance(meta, dict) else None
    found: Dict[str, Dict[str, Any]] = {}
    for item in (items if isinstance(items, list) else [])[:MAX_FAILURES]:
        name = item.get("name") if isinstance(item, dict) else None
        listed = watched.get(name.strip().casefold()) if isinstance(name, str) else None
        if listed is None or listed.casefold() in found:
            continue
        failure_id = item.get("failure_id")
        if not isinstance(failure_id, str) or not failure_id or len(failure_id) > _ID_CAP:
            failure_id = f"{listed.casefold()}-{item.get('since')}"
        found[listed.casefold()] = {"service": listed, "failureId": failure_id, "at": _since(item.get("since"), now)}
    return [found[key] for key in sorted(found)]


# ---------------------------------------------------------------- what the ledger and the memory say

def _service_filter(tenant_id: str, agent_id: str, service: str) -> Dict[str, Any]:
    """Every restart row for this service on this computer, whichever spelling it was sent in."""
    return {"tenantId": tenant_id, "command": COMMAND, "targets": agent_id,
            "params.service_name": {"$regex": f"^{re.escape(service)}$", "$options": "i"}}


async def _window_rows(db, tenant_id: str, agent_id: str, service: str, now: datetime) -> List[Dict[str, Any]]:
    """The rows that count toward the budget, newest first: created strictly after one hour ago, not refused and
    not a simulation."""
    found = raw(db).autonomy_actions.find(
        {**_service_filter(tenant_id, agent_id, service), "state": {"$nin": list(_NOT_COUNTED)},
         "createdAt": {"$gt": now - BUDGET_WINDOW}},
        {"_id": 0, "id": 1, "createdAt": 1}).sort([("createdAt", -1), ("id", -1)]).limit(100)
    return [{**r, "createdAt": _aware(r.get("createdAt"))} async for r in found]


async def _has_open_row(db, tenant_id: str, agent_id: str, service: str) -> bool:
    found = await raw(db).autonomy_actions.find_one(
        {**_service_filter(tenant_id, agent_id, service), "state": {"$in": list(OPEN_STATES)}}, {"_id": 1})
    return found is not None


def _memory_key(tenant_id: str, agent_id: str, service: str) -> Dict[str, str]:
    return {"tenantId": tenant_id, "agentId": agent_id, "kind": _KIND, "indicator": service.casefold()}


async def _held(db, tenant_id: str, agent_id: str, service: str, now: datetime) -> bool:
    """The last card (or refusal) recorded for this service still holds it quiet: a card a person denied or let
    lapse waits 24 hours."""
    doc = await raw(db).autonomy_signals.find_one(_memory_key(tenant_id, agent_id, service), {"_id": 0, "decision": 1})
    decision = (doc or {}).get("decision")
    if not isinstance(decision, dict) or not decision:
        return False
    decision = {k: _aware(v) for k, v in decision.items()}
    row = await sweep_memory.latest_state(db, tenant_id, decision)
    if (row or {}).get("reasonCode") == "service_recovered":
        return False                                   # the service came back: a new failure is a new start
    return sweep_memory.skip_reason(decision, row, [], now) in _HOLDS


async def _first_sighting(db, tenant_id: str, agent_id: str, failure: Dict[str, Any], now: datetime) -> bool:
    """True once per failure id: the claim is one atomic write on the service's signal document, which is also
    where the sweep keeps what it decided."""
    prior = await raw(db).autonomy_signals.find_one_and_update(
        _memory_key(tenant_id, agent_id, failure["service"]),
        {"$setOnInsert": {"origins": {}}, "$set": {"failureId": failure["failureId"]}, "$max": {"lastSeenAt": now}},
        upsert=True, return_document=ReturnDocument.BEFORE)
    return (prior or {}).get("failureId") != failure["failureId"]


async def _incident_of(db, tenant_id: str, agent_id: str, failure: Dict[str, Any], now: datetime) -> Optional[str]:
    """The incident this failure belongs to, with the failure put on it the first time it is seen. None when it
    cannot be read: the decision is then skipped (fail closed)."""
    try:
        if await _first_sighting(db, tenant_id, agent_id, failure, now):
            return (await incidents.attach(db, tenant_id, agent_id, failure["at"]))["id"]
        return (await incidents.current(db, tenant_id, agent_id, failure["at"]))["id"]
    except Exception as exc:
        logger.error("autonomous_ops: incident for %s unreadable, skipping the restart: %s", agent_id, exc)
        return None


# ---------------------------------------------------------------- the decision

def _request(tenant_id: str, agent_id: str, failure: Dict[str, Any], attempt: int, incident_id: str,
             over_budget: bool) -> gate.ActionRequest:
    service = failure["service"]
    inputs: Dict[str, Any] = {"service": service, "failureId": failure["failureId"], "incidentId": incident_id}
    key = f"{tenant_id}|sweep|{COMMAND}|{agent_id}|{service.casefold()}"
    if over_budget:
        # A card is not "restart k of 3": it is the fourth try, which needs a person.
        inputs["overBudget"] = True
        key += "|card"
    else:
        inputs["attempt"] = attempt
    text = rm.fill(rm.WHY_TEMPLATES["restart_over_budget" if over_budget else "restart_watched"], service=service)
    return gate.ActionRequest(
        tenant_id=tenant_id, kind="security", origin="sweep", actions=[COMMAND], targets=[agent_id],
        params={"service_name": service}, dedupe_key=key, playbook_raise=over_budget,
        reason={"ruleId": RULE_ID, "inputs": inputs}, reason_text=text, dispatcher=response_dispatch.DISPATCHER_NAME)


async def _settle(db, tenant_id: str, agent_id: str, failure: Dict[str, Any], decision, now: datetime,
                  counts: Dict[str, int]) -> None:
    """Send a row the gate recorded as dispatching; remember every other recorded outcome so a card a person
    denied (or a refusal) is not asked again at once."""
    if not decision.recorded or not decision.action_id:
        counts["skipped"] += 1
        return
    if decision.state == "dispatching":
        row = await ledger.get(db, tenant_id, decision.action_id)
        if row is not None:
            sent = await response_dispatch.send(db, row)
            counts["restarted" if sent.get("status") == "queued" else "failed"] += 1
        return
    outcome = {"shadow": "shadow", "refused": "refused", "awaiting_approval": "card", "suggested": "suggested"}.get(
        decision.state)
    if outcome is None:
        return
    counts["cards" if outcome in ("card", "suggested") else outcome] += 1
    await signals.remember(db, _memory_key(tenant_id, agent_id, failure["service"]),
                           {"actionId": decision.action_id, "at": now, "outcome": outcome, "origins": []})


async def _one(db, tenant_id: str, agent: Dict[str, Any], failure: Dict[str, Any], now: datetime,
               counts: Dict[str, int]) -> None:
    agent_id, service = agent["id"], failure["service"]
    if await agent_support.check(db, tenant_id, agent, COMMAND, now=now) or await _has_open_row(db, tenant_id, agent_id, service):
        counts["skipped"] += 1
        return
    rows = await _window_rows(db, tenant_id, agent_id, service, now)
    used = len(rows)
    if used and now - rows[0]["createdAt"] < timedelta(seconds=WAITS[min(used, RESTART_BUDGET) - 1]):
        counts["waiting"] += 1
        return
    if await _held(db, tenant_id, agent_id, service, now):
        counts["skipped"] += 1
        return
    incident_id = await _incident_of(db, tenant_id, agent_id, failure, now)
    if incident_id is None:
        counts["skipped"] += 1
        return
    request = _request(tenant_id, agent_id, failure, used + 1, incident_id, used >= RESTART_BUDGET)
    await _settle(db, tenant_id, agent_id, failure, await gate.decide(db, request, now=now), now, counts)


async def _failing_agents(db, tenant_id: str) -> List[Dict[str, Any]]:
    found = raw(db).agents.find(
        {"tenantId": tenant_id, "meta.service_failures.0": {"$exists": True}},
        {"_id": 0, "id": 1, "status": 1, "lastSeen": 1, "platform": 1, "meta.response_actions": 1,
         "meta.service_failures": 1}).sort("id", 1).limit(signals.AGENT_LIMIT)
    return [a async for a in found if a.get("id")]


async def _close_recovered(db, tenant_id: str, counts: Dict[str, int]) -> None:
    """End every open over-budget card whose service its computer no longer reports failing (WR-03)."""
    cards = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "command": COMMAND, "state": "awaiting_approval", "reason.inputs.overBudget": True},
        {"_id": 0, "id": 1, "targets": 1, "params": 1}).limit(_ID_CAP)
    async for card in cards:
        failing = await agent_support.reports_failing(db, tenant_id, (card.get("targets") or [None])[0],
                                                      (card.get("params") or {}).get("service_name"))
        if failing is not False:
            continue                                   # still failing, or nothing to read: approval re-checks it
        done = await ledger.transition(db, tenant_id, card["id"], ("awaiting_approval",), "expired",
                                       reasonCode="service_recovered", reasonText=rm.REASON_TEXT["service_recovered"])
        counts["recovered"] += 1 if done else 0


async def run(db, tenant_id: str, tenant: TenantSettings, response, now: datetime) -> Dict[str, int]:
    """One tenant's pass. Returns counts {restarted, cards, recovered, shadow, refused, failed, waiting, skipped}.
    A computer that cannot be read is logged and does not stop the others."""
    counts = {"restarted": 0, "cards": 0, "recovered": 0, "shadow": 0, "refused": 0, "failed": 0, "waiting": 0,
              "skipped": 0}
    await _close_recovered(db, tenant_id, counts)
    watched = _watched(response)
    if not watched:
        return counts                                  # D-10: an empty list means nothing restarts
    for agent in await _failing_agents(db, tenant_id):
        for failure in _failures(agent, watched, now):
            try:
                await _one(db, tenant_id, agent, failure, now, counts)
            except Exception as exc:                   # one service never stops the others
                logger.error("autonomous_ops: restart of %s on %s not decided: %s", failure["service"], agent["id"], exc)
    return counts
