"""What people do with a desk answer after it exists: send, edit or discard a draft (D-09, D-10).

Every change to a comment or a ticket here is a compare-and-set on the raw handle with an explicit tenantId, so a
person who already acted is never overridden and two people racing for one draft give exactly one winner. A
function returns ``{"status": "sent" | "discarded", ...}`` or ``{"status": "refused", "reason": code}`` where
``code`` is a key of ``messages.API_DETAIL``; the routes turn a refusal into the text of that key. Anyone who
works tickets may act on a draft (no approval tier, no MFA ask, D-10); a person-sent answer is a person's
decision and never counts toward the desk's automatic pool or its breaker (it is not ``autoDispatched``).
Nothing in this module closes a ticket.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from autonomous_ops import ledger
from autonomous_ops.rollout import windows
from autonomous_ops.scope import raw

from . import ANSWER_MAX_CHARS, notify, projection, ticket_writes, workdays, messages

logger = logging.getLogger(__name__)

_SEND_FROM = ("open", "in_progress", "on_hold")


def _aware(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def refused(reason: str, **detail: Any) -> Dict[str, Any]:
    return {"status": "refused", "reason": reason, **detail}


def _ledger_actor(actor: Dict[str, Any]) -> Dict[str, str]:
    """The shape the ledger records for a person: the same keys an approval's ``approver`` carries."""
    return {"username": str(actor.get("id") or ""), "display": str(actor.get("name") or actor.get("id") or ""),
            "tier": "tenant"}


def _history(actor: str, action: str, changes: Dict[str, Any], at: str) -> Dict[str, Any]:
    return {"id": str(uuid.uuid4()), "actor": actor, "action": action, "changes": changes, "created_at": at}


async def _read(db, tenant_id: str, ticket_id: str) -> Optional[Dict[str, Any]]:
    return await raw(db).tickets.find_one({"id": ticket_id, "tenantId": tenant_id}, {"_id": 0})


def _draft(ticket: Dict[str, Any], comment_id: str) -> Optional[Dict[str, Any]]:
    for comment in ticket.get("comments") or []:
        if (isinstance(comment, dict) and comment.get("id") == comment_id and comment.get("kind") == "ai_draft"
                and isinstance(comment.get("ai"), dict) and comment["ai"].get("state") == "draft"):
            return comment
    return None


async def _turn_draft(db, tenant_id: str, ticket_id: str, comment_id: str, sets: Dict[str, Any], *,
                      actor: Dict[str, Any], action: str, now: datetime) -> bool:
    """The one compare-and-set on a draft: it changes only while it is still a waiting draft. True for the
    caller that won."""
    at = now.isoformat()
    result = await raw(db).tickets.update_one(
        {"id": ticket_id, "tenantId": tenant_id,
         "comments": {"$elemMatch": {"id": comment_id, "kind": "ai_draft", "ai.state": "draft"}}},
        {"$set": {**{f"comments.$.{key}": value for key, value in sets.items()}, "updated_at": at},
         "$push": {"history": _history(str(actor.get("id") or ""), action, {"comment": comment_id}, at)}})
    return result.matched_count == 1


async def _guarded(step: str, ticket_id: str, call) -> Any:
    """Run one write after the decision is made. A failure is logged and the rest still runs: the person's
    choice is already stored, and the next read shows what really happened."""
    try:
        return await call
    except Exception as exc:
        logger.error("service_desk: %s for ticket %s did not complete: %s", step, ticket_id, exc)
        return None


async def send_draft(db, tenant_id: str, ticket_id: str, comment_id: str, *, actor: Dict[str, Any],
                     text: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Send the waiting draft ``comment_id`` to the requester as it stands, or with ``text`` as an edit (D-09).
    The answer keeps its AI-assisted mark and its citations; the ticket then waits on the customer."""
    now = _aware(now)
    ticket = await _read(db, tenant_id, ticket_id)
    if ticket is None:
        return refused("not_found")
    comment = _draft(ticket, comment_id)
    if comment is None:
        return refused("already_handled")
    code, _ = projection.blocked(ticket)
    if code:
        return refused(code, state=ticket.get("status"))
    answer, edited = comment.get("text") or "", False
    if text is not None:
        cleaned = text.strip()
        if not cleaned:
            return refused("draft_empty")
        if len(cleaned) > ANSWER_MAX_CHARS:
            return refused("draft_too_long")
        if cleaned == answer.strip():
            return refused("edit_unchanged")
        answer, edited = cleaned, True

    sent_by = {"id": actor.get("id"), "name": actor.get("name")}
    won = await _turn_draft(
        db, tenant_id, ticket_id, comment_id,
        {"kind": "ai_answer", "visibility": "requester", "text": answer, "ai.state": "sent", "ai.sentBy": sent_by,
         "ai.sentAt": now.isoformat(), "ai.edited": edited}, actor=actor, action="draft_sent", now=now)
    if not won:
        return refused("already_handled")

    await _guarded("the status change", ticket_id, ticket_writes.move_status(
        db, tenant_id, ticket_id, _SEND_FROM, "pending_customer", actor=str(actor.get("id") or ""), now=now))
    action_id = comment["ai"].get("actionId")
    desk = {"phase": "sent", "commentId": comment_id, "draftWaiting": False, "undoable": True, "postedAt": now,
            "sentBy": sent_by, "sentAt": now, "edited": edited}
    await _guarded("the desk fields", ticket_id, ticket_writes.set_desk(db, tenant_id, ticket_id, desk, now=now))
    zone = await workdays.tenant_zone(db, tenant_id)
    await _guarded("the Activity row", ticket_id, _row_sent(db, tenant_id, action_id, actor, desk, zone, now))
    await _guarded("the notice", ticket_id, notify.requester_notice(db, ticket, event="answer_sent"))
    return {"status": "sent", "commentId": comment_id, "edited": edited}


async def _row_sent(db, tenant_id: str, action_id: Optional[str], actor: Dict[str, Any], desk: Dict[str, Any],
                    zone: str, now: datetime) -> None:
    """The draft's row: a suggestion becomes executed with the sender as approver; a shadow or refused row only
    gets its desk fields and an audit event (it stays what the gate made it)."""
    if not action_id:
        return
    who = _ledger_actor(actor)
    fields = {"desk.phase": "sent", "desk.sentBy": desk["sentBy"], "desk.sentAt": now, "desk.edited": desk["edited"],
              "desk.undoable": True, "desk.postedAt": now, "approval.approver": who, "approval.decidedAt": now}
    moved = await ledger.transition(db, tenant_id, action_id, ("suggested",), "executed", actor=who, **fields)
    if moved is not None:
        await ledger.set_display(db, tenant_id, action_id, activityResult=messages.ACTIVITY["sent_result"].format(
            name=actor.get("name") or actor.get("id"), time=windows.clock_text(now, zone)))
        return
    await ledger.set_desk_fields(
        db, tenant_id, action_id, {"phase": "sent", "sentBy": desk["sentBy"], "sentAt": now, "edited": desk["edited"],
                                   "undoable": True, "postedAt": now}, event="sent", actor=who)


async def discard_draft(db, tenant_id: str, ticket_id: str, comment_id: str, *, actor: Dict[str, Any],
                        now: Optional[datetime] = None) -> Dict[str, Any]:
    """Discard the waiting draft. It stays staff-only, the service desk does not try again on this ticket (D-04)
    and nothing is sent to the requester. Allowed on a resolved or closed ticket."""
    now = _aware(now)
    ticket = await _read(db, tenant_id, ticket_id)
    if ticket is None:
        return refused("not_found")
    comment = _draft(ticket, comment_id)
    if comment is None:
        return refused("already_handled")
    by = {"id": actor.get("id"), "name": actor.get("name")}
    won = await _turn_draft(db, tenant_id, ticket_id, comment_id,
                            {"ai.state": "discarded", "ai.discardedBy": by, "ai.discardedAt": now.isoformat()},
                            actor=actor, action="draft_discarded", now=now)
    if not won:
        return refused("already_handled")
    await _guarded("the desk fields", ticket_id, ticket_writes.set_desk(
        db, tenant_id, ticket_id, {"phase": "discarded", "draftWaiting": False, "discardedBy": by, "discardedAt": now},
        now=now))
    await _guarded("the Activity row", ticket_id, _row_discarded(db, tenant_id, comment["ai"].get("actionId"), actor,
                                                                 by, now))
    return {"status": "discarded", "commentId": comment_id}


async def _row_discarded(db, tenant_id: str, action_id: Optional[str], actor: Dict[str, Any], by: Dict[str, Any],
                         now: datetime) -> None:
    if not action_id:
        return
    who = _ledger_actor(actor)
    moved = await ledger.transition(
        db, tenant_id, action_id, ("suggested",), "denied", actor=who,
        **{"desk.phase": "discarded", "desk.discardedBy": by, "desk.discardedAt": now,
           "approval.approver": who, "approval.decidedAt": now})
    if moved is None:
        await ledger.set_desk_fields(db, tenant_id, action_id, {"phase": "discarded", "discardedBy": by,
                                                                "discardedAt": now}, event="discarded", actor=who)
        return
    await ledger.set_display(db, tenant_id, action_id,
                             activityResult=messages.ACTIVITY["discarded_result"].format(name=by.get("name") or by.get("id")))
