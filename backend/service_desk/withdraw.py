"""A person takes back a posted service desk answer (D-25), through the Autonomous Ops Undo button.

``undo_answer`` is registered as the ``service_desk`` undo handler when this module is imported, and the required
service desk settings router imports it, so a running app always has it. Withdrawing

* hides the answer from the requester (the comment turns ``withdrawn``; staff keep the original) and gives the
  requester a plain notice instead: ``This answer was withdrawn; a person will follow up.``;
* moves a ticket that waits on the customer back to open and sends it to a person (``answer_withdrawn``);
* moves the row ``executed`` to ``undone`` naming the person, which the ledger mirrors to the audit chain.

It works while a stop is on (withdrawing is the safe direction) and never touches an agent or the Phase 81
breaker. The breaker that watches withdrawals belongs to the desk alone (``evaluate_breaker``). Every write is
on the raw handle with an explicit tenantId; the ticket write that hides the answer is one compare-and-set, so an
answer the requester confirmed or a person already answered in the meantime is not withdrawn.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from autonomous_ops import PLATFORM_TENANT_ID, approvals, ledger
from autonomous_ops.rollout import windows
from autonomous_ops.scope import raw

from . import (COMMAND_WITHDRAW, DESK_BREAKER_THRESHOLD, DESK_BREAKER_WINDOW, DISPATCHER_NAME, SYSTEM_AUTHOR, handoff,
               messages, notify, ticket_writes, workdays)

logger = logging.getLogger(__name__)

_UNDOABLE_STATES = ("executed", "verified")
_POSTED_PHASES = ("posted", "sent")            # the answer is on the ticket; the same set the Activity row uses
_EVENT = "service_desk_breaker_tripped"             # the control row and the notice carry this event name
_DESK_ACTOR = {"username": "autonomous_ops", "display": "Service desk", "tier": "system"}
_VISIBLE = ["posted", "sent"]                  # the comment states a requester can read


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _refusal(tenant_id: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The answer that says why this row cannot be withdrawn, or None when it can. The row is checked here and
    the ticket is checked again by the compare-and-set that hides the answer."""
    if tenant_id == PLATFORM_TENANT_ID:
        return {"status": "refused", "reason": "not_undoable"}
    if row.get("state") == "undone":
        return {"status": "already_handled"}
    desk = row.get("desk") if isinstance(row.get("desk"), dict) else {}
    if (row.get("state") not in _UNDOABLE_STATES or row.get("shadow") or row.get("kind") != ledger.DESK_KIND
            or row.get("command") != "ticket_answer" or desk.get("undoable") is not True
            or desk.get("phase") not in _POSTED_PHASES or not isinstance(desk.get("ticketId"), str)):
        return {"status": "refused", "reason": "not_undoable"}
    return None


def _name(actor: Dict[str, Any]) -> str:
    return str(actor.get("display") or actor.get("username") or "unknown")


async def _hide_answer(db, tenant_id: str, ticket_id: str, comment_id: str, who: Dict[str, str],
                       now: datetime) -> bool:
    """The one compare-and-set that withdraws: the comment turns ``withdrawn`` and the ticket's desk fields end
    Undo, only while the ticket still shows this answer as posted or sent and undoable. False when it no
    longer does (the requester confirmed, a person replied, or another click won)."""
    at = now.isoformat()
    result = await raw(db).tickets.update_one(
        {"id": ticket_id, "tenantId": tenant_id, "desk.undoable": True, "desk.phase": {"$in": list(_POSTED_PHASES)},
         "comments": {"$elemMatch": {"id": comment_id, "kind": "ai_answer", "ai.state": {"$in": _VISIBLE}}}},
        {"$set": {"comments.$.ai.state": "withdrawn", "comments.$.ai.withdrawnBy": who,
                  "comments.$.ai.withdrawnAt": at, "desk.phase": "withdrawn", "desk.undoable": False,
                  "desk.withdrawnAt": now, "desk.withdrawnBy": who, "updated_at": at},
         "$push": {"history": {"id": comment_id + "-withdrawn", "actor": who["id"], "action": "answer_withdrawn",
                               "changes": {"comment": comment_id}, "created_at": at}}})
    return result.matched_count == 1


async def _put_row_back(db, tenant_id: str, row: Dict[str, Any], actor: Dict[str, Any]) -> None:
    """The withdrawal did not reach the ticket: the row goes back to what it was, so it never says undone while
    the requester can still read the answer."""
    desk = row.get("desk") or {}
    try:
        await ledger.transition(
            db, tenant_id, row["id"], ("undone",), row["state"], actor=actor,
            undo=row.get("undo") or {"available": True, "action": COMMAND_WITHDRAW, "params": {}, "undoneAt": None,
                                     "undoneBy": None},
            **{"desk.phase": desk.get("phase"), "desk.undoable": True})
    except Exception as exc:
        logger.error("service_desk: the row %s could not be put back after a failed withdrawal: %s", row["id"], exc)


async def _step(label: str, ticket_id: str, call) -> Any:
    """One write after the answer is hidden. A failure is logged and the rest still runs: the requester no longer
    reads the answer, and the ticket must still reach a person."""
    try:
        return await call
    except Exception as exc:
        logger.error("service_desk: %s for ticket %s did not complete: %s", label, ticket_id, exc)
        return None


async def evaluate_breaker(db, tenant_id: str, *, now: Optional[datetime] = None) -> bool:
    """Drop the desk to Drafts only after DESK_BREAKER_THRESHOLD (3) automatically posted answers were withdrawn
    within DESK_BREAKER_WINDOW (24 hours). True when THIS call tripped it.

    Only rows the desk posted on its own count: a draft a person sent (``desk.sentBy``) is that person's decision,
    and an I still need help never makes a row undone. One compare-and-set on ``serviceDesk.mode`` decides the
    winner, so concurrent withdrawals trip it once and notify once. The tenant's Autonomous Ops level, its own
    breaker and the on-call page are never touched (D-25, PROH-85-08): the Phase 81 breaker module is not called."""
    now = _now(now)
    if tenant_id == PLATFORM_TENANT_ID:
        return False
    cursor = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "kind": ledger.DESK_KIND, "state": "undone", "autoDispatched": True,
         "desk.sentBy": None, "undo.undoneAt": {"$gt": now - DESK_BREAKER_WINDOW}},
        {"_id": 0, "id": 1}).sort("undo.undoneAt", -1).limit(DESK_BREAKER_THRESHOLD)
    rows = await cursor.to_list(length=DESK_BREAKER_THRESHOLD)
    if len(rows) < DESK_BREAKER_THRESHOLD:
        return False
    breaker = {"trippedAt": now, "actionIds": [r["id"] for r in rows]}
    won = await raw(db).autonomy_settings.update_one(
        {"tenantId": tenant_id, "serviceDesk.mode": "post", "serviceDesk.breaker": None},
        {"$set": {"serviceDesk.mode": "drafts", "serviceDesk.breaker": breaker, "updatedAt": now,
                  "updatedBy": "system"}})
    if won.modified_count != 1:
        return False                          # already at Drafts only or Off, or another withdrawal tripped it first
    try:
        await ledger.record_control(db, tenant_id, _EVENT, scope="tenant", actor=_DESK_ACTOR,
                                    reason=messages.CONTROL_REASONS[_EVENT])
    except Exception as exc:                  # the mode is already lowered; say so in the log
        logger.error("service_desk: the desk breaker trip for %s was not recorded in the ledger: %s", tenant_id, exc)
    try:
        from notification_service import get_notification_service
        await get_notification_service(raw(db)).send_alert(
            messages.BREAKER_NOTICE_TITLE, messages.BREAKER_NOTICE, "warning", recipients=[], tenant_id=tenant_id,
            channels=[], metadata={"source": "service_desk", "event": _EVENT,
                                   "audience": "tenant_admins", "actionIds": breaker["actionIds"]})
    except Exception as exc:
        logger.warning("service_desk: the desk breaker notice for %s was not stored: %s", tenant_id, exc)
    return True


async def undo_answer(db, tenant_id: str, row: Dict[str, Any], *, actor: Dict[str, Any],
                      now: Optional[datetime] = None) -> Dict[str, Any]:
    """Withdraw the answer of desk ``row``. Returns ``{"status": "undone", "desk_breaker_tripped": bool}``,
    ``{"status": "already_handled"}`` or ``{"status": "refused", "reason": "not_undoable"}`` (the route turns the
    last two into 409). ``actor`` is the ledger actor ``{username, display, tier}`` of the person who clicked."""
    refusal = _refusal(tenant_id, row)
    if refusal is not None:
        return refusal
    now = _now(now)
    desk = row["desk"]
    ticket_id = desk["ticketId"]
    comment_id = desk.get("commentId") or "sd-" + row["id"]
    who = {"id": str(actor.get("username") or actor.get("display") or ""), "name": _name(actor)}
    zone = await workdays.tenant_zone(db, tenant_id)
    block = {"available": True, "action": COMMAND_WITHDRAW, "params": {"ticketId": ticket_id}, "undoneAt": now,
             "undoneBy": dict(actor)}
    moved = await ledger.transition(
        db, tenant_id, row["id"], _UNDOABLE_STATES, "undone", actor=actor, undo=block,
        **{"desk.phase": "withdrawn", "desk.undoable": False, "desk.withdrawnAt": now, "desk.withdrawnBy": who})
    if moved is None:
        return {"status": "already_handled"}

    try:
        hidden = await _hide_answer(db, tenant_id, ticket_id, comment_id, who, now)
    except Exception:
        await _put_row_back(db, tenant_id, row, actor)
        raise
    if not hidden:
        await _put_row_back(db, tenant_id, row, actor)
        stored = await raw(db).tickets.find_one({"id": ticket_id, "tenantId": tenant_id}, {"_id": 0, "desk.phase": 1})
        if ((stored or {}).get("desk") or {}).get("phase") == "withdrawn":
            return {"status": "already_handled"}
        return {"status": "refused", "reason": "not_undoable"}

    await _step("the withdrawal notice", ticket_id, ticket_writes.add_comment(
        db, tenant_id, ticket_id, comment_id="sd-withdrawn-" + row["id"], kind="withdrawn_notice",
        visibility="requester", text=messages.WITHDRAWN_NOTICE, author=SYSTEM_AUTHOR, now=now))
    await _step("the status change", ticket_id, ticket_writes.move_status(
        db, tenant_id, ticket_id, ("pending_customer",), "open", actor=who["id"], now=now))
    await _step("the Activity words", ticket_id, ledger.set_display(
        db, tenant_id, row["id"], activityResult=messages.ACTIVITY["withdrawn_result"].format(
            name=who["name"], time=windows.clock_text(now, zone))))
    ticket = await raw(db).tickets.find_one({"id": ticket_id, "tenantId": tenant_id}, {"_id": 0})
    if ticket is not None:
        await _step("the hand-off", ticket_id, handoff.handoff(
            db, ticket, "answer_withdrawn", now=now, notify_requester=False, actor=actor))
        # handoff() marks the ticket handed off; the requester panel reads withdrawn, so it is set again
        await _step("the desk fields", ticket_id, ticket_writes.set_desk(
            db, tenant_id, ticket_id, {"phase": "withdrawn", "undoable": False}, now=now))
        text = messages.WITHDRAWN_NOTICE_TITLE.format(number=ticket.get("ticket_number") or "")
        await _step("the requester notice", ticket_id, notify.requester_notice(
            db, ticket, event="answer_withdrawn", title=text, message=text))

    tripped = False
    try:
        tripped = await evaluate_breaker(db, tenant_id, now=now)
    except Exception as exc:
        logger.error("service_desk: the desk breaker check after the withdrawal of %s failed: %s", row["id"], exc)
    return {"status": "undone", "desk_breaker_tripped": bool(tripped)}


approvals.register_undo_handler(DISPATCHER_NAME, undo_answer)
