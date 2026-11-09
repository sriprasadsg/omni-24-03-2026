"""What people do with a desk answer after it exists: send, edit or discard a draft (D-09, D-10), and what the
requester answers: This fixed it or I still need help (D-07, D-31).

Every change to a comment or a ticket here is a compare-and-set on the raw handle with an explicit tenantId, so a
person who already acted is never overridden and two people racing for one draft give exactly one winner. A
function returns ``{"status": "sent" | "discarded", ...}`` or ``{"status": "refused", "reason": code}`` where
``code`` is a key of ``messages.API_DETAIL``; the routes turn a refusal into the text of that key. Anyone who
works tickets may act on a draft (no approval tier, no MFA ask, D-10); a person-sent answer is a person's
decision and never counts toward the desk's automatic pool or its breaker (it is not ``autoDispatched``).
The only status this module sets besides the hold on the customer is ``resolved``, and only on the requester's
own confirmation (D-07): the desk never resolves a ticket by itself and nothing here closes one.
A person-sent answer follows the same order as the desk's own post: the status moves to pending_customer first,
the draft turns into the visible answer only after that, and the status is put back when the turn is lost, so the
requester never reads an answer on a ticket that did not move (WR-103).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from autonomous_ops import ledger
from autonomous_ops.rollout import windows
from autonomous_ops.scope import raw

from . import ANSWER_MAX_CHARS, handoff, messages, notify, projection, ticket_writes, workdays

logger = logging.getLogger(__name__)

_SEND_FROM = ("open", "in_progress", "on_hold")
HELP_MAX_CHARS = 1000                    # the optional note with I still need help


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
    The answer keeps its AI-assisted mark and its citations; the ticket then waits on the customer. The status
    moves first by compare-and-set (a ticket a person already set to pending_customer needs no move), the draft
    turns only when that worked, and a lost turn puts the status back to what it was (open, in progress or on
    hold, never a closed status)."""
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

    prior = ticket.get("status") or ""
    moved = False
    if prior != "pending_customer":
        moved = await ticket_writes.move_status(db, tenant_id, ticket_id, _SEND_FROM, "pending_customer",
                                                actor=str(actor.get("id") or ""), now=now)
        if not moved:
            return await _refusal_after_lost_move(db, tenant_id, ticket_id, comment_id)
    sent_by = {"id": actor.get("id"), "name": actor.get("name")}
    won = await _turn_draft(
        db, tenant_id, ticket_id, comment_id,
        {"kind": "ai_answer", "visibility": "requester", "text": answer, "ai.state": "sent", "ai.sentBy": sent_by,
         "ai.sentAt": now.isoformat(), "ai.edited": edited}, actor=actor, action="draft_sent", now=now)
    if not won:
        if moved:
            await _put_status_back(db, tenant_id, ticket_id, comment_id, prior, actor, now)
        return refused("already_handled")

    action_id = comment["ai"].get("actionId")
    desk = {"phase": "sent", "commentId": comment_id, "draftWaiting": False, "undoable": True, "postedAt": now,
            "sentBy": sent_by, "sentAt": now, "edited": edited}
    await _guarded("the desk fields", ticket_id, ticket_writes.set_desk(db, tenant_id, ticket_id, desk, now=now))
    zone = await workdays.tenant_zone(db, tenant_id)
    await _guarded("the Activity row", ticket_id, _row_sent(db, tenant_id, action_id, actor, desk, zone, now))
    await _guarded("the notice", ticket_id, notify.requester_notice(db, ticket, event="answer_sent"))
    return {"status": "sent", "commentId": comment_id, "edited": edited}


async def _refusal_after_lost_move(db, tenant_id: str, ticket_id: str, comment_id: str) -> Dict[str, Any]:
    """The status move lost: the ticket changed after the first read. Refuse with the code the fresh ticket gives
    (closed, a person replied, no requester), else ``already_handled``; the comment stays a staff-only draft."""
    fresh = await _read(db, tenant_id, ticket_id)
    if fresh is None:
        return refused("not_found")
    if _draft(fresh, comment_id) is None:
        return refused("already_handled")
    code, _ = projection.blocked(fresh)
    return refused(code, state=fresh.get("status")) if code else refused("already_handled")


async def _put_status_back(db, tenant_id: str, ticket_id: str, comment_id: str, prior: str,
                           actor: Dict[str, Any], now: datetime) -> None:
    """The turn was lost after this call moved the status. Put it back to the status it moved from (read from the
    ticket's own history: a person may have changed it between the first read and the move; ``prior`` when the
    history shows nothing), unless the winner already sent the answer (it needs the status this call set) or the
    ticket moved on again (the compare-and-set sees that)."""
    fresh = await _read(db, tenant_id, ticket_id)
    sent = next((c for c in (fresh or {}).get("comments") or []
                 if isinstance(c, dict) and c.get("id") == comment_id and c.get("kind") == "ai_answer"), None)
    if fresh is None or sent is not None:
        return
    origin = prior
    for entry in reversed(fresh.get("history") or []):
        change = ((entry.get("changes") or {}).get("status") or {}) if isinstance(entry, dict) else {}
        if entry.get("action") == "updated" and change.get("to") == "pending_customer":
            origin = change.get("from") if change.get("from") in _SEND_FROM else prior
            break
    await _guarded("the status put-back", ticket_id, ticket_writes.move_status(
        db, tenant_id, ticket_id, ("pending_customer",), origin, actor=str(actor.get("id") or ""), now=now))


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


# ---------------------------------------------------------------- the requester answers (D-07, D-31)

async def confirm(db, tenant_id: str, ticket_id: str, *, requester: Dict[str, Any],
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """This fixed it: the requester resolves the ticket. The only way the desk's answer ends a ticket; the
    status moves by compare-and-set from pending_customer, so a person who acted first is not overridden."""
    now = _aware(now)
    ticket = await _read(db, tenant_id, ticket_id)
    if ticket is None:
        return refused("not_found")
    if not projection.confirmable(ticket):
        return refused("not_confirmable")
    moved = await ticket_writes.move_status(db, tenant_id, ticket_id, ("pending_customer",), "resolved",
                                            actor=str(requester.get("id") or ""), now=now,
                                            extra={"resolved_at": now.isoformat()})
    if not moved:
        return refused("not_confirmable")
    await _guarded("the desk fields", ticket_id, ticket_writes.set_desk(
        db, tenant_id, ticket_id, {"phase": "confirmed", "confirmedAt": now, "undoable": False}, now=now))
    zone = await workdays.tenant_zone(db, tenant_id)
    await _guarded("the Activity row", ticket_id, _row_answered(
        db, tenant_id, (ticket.get("desk") or {}).get("actionId"), requester, "confirmed",
        {"phase": "confirmed", "confirmedAt": now, "undoable": False},
        messages.ACTIVITY["confirmed_result"].format(date=windows.day_text(now, zone))))
    return {"status": "confirmed"}


async def _row_answered(db, tenant_id: str, action_id: Optional[str], who: Dict[str, Any], event: str,
                        fields: Dict[str, Any], result: Optional[str]) -> None:
    """The answer's own row records what the requester decided and no longer offers Undo."""
    if not action_id:
        return
    updated = await ledger.set_desk_fields(db, tenant_id, action_id, fields, event=event, actor=_ledger_actor(who))
    if updated is not None and result:
        await ledger.set_display(db, tenant_id, action_id, activityResult=result)


async def still_need_help(db, tenant_id: str, ticket_id: str, *, requester: Dict[str, Any], text: Optional[str] = None,
                          now: Optional[datetime] = None) -> Dict[str, Any]:
    """I still need help: the ticket goes to a person. The optional note (up to 1000 characters) is stored as the
    requester's own reply. There is no second attempt (D-31) and no notice to the requester, who just asked."""
    now = _aware(now)
    ticket = await _read(db, tenant_id, ticket_id)
    if ticket is None:
        return refused("not_found")
    if not projection.confirmable(ticket):
        return refused("not_confirmable")
    note = text.strip() if isinstance(text, str) else ""
    if len(note) > HELP_MAX_CHARS:
        return refused("help_too_long")
    who = str(requester.get("id") or "")
    if not await ticket_writes.move_status(db, tenant_id, ticket_id, ("pending_customer",), "open", actor=who, now=now):
        return refused("not_confirmable")
    if note:
        await _guarded("the requester's note", ticket_id, ticket_writes.add_comment(
            db, tenant_id, ticket_id, comment_id="sd-help-" + uuid.uuid4().hex, kind="requester_reply",
            visibility="requester", text=note, author=who, now=now))
    fresh = await _read(db, tenant_id, ticket_id) or ticket
    await _guarded("the hand-off", ticket_id, handoff.handoff(db, fresh, "did_not_help", now=now,
                                                              notify_requester=False, actor=requester))
    fields = {"phase": "helped", "helpedAt": now, "undoable": False}
    await _guarded("the desk fields", ticket_id, ticket_writes.set_desk(db, tenant_id, ticket_id, fields, now=now))
    await _guarded("the Activity row", ticket_id, _row_answered(
        db, tenant_id, (ticket.get("desk") or {}).get("actionId"), requester, "helped", fields, None))
    return {"status": "helped"}


async def on_comment_added(db, ticket: Dict[str, Any], *, author: str, visibility: str,
                           now: Optional[datetime] = None) -> None:
    """Called after every comment on a ticket. The reporter writing to a ticket whose answer is with them is the
    same as I still need help (without a second comment); a person replying to the requester ends Undo and
    blocks any waiting draft."""
    desk = ticket.get("desk")
    tenant_id, ticket_id = ticket.get("tenantId"), ticket.get("id")
    if not isinstance(desk, dict) or not tenant_id or not ticket_id:
        return
    now = _aware(now)
    if projection.same_person(ticket.get("reporter"), author):
        if projection.confirmable(ticket):
            await still_need_help(db, tenant_id, ticket_id, requester={"id": author, "name": author}, now=now)
        return
    if visibility != "requester" or desk.get("personReplied") is True:
        return
    await ticket_writes.set_desk(db, tenant_id, ticket_id, {"personReplied": True, "undoable": False}, now=now)
    result = messages.ACTIVITY["person_replied_result"] if desk.get("phase") in projection.ANSWERED_PHASES else None
    await _row_answered(db, tenant_id, desk.get("actionId"), {"id": author, "name": author}, "person_replied",
                        {"personReplied": True, "undoable": False}, result)
