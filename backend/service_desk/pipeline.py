"""One job from the ticket to a posted answer, a staff-only draft or a hand-off to a person (DESK-01 to DESK-05).

``prepare`` is the cheap, deterministic part and runs before any model call: the stop, the fixed text rules
(``rules.evaluate``), the English check and the tenant's own Help desk article. ``answer`` is the slow part:
probe the local model, ask it once with a timeout sized from this server's measurement, check the reply
against the articles it cites, then ask the Autonomous Ops gate (research Pattern 2), so a stop or a level
change during the slow call is honoured at the moment of posting.

Every attempt ends as exactly one of: a post, a draft, or a hand-off through ``handoff.handoff``. Whether a
ticket goes to a person is decided by the fixed rules, the gate and the output checks, never by anything the
model says about itself (PROH-85-03). The model's reply is read for its answer text and its cited numbers and
nothing else: it never selects an outcome, a target or a ticket change, and nothing here writes an agent
instruction or a response task (PROH-85-01). The AI path never resolves or closes a ticket (PROH-85-04).
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from autonomous_ops import gate
from autonomous_ops import settings as ao_settings
from autonomous_ops.scope import raw

from . import (DESCRIPTION_CAP, NUM_PREDICT, SYSTEM_AUTHOR, TITLE_CAP, handoff, outcomes, projection, retrieval, rules,
               runtime, settings)
from .checks import check, given_citations, parse_reply
from .model import ModelError, OllamaClient
from .sanitize import build_prompt, clean_text

logger = logging.getLogger(__name__)

STOP_REASONS = ("platform_stop", "tenant_stop")


@dataclass
class Prepared:
    job: Dict[str, Any]
    ticket: Dict[str, Any]
    question: str
    matches: List[retrieval.Match] = field(default_factory=list)


async def _handoff(db, ticket: Dict[str, Any], reason: str, *, now: Optional[datetime], question: Optional[str] = None,
                   notify_requester: bool = True) -> str:
    """Send the ticket to a person and return the reason as the job's outcome word."""
    await handoff.handoff(db, ticket, reason, now=now, notify_requester=notify_requester, question=question)
    return reason


async def _stopped(db, tenant: str) -> bool:
    """True when the platform or the tenant stop is on. Anything unreadable counts as on (fail closed)."""
    try:
        if ao_settings.stop_active((await ao_settings.load(db, tenant)).stop):
            return True
        return ao_settings.stop_active(await ao_settings.platform_stop(db))
    except Exception as exc:
        logger.warning("service_desk: the stop for %s could not be read (treated as on): %s", tenant, exc)
        return True


def _question(ticket: Dict[str, Any]) -> str:
    return clean_text(ticket.get("title"), TITLE_CAP) + "\n" + clean_text(ticket.get("description"), DESCRIPTION_CAP)


async def prepare(db, job: Dict[str, Any], *, now: Optional[datetime] = None) -> Tuple[Optional[Prepared], Optional[str]]:
    """(Prepared, None) when an article fits and the model may be asked, else (None, outcome): ticket_missing,
    desk_off (nothing is written), or the hand-off reason (the ticket has been sent to a person)."""
    tenant = job.get("tenantId")
    ticket = await raw(db).tickets.find_one({"id": job.get("ticketId"), "tenantId": tenant}, {"_id": 0})
    if not ticket:
        return None, "ticket_missing"
    desk_settings = await settings.load(db, tenant)
    if desk_settings.mode == "off":
        return None, "desk_off"
    if await _stopped(db, tenant):
        # A ticket picked up during a stop goes to a person quietly: no notice to the requester (decision 3).
        return None, await _handoff(db, ticket, "desk_stopped", now=now, notify_requester=False)
    question = _question(ticket)
    reason = rules.evaluate(ticket, question, desk_settings.words)
    if reason is None and not rules.is_english(question):
        reason = "not_english"
    matches: List[retrieval.Match] = []
    if reason is None:
        matches = retrieval.select(retrieval.score(question, await retrieval.candidates(db, tenant)))
        if not matches:
            reason = "no_article"
    if reason is not None:
        return None, await _handoff(db, ticket, reason, now=now, question=question)
    return Prepared(job=job, ticket=ticket, question=question, matches=matches), None


def _changed(ticket: Dict[str, Any]) -> bool:
    """A person moved the ticket out of open or replied to the requester since the desk read it."""
    if ticket.get("status") != "open":
        return True
    return any(isinstance(c, dict) and c.get("visibility") == "requester" and c.get("author") != SYSTEM_AUTHOR
               for c in (ticket.get("comments") or []))


async def answer(db, prepared: Prepared, client: OllamaClient, *, now: Optional[datetime] = None) -> str:
    """The outcome word: posted, drafted, ticket_changed, ticket_missing, desk_off or the hand-off reason."""
    now = now or datetime.now(timezone.utc)
    ticket, tenant = prepared.ticket, prepared.job["tenantId"]
    if not await client.available():
        return await _handoff(db, ticket, "service_desk_offline", now=now)
    system, prompt = build_prompt(ticket.get("title"), ticket.get("description"), prepared.matches)
    timeout = runtime.call_timeout(len(system) + len(prompt), NUM_PREDICT, await runtime.load_measurement(db),
                                   await runtime.recent_gen_ms(db))
    try:
        model_reply = await client.generate(system, prompt, timeout=timeout)
    except ModelError as exc:                     # busy, too slow or any other failure: a person takes it
        logger.warning("service_desk: the model gave no answer: %s", exc)
        return await _handoff(db, ticket, "service_desk_busy", now=now)
    parsed = parse_reply(model_reply.text)
    given = {n: m.content for n, m in enumerate(prepared.matches, start=1)}
    if parsed is None or check(parsed, given.keys(), given) is not None:
        return await _handoff(db, ticket, "output_check_failed", now=now)

    # Read the ticket again: the generation took a while and a person may have acted meanwhile.
    fresh = await raw(db).tickets.find_one({"id": ticket["id"], "tenantId": tenant}, {"_id": 0})
    if fresh is None:
        return "ticket_missing"
    desk_settings = await settings.load(db, tenant)
    if desk_settings.mode == "off":
        return "desk_off"
    changed = _changed(fresh)
    can_see = projection.can_see(ticket)
    request = outcomes.build_request(ticket, tenant, prepared.matches, model_reply, client.model,
                                     force_suggest=changed or desk_settings.mode != "post" or not can_see,
                                     can_see=can_see)
    decision = await gate.decide(db, request, now=now)

    cited = [prepared.matches[n - 1] for n in given_citations(parsed, given)]
    details = dict(action_id=decision.action_id, text=parsed.answer, cited=cited, matched=len(prepared.matches),
                   title=clean_text(ticket.get("title"), TITLE_CAP), now=now)
    if decision.outcome == "refuse" or not decision.action_id:
        if decision.reason in STOP_REASONS and decision.action_id:
            # Stop pressed during generation: nothing is posted, the text stays a draft for staff (decision 3).
            await outcomes.keep_draft(db, tenant, ticket, reason="stopped", shadow=False, **details)
            return "drafted"
        if decision.reason in STOP_REASONS:
            return await _handoff(db, ticket, "desk_stopped", now=now, notify_requester=False)
        return await _handoff(db, ticket, "service_desk_busy", now=now)

    shadow = bool(decision.shadow)
    if decision.outcome == "allow_auto" and decision.state == "dispatching" and not shadow:
        if await outcomes.post(db, tenant, ticket, **details):
            return "posted"
        await outcomes.post_lost_to_draft(db, tenant, decision.action_id)     # a person moved the ticket just now
        changed = True
    await outcomes.keep_draft(db, tenant, ticket, reason=outcomes.draft_reason(decision, desk_settings, can_see),
                              shadow=shadow, **details)
    return "ticket_changed" if changed else "drafted"
