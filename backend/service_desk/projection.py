"""What a requester may see of a ticket's desk activity.

Only comments marked ``requester`` are projected; a comment with no visibility reads as staff, so
every older comment stays staff-only without a data change. Plain data only; the portal and the tray
render the text as text.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import ANSWER_MAX_CHARS, PERSON_RAISED, messages

CLOSED_STATUSES = ("resolved", "closed")
ANSWERED_PHASES = ("posted", "sent")                # an answer is with the requester
NOTICES = {"confirmed": "confirmed", "helped": "helped", "handed_off": "handed_off", "returned": "handed_off",
           "withdrawn": "withdrawn"}                  # desk.phase -> the requester panel's notice


def requester_items(ticket: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The requester-visible comments, oldest first."""
    comments = [c for c in (ticket.get("comments") or []) if isinstance(c, dict) and c.get("visibility") == "requester"]
    comments.sort(key=lambda c: (str(c.get("created_at") or ""), str(c.get("id") or "")))
    items = []
    for comment in comments:
        kind = comment.get("kind")
        ai = comment.get("ai") if isinstance(comment.get("ai"), dict) else {}
        citations = []
        if kind == "ai_answer":
            citations = [{"articleId": c.get("articleId"), "title": c.get("title")}
                         for c in (ai.get("citations") or []) if isinstance(c, dict)]
        items.append({"id": comment.get("id"), "kind": kind, "at": comment.get("created_at"),
                      "author": comment.get("author"), "text": comment.get("text"), "citations": citations})
    return items


def can_see(ticket: Dict[str, Any]) -> bool:
    """True when the requester has a place to read an answer: the portal, or the tray with My tickets."""
    channel = ticket.get("requester_channel")
    if not isinstance(channel, dict):
        return False
    return channel.get("portal") is True or (channel.get("tray") is True and channel.get("myTickets") is True)


def _text(value: Any) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def same_person(reporter: Any, name: Any) -> bool:
    """True when ``name`` (a comment author or user name) is the ticket's reporter, ignoring case."""
    return bool(_text(reporter)) and _text(reporter) == _text(name)


def is_reporter(ticket: Dict[str, Any], user: Any) -> bool:
    """True when ``user`` (anything with ``username`` and ``email``) is the person who raised the ticket."""
    reporter = _text(ticket.get("reporter"))
    names = {_text(getattr(user, field, "")) for field in ("username", "email")} - {""}
    return bool(reporter) and reporter in names


def iso(value: Any) -> Optional[str]:
    """A stored moment (datetime, naive ones read as UTC, or an ISO string) as an ISO 8601 string."""
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return value if isinstance(value, str) and value else None


def waiting_draft(ticket: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The newest staff draft nobody has sent or discarded yet, or None."""
    drafts = [c for c in (ticket.get("comments") or [])
              if isinstance(c, dict) and c.get("kind") == "ai_draft"
              and isinstance(c.get("ai"), dict) and c["ai"].get("state") == "draft"]
    drafts.sort(key=lambda c: (str(c.get("created_at") or ""), str(c.get("id") or "")))
    return drafts[-1] if drafts else None


def person_replied(ticket: Dict[str, Any]) -> bool:
    """True once a person other than the reporter has written to the requester: the flag the comment hook
    sets, or a requester-visible plain comment by someone else (the desk's own comments carry a kind)."""
    desk = ticket.get("desk") if isinstance(ticket.get("desk"), dict) else {}
    if desk.get("personReplied") is True:
        return True
    reporter = _text(ticket.get("reporter"))
    return any(isinstance(c, dict) and c.get("visibility") == "requester" and not c.get("kind")
               and _text(c.get("author")) != reporter for c in (ticket.get("comments") or []))


def blocked(ticket: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Why a waiting draft cannot be sent right now: (code, text), or (None, None). Discarding stays open."""
    status = ticket.get("status") or ""
    code = None
    if status in CLOSED_STATUSES:
        code = "ticket_closed"
    elif person_replied(ticket):
        code = "person_replied"
    elif not can_see(ticket):
        code = "no_requester"
    return (code, messages.API_DETAIL[code].format(state=status)) if code else (None, None)


def can_reply(ticket: Dict[str, Any]) -> bool:
    """True when staff may reply to the requester: a person raised the ticket and can read the reply."""
    return ticket.get("raised_via") in PERSON_RAISED and can_see(ticket)


def staff_view(ticket: Dict[str, Any], row: Optional[Dict[str, Any]], viewer: Any) -> Optional[Dict[str, Any]]:
    """The staff draft panel (``DraftView``), or None: no draft is waiting, or ``viewer`` raised the ticket
    (a requester never learns that a draft exists)."""
    comment = waiting_draft(ticket)
    if comment is None or is_reporter(ticket, viewer):
        return None
    ai = comment["ai"]
    citations = [{"articleId": c.get("articleId"), "title": c.get("title")}
                 for c in (ai.get("citations") or []) if isinstance(c, dict)]
    desk = ticket.get("desk") if isinstance(ticket.get("desk"), dict) else {}
    row_desk = (row or {}).get("desk") if isinstance((row or {}).get("desk"), dict) else {}
    reason = desk.get("draftReason") or row_desk.get("draftReason")
    code, text = blocked(ticket)
    return {"commentId": comment.get("id"), "actionId": ai.get("actionId"), "answer": comment.get("text"),
            "citations": citations, "createdAt": iso(comment.get("created_at")), "articleCount": len(citations),
            "draftReason": reason, "draftReasonText": messages.DRAFT_REASON_TEXT.get(reason),
            "maxAnswerLength": ANSWER_MAX_CHARS, "canActOnDraft": code is None,
            "blockedReason": code, "blockedText": text, "reporter": ticket.get("reporter")}


def confirmable(ticket: Dict[str, Any]) -> bool:
    """True while an answer is with the requester and the ticket waits on them: the only time they can say
    This fixed it or I still need help."""
    desk = ticket.get("desk") if isinstance(ticket.get("desk"), dict) else {}
    return desk.get("phase") in ANSWERED_PHASES and ticket.get("status") == "pending_customer"


def requester_view(ticket: Dict[str, Any], zone: str = "UTC") -> Dict[str, Any]:
    """What the reporter's answer panel reads: the requester-visible items, whether they can answer it, the
    notice that replaces the buttons once they have, and when they confirmed. Never a draft, a staff-only
    comment or a reason."""
    desk = ticket.get("desk") if isinstance(ticket.get("desk"), dict) else {}
    return {"items": requester_items(ticket), "canSee": can_see(ticket), "canConfirm": confirmable(ticket),
            "notice": NOTICES.get(desk.get("phase")), "confirmedAt": iso(desk.get("confirmedAt")),
            "returnAt": None}
