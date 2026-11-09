"""How an attempt that holds a checked answer ends: a post to the requester or a staff-only draft (DESK-01).

``pipeline.answer`` decides which (the fixed rules, the output checks and ``gate.decide`` have already
spoken); this module only writes. The ticket's status moves first, by compare-and-set, so a person who moved
the ticket meanwhile is never overridden and the requester never reads an answer on a ticket a person has taken.
Every row the desk writes gets its Activity words (``reasonText`` and ``activityResult``) here. Nothing in
this module reads a key of the model's reply other than the answer text it is handed (PROH-85-01).

Once the requester can read an answer (or a staff draft exists) no later write can undo it or hand the ticket
off (WR-102): every follow-up step is guarded and logged by ``_step``, and the two writes the rest of the desk
depends on (the desk phase and the row's move to ``executed``) are tried once more at the end.
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

from autonomous_ops import gate, ledger
from autonomous_ops import messages as ao_messages

from . import COMMAND_ANSWER, DISPATCHER_NAME, KIND, SYSTEM_AUTHOR, messages, notify, retrieval, ticket_writes

logger = logging.getLogger(__name__)

_FAILED = object()                       # what a guarded step returns when it raised


async def _step(label: str, ticket_id: str, call) -> Any:
    """Run one write that follows a visible answer or draft. A failure is logged with the ticket and the step and
    returns ``_FAILED``: the requester-visible change is already stored and must not be undone or contradicted."""
    try:
        return await call
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("service_desk: %s for ticket %s did not complete: %s", label, ticket_id, exc)
        return _FAILED


def build_request(ticket: Dict[str, Any], tenant: str, matches: List[retrieval.Match], model_reply: Any,
                  model_name: str, *, force_suggest: bool, can_see: bool) -> gate.ActionRequest:
    """The one request the desk puts to the gate for an answer (85-01 shape). The reason inputs carry the
    articles and the model's own timings (DESK-05); ``suggestionOnly`` marks the row as a ticket answer."""
    inputs = {
        "articles": [{"id": m.id, "title": m.title, "contentHash": m.content_hash, "score": round(m.score, 4)}
                     for m in matches],
        "cut": retrieval.CUT, "matchedTerms": matches[0].terms, "model": model_name,
        "promptTokens": model_reply.prompt_tokens, "evalTokens": model_reply.eval_tokens,
        "genMs": model_reply.gen_ms, "loadMs": model_reply.load_ms,
        "requesterCanSee": can_see, "suggestionOnly": True}
    return gate.ActionRequest(
        tenant_id=tenant, kind=KIND, origin="service_desk", actions=[COMMAND_ANSWER], targets=[],
        params={"ticketId": ticket["id"]}, dedupe_key=f"{tenant}|{DISPATCHER_NAME}|{ticket['id']}",
        reason={"ruleId": "service_desk:answer", "inputs": inputs}, dispatcher=DISPATCHER_NAME,
        force_suggest=force_suggest,
        desk={"ticketId": ticket["id"], "ticketNumber": ticket.get("ticket_number"), "title": ticket.get("title"),
              "phase": "drafted"})


def draft_reason(decision: Any, desk_settings: Any, can_see: bool) -> str:
    """Why an answer is a draft, one of ``DRAFT_REASONS``. The first that holds: the tenant is in shadow, the
    gate's own reason (level, hourly limit, unreadable settings), the requester has nowhere to read it, a
    desk breaker is stored, else the desk is set to Drafts only."""
    if decision.shadow:
        return "shadow"
    if decision.reason in ("level_suggest", "desk_rate_limit", "settings_unreadable"):
        return decision.reason
    if not desk_settings.readable:
        return "settings_unreadable"
    if not can_see:
        return "no_tray_window"
    if desk_settings.breaker:
        return "desk_breaker"
    return "mode_drafts"


def _why(ticket: Dict[str, Any], title: str, matched: int) -> str:
    return messages.activity_why(ticket.get("ticket_number") or "", title, matched)


def _citations(cited: List[retrieval.Match]) -> List[Dict[str, Any]]:
    return [{"articleId": m.id, "title": m.title, "contentHash": m.content_hash} for m in cited]


async def post(db, tenant: str, ticket: Dict[str, Any], *, action_id: str, text: str, cited: List[retrieval.Match],
               matched: int, title: str, now: datetime) -> bool:
    """Post the answer to the requester and hold the ticket for their reply. False, with nothing left behind,
    when the ticket was moved by a person (the status compare-and-set lost) or the comment could not be written:
    the caller then keeps the answer as a draft. After the comment is stored this never raises and returns True:
    the row ends ``executed`` with its Activity words and the requester gets one in-app notice, and a step that
    failed is logged; the desk phase and the executed move are tried once more at the end (WR-102)."""
    moved = await ticket_writes.move_status(db, tenant, ticket["id"], ("open",), "pending_customer",
                                            actor=SYSTEM_AUTHOR, now=now)
    if not moved:
        return False
    comment_id = "sd-" + action_id
    try:
        added = await ticket_writes.add_comment(
            db, tenant, ticket["id"], comment_id=comment_id, kind="ai_answer", visibility="requester", text=text,
            author=SYSTEM_AUTHOR, now=now,
            ai={"actionId": action_id, "citations": _citations(cited), "state": "posted", "postedAt": now.isoformat()})
    except Exception as exc:
        logger.error("service_desk: the answer for ticket %s was not saved: %s", ticket["id"], exc)
        added = False
    if not added:
        await ticket_writes.move_status(db, tenant, ticket["id"], ("pending_customer",), "open",
                                        actor=SYSTEM_AUTHOR, now=now)
        return False
    tid = ticket["id"]
    posted = {"phase": "posted", "actionId": action_id, "commentId": comment_id, "undoable": True, "postedAt": now,
              "draftWaiting": False}
    row_fields = {"desk.phase": "posted", "desk.postedAt": now, "desk.commentId": comment_id, "desk.undoable": True}
    desk_done: Any = _FAILED
    row_done: Any = _FAILED
    try:
        desk_done = await _step("the desk fields", tid, ticket_writes.set_desk(db, tenant, tid, posted, now=now))
        row_done = await _step("the executed move of the row", tid,
                               ledger.transition(db, tenant, action_id, ("dispatching",), "executed", **row_fields))
        await _step("the Activity words", tid, ledger.set_display(
            db, tenant, action_id, reasonText=_why(ticket, title, matched),
            activityResult=messages.ACTIVITY["posted_result"].format(
                n=len(cited), articles=messages.plural(len(cited), "article", "articles"))))
        await _step("the requester notice", tid, notify.requester_notice(db, ticket, event="answer_posted"))
    finally:
        if desk_done is _FAILED:
            await _step("the desk fields (second try)", tid, ticket_writes.set_desk(db, tenant, tid, posted, now=now))
        if row_done is _FAILED:
            await _step("the executed move of the row (second try)", tid,
                        ledger.transition(db, tenant, action_id, ("dispatching",), "executed", **row_fields))
    return True


async def keep_draft(db, tenant: str, ticket: Dict[str, Any], *, action_id: str, text: str,
                     cited: List[retrieval.Match], matched: int, title: str, reason: str, shadow: bool,
                     now: datetime) -> None:
    """Keep the answer as a staff-only draft with ``reason`` (one of ``DRAFT_REASONS``) on the ticket and on the
    row. A tenant in shadow gets the simulation sentence as the row's result (the Phase 81 wording). The draft
    comment is the one write that may raise (nothing is visible yet); after it every step is guarded and the
    desk write that shows the draft in the panel (``draftWaiting``) is tried once more (WR-102)."""
    comment_id = "sd-" + action_id
    await ticket_writes.add_comment(
        db, tenant, ticket["id"], comment_id=comment_id, kind="ai_draft", visibility="staff", text=text,
        author=SYSTEM_AUTHOR, now=now, ai={"actionId": action_id, "citations": _citations(cited), "state": "draft"})
    tid = ticket["id"]
    drafted = {"phase": "drafted", "actionId": action_id, "commentId": comment_id, "draftWaiting": True,
               "draftReason": reason}
    desk_done: Any = _FAILED
    try:
        desk_done = await _step("the desk fields", tid, ticket_writes.set_desk(db, tenant, tid, drafted, now=now))
        await _step("the row's desk fields", tid, ledger.set_desk_fields(
            db, tenant, action_id, {"phase": "drafted", "commentId": comment_id, "draftReason": reason},
            event="draft_kept"))
        result = (ao_messages.simulation_result(
            messages.ACTIVITY["simulation_result"].format(number=ticket.get("ticket_number") or ""))
            if shadow else messages.ACTIVITY["draft_result"])
        await _step("the Activity words", tid, ledger.set_display(
            db, tenant, action_id, reasonText=_why(ticket, title, matched) + " " + messages.DRAFT_REASON_TEXT[reason],
            activityResult=result))
    finally:
        if desk_done is _FAILED:
            await _step("the desk fields (second try)", tid, ticket_writes.set_desk(db, tenant, tid, drafted, now=now))


async def post_lost_to_draft(db, tenant: str, action_id: str) -> None:
    """The row of a post that could not be made becomes the suggestion a draft needs (open, no expiry). It never
    raises: a failed move is logged and tried once more, so the staff draft that follows is always written."""
    async def move():
        return await ledger.transition(db, tenant, action_id, ("dispatching",), "suggested",
                                       **{"desk.phase": "drafted", "reasonCode": "suggest_requested",
                                          "approval.requiredBy": "suggest_requested"})
    if await _step("the suggested move of the row", f"with action {action_id}", move()) is _FAILED:
        await _step("the suggested move of the row (second try)", f"with action {action_id}", move())
