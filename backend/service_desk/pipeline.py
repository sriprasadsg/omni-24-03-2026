"""One job from the ticket to a posted answer or a staff-only draft (DESK-01).

``prepare`` is the cheap, deterministic part: read the ticket, find the tenant's own Help desk
article. ``answer`` is the slow part: probe the local model, ask it once, check the reply, and only
then ask the Autonomous Ops gate (research Pattern 2), so a stop or a level change during the slow
call is honoured at the moment of posting. The model's reply is text only: it never selects an
outcome, a target or a ticket change, and nothing here writes an agent instruction or a response
task (PROH-85-01). The AI path never resolves or closes a ticket (PROH-85-04). 85-13 adds every
hand-off, the stop and moved-ticket edges.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from autonomous_ops import gate, ledger
from autonomous_ops.scope import raw

from . import (COMMAND_ANSWER, DESCRIPTION_CAP, DISPATCHER_NAME, KIND, SYSTEM_AUTHOR, TITLE_CAP, projection,
               retrieval, settings, ticket_writes)
from .checks import check, parse_reply
from .model import ModelError, OllamaClient
from .sanitize import build_prompt, clean_text

logger = logging.getLogger(__name__)


@dataclass
class Prepared:
    job: Dict[str, Any]
    ticket: Dict[str, Any]
    question: str
    matches: List[retrieval.Match] = field(default_factory=list)


async def prepare(db, job: Dict[str, Any], *, now: Optional[datetime] = None) -> Tuple[Optional[Prepared], Optional[str]]:
    """(Prepared, None) when an article fits, else (None, reason): ticket_missing or no_article."""
    ticket = await raw(db).tickets.find_one({"id": job.get("ticketId"), "tenantId": job.get("tenantId")}, {"_id": 0})
    if not ticket:
        return None, "ticket_missing"
    question = (clean_text(ticket.get("title"), TITLE_CAP) + "\n"
                + clean_text(ticket.get("description"), DESCRIPTION_CAP))
    matches = retrieval.select(retrieval.score(question, await retrieval.candidates(db, job["tenantId"])))
    if not matches:
        return None, "no_article"
    return Prepared(job=job, ticket=ticket, question=question, matches=matches), None


def _request(prepared: Prepared, *, mode: str, can_see: bool, model_reply, model_name: str) -> gate.ActionRequest:
    ticket, tenant = prepared.ticket, prepared.job["tenantId"]
    inputs = {
        "articles": [{"id": m.id, "title": m.title, "contentHash": m.content_hash, "score": round(m.score, 4)}
                     for m in prepared.matches],
        "cut": retrieval.CUT, "matchedTerms": prepared.matches[0].terms, "model": model_name,
        "promptTokens": model_reply.prompt_tokens, "evalTokens": model_reply.eval_tokens,
        "genMs": model_reply.gen_ms, "loadMs": model_reply.load_ms,
        "requesterCanSee": can_see, "suggestionOnly": True}
    return gate.ActionRequest(
        tenant_id=tenant, kind=KIND, origin="service_desk", actions=[COMMAND_ANSWER], targets=[],
        params={"ticketId": ticket["id"]}, dedupe_key=f"{tenant}|{DISPATCHER_NAME}|{ticket['id']}",
        reason={"ruleId": "service_desk:answer", "inputs": inputs}, dispatcher=DISPATCHER_NAME,
        force_suggest=(mode != "post" or not can_see),
        desk={"ticketId": ticket["id"], "ticketNumber": ticket.get("ticket_number"), "title": ticket.get("title"),
              "phase": "drafted"})


async def answer(db, prepared: Prepared, client: OllamaClient, *, now: Optional[datetime] = None) -> str:
    """The outcome word: posted, drafted, offline, model_error, output_check_failed or refused:<code>."""
    now = now or datetime.now(timezone.utc)
    if not await client.available():
        return "offline"
    system, prompt = build_prompt(prepared.ticket.get("title"), prepared.ticket.get("description"), prepared.matches)
    try:
        model_reply = await client.generate(system, prompt)
    except ModelError as exc:
        logger.warning("service_desk: the model gave no answer: %s", exc)
        return "model_error"
    parsed = parse_reply(model_reply.text)
    if parsed is None or check(parsed, range(1, len(prepared.matches) + 1)) is not None:
        return "output_check_failed"

    tenant, ticket = prepared.job["tenantId"], prepared.ticket
    cited = [prepared.matches[n - 1] for n in dict.fromkeys(parsed.cited)]
    desk_settings = await settings.load(db, tenant)
    can_see = projection.can_see(ticket)
    request = _request(prepared, mode=desk_settings.mode, can_see=can_see, model_reply=model_reply,
                       model_name=client.model)
    decision = await gate.decide(db, request, now=now)
    if decision.outcome == "refuse" or not decision.action_id:
        return "refused:" + decision.reason

    action_id = decision.action_id
    citations = [{"articleId": m.id, "title": m.title, "contentHash": m.content_hash} for m in cited]
    comment_id = "sd-" + action_id
    if decision.outcome == "allow_auto" and decision.state == "dispatching" and not decision.shadow:
        await ticket_writes.add_comment(
            db, tenant, ticket["id"], comment_id=comment_id, kind="ai_answer", visibility="requester",
            text=parsed.answer, author=SYSTEM_AUTHOR, now=now,
            ai={"actionId": action_id, "citations": citations, "state": "posted", "postedAt": now.isoformat()})
        await ticket_writes.move_status(db, tenant, ticket["id"], ("open",), "pending_customer",
                                        actor=SYSTEM_AUTHOR, now=now)
        await ticket_writes.set_desk(db, tenant, ticket["id"],
                                     {"phase": "posted", "actionId": action_id, "commentId": comment_id,
                                      "undoable": True, "postedAt": now, "draftWaiting": False}, now=now)
        await ledger.transition(db, tenant, action_id, ("dispatching",), "executed",
                                **{"desk.phase": "posted", "desk.postedAt": now, "desk.commentId": comment_id,
                                   "desk.undoable": True})
        return "posted"

    await ticket_writes.add_comment(
        db, tenant, ticket["id"], comment_id=comment_id, kind="ai_draft", visibility="staff",
        text=parsed.answer, author=SYSTEM_AUTHOR, now=now,
        ai={"actionId": action_id, "citations": citations, "state": "draft"})
    await ticket_writes.set_desk(db, tenant, ticket["id"],
                                 {"phase": "drafted", "actionId": action_id, "commentId": comment_id,
                                  "draftWaiting": True}, now=now)
    return "drafted"
