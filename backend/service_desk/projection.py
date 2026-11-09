"""What a requester may see of a ticket's desk activity.

Only comments marked ``requester`` are projected; a comment with no visibility reads as staff, so
every older comment stays staff-only without a data change. Plain data only; the portal and the tray
render the text as text. ``for_viewer`` and ``history_for_viewer`` are the reporter projection of the legacy
ticket JSON (CR-401, D-11): what a caller may read of a ticket. Only ticket staff who did not raise it get the stored
ticket, told by the ``staff`` input, which defaults to False so a caller that forgets it gets the projection (T-85-117).
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import ANSWER_MAX_CHARS, PERSON_RAISED, RETURN_WORKING_DAYS, messages, workdays

CLOSED_STATUSES = ("resolved", "closed")
ANSWERED_PHASES = ("posted", "sent")                # an answer is with the requester
NOTICES = {"confirmed": "confirmed", "helped": "helped", "handed_off": "handed_off", "returned": "handed_off",
           "withdrawn": "withdrawn"}                  # desk.phase -> the requester panel's notice


def requester_items(ticket: Dict[str, Any], names: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """The requester-visible comments, oldest first. An answer that was withdrawn is left out (the requester
    reads the withdrawal notice instead). With ``names`` (lowercase user name -> profile name) a reply written
    by a person shows that person's name, or no name when there is no profile (the screen then says IT)."""
    comments = [c for c in (ticket.get("comments") or []) if _requester_visible(c)]
    comments.sort(key=lambda c: (str(c.get("created_at") or ""), str(c.get("id") or "")))
    items = []
    for comment in comments:
        kind = comment.get("kind")
        ai = comment.get("ai") if isinstance(comment.get("ai"), dict) else {}
        citations = []
        if kind == "ai_answer":
            citations = [{"articleId": c.get("articleId"), "title": c.get("title")}
                         for c in (ai.get("citations") or []) if isinstance(c, dict)]
        author = comment.get("author")
        if names is not None and _staff_reply(ticket, comment):
            author = names.get(_text(author))
        items.append({"id": comment.get("id"), "kind": kind, "at": comment.get("created_at"),
                      "author": author, "text": comment.get("text"), "citations": citations})
    return items


def _requester_visible(comment: Any) -> bool:
    """A comment marked for the requester that is not a withdrawn answer: the one rule the answer panel and the
    reporter's comment list both read, so they cannot drift."""
    return isinstance(comment, dict) and comment.get("visibility") == "requester" and not _withdrawn(comment)


def _withdrawn(comment: Dict[str, Any]) -> bool:
    ai = comment.get("ai") if isinstance(comment.get("ai"), dict) else {}
    return comment.get("kind") == "ai_answer" and ai.get("state") == "withdrawn"


def _staff_reply(ticket: Dict[str, Any], comment: Dict[str, Any]) -> bool:
    """A plain requester-visible comment written by someone other than the reporter."""
    return not comment.get("kind") and _text(comment.get("author")) != _text(ticket.get("reporter"))


def staff_reply_authors(ticket: Dict[str, Any]) -> List[str]:
    """The user names behind the requester-visible staff replies (to look their profile names up)."""
    return sorted({c["author"] for c in (ticket.get("comments") or [])
                   if isinstance(c, dict) and c.get("visibility") == "requester" and _staff_reply(ticket, c)
                   and isinstance(c.get("author"), str) and c["author"]})


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


# ---------------------------------------------------------------- the reporter's own ticket (CR-401, D-11)

REPORTER_AI_KEYS = ("state", "citations", "sentBy", "postedAt", "sentAt")     # what an AI comment keeps for the reporter
REPORTER_DESK_KEYS: Tuple[str, ...] = ()      # no desk field is the reporter's: they read desk state only through requester_view
REPORTER_HIDDEN_HISTORY_ACTIONS = ("draft_sent", "draft_discarded")
_PREVIEW_CHARS = 80                           # tickets_service.add_comment keeps this much of a requester comment in history


def requester_may_read(ticket: Dict[str, Any], comment: Any) -> bool:
    """True when the reporter may read ``comment`` on their own ticket: a requester-visible comment that is not a
    withdrawn answer, or any comment the reporter wrote themselves (the portal stores it as staff-only by default),
    never an AI draft."""
    if not isinstance(comment, dict) or comment.get("kind") == "ai_draft":
        return False
    return _requester_visible(comment) or same_person(ticket.get("reporter"), comment.get("author"))


def _reporter_comment(comment: Dict[str, Any]) -> Dict[str, Any]:
    shown = dict(comment)
    if "ai" in shown and shown["ai"] is not None:
        ai = shown["ai"] if isinstance(shown["ai"], dict) else {}
        shown["ai"] = {key: ai[key] for key in REPORTER_AI_KEYS if key in ai}
        if isinstance(ai.get("citations"), list):
            shown["ai"]["citations"] = [{"articleId": c.get("articleId"), "title": c.get("title")}
                                        for c in ai["citations"] if isinstance(c, dict)]
    return shown


def reporter_history(ticket: Dict[str, Any], entries: Any) -> List[Dict[str, Any]]:
    """The history the reporter may read: no draft entry, and a commented entry only when the reporter wrote it,
    the desk marked it for the requester, or its preview is the start of a comment they may read. Status,
    assignment and every other entry stay."""
    readable = {str(c.get("text") or "")[:_PREVIEW_CHARS] for c in (ticket.get("comments") or [])
                if requester_may_read(ticket, c)}
    shown = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("action") in REPORTER_HIDDEN_HISTORY_ACTIONS:
            continue
        if entry.get("action") == "commented":
            changes = entry.get("changes") if isinstance(entry.get("changes"), dict) else {}
            if not (same_person(ticket.get("reporter"), entry.get("actor")) or changes.get("visibility") == "requester"
                    or (isinstance(changes.get("preview"), str) and changes["preview"] in readable)):
                continue
        shown.append(entry)
    return shown


def reporter_ticket(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """The ticket as its reporter may read it: the comments they may read (an AI comment cut down to
    ``REPORTER_AI_KEYS``), no desk field and the reporter history."""
    shown = dict(ticket)
    shown.pop("desk", None)                   # REPORTER_DESK_KEYS is empty: no desk field is the reporter's
    if "comments" in ticket:
        shown["comments"] = [_reporter_comment(c) for c in (ticket.get("comments") or []) if requester_may_read(ticket, c)]
    if "history" in ticket:
        shown["history"] = reporter_history(ticket, ticket.get("history"))
    return shown


def for_viewer(ticket: Optional[Dict[str, Any]], user: Any, *, staff: bool = False) -> Optional[Dict[str, Any]]:
    """``ticket`` as ``user`` may read it (D-11): the stored ticket only for ticket staff who did not raise it, the
    reporter projection for everybody else, including staff who raised it. ``staff`` defaults to False (fail closed)."""
    if ticket is None or (staff and not is_reporter(ticket, user)):
        return ticket
    return reporter_ticket(ticket)


def history_for_viewer(ticket: Dict[str, Any], entries: Any, user: Any, *, staff: bool = False) -> Any:
    """A history list as ``user`` may read it: the full history only for ticket staff who did not raise the ticket,
    the reporter history for everybody else. ``staff`` defaults to False (fail closed)."""
    return entries if staff and not is_reporter(ticket, user) else reporter_history(ticket, entries)


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


def _moment(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def return_at(ticket: Dict[str, Any], zone: str) -> Optional[str]:
    """When a person from IT picks the ticket up if the requester stays silent (D-08): three working days after
    the answer reached them, in the tenant's zone. Worked out here every time it is shown, never stored."""
    posted = _moment((ticket.get("desk") or {}).get("postedAt")) if confirmable(ticket) else None
    return workdays.add_working_days(posted, RETURN_WORKING_DAYS, zone).isoformat() if posted else None


def requester_view(ticket: Dict[str, Any], zone: str = "UTC", names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """What the reporter's answer panel reads: the requester-visible items, whether they can answer it, when a
    person will pick it up, the notice that replaces the buttons once they have answered, and when they
    confirmed. Never a draft, a staff-only comment or a reason."""
    desk = ticket.get("desk") if isinstance(ticket.get("desk"), dict) else {}
    return {"items": requester_items(ticket, names), "canSee": can_see(ticket), "canConfirm": confirmable(ticket),
            "returnAt": return_at(ticket, zone), "notice": NOTICES.get(desk.get("phase")),
            "confirmedAt": iso(desk.get("confirmedAt"))}


def cited_articles(ticket: Dict[str, Any], *, for_requester: bool) -> Dict[str, str]:
    """{article id: cited title} for the articles that may be opened from this ticket (D-14). The reporter:
    those cited on an answer they can see (requester-visible, not withdrawn). Staff: those cited on any answer
    and on the waiting draft."""
    found: Dict[str, str] = {}
    for comment in ticket.get("comments") or []:
        if not isinstance(comment, dict) or not isinstance(comment.get("ai"), dict):
            continue
        ai, kind = comment["ai"], comment.get("kind")
        if for_requester:
            visible = kind == "ai_answer" and comment.get("visibility") == "requester" and not _withdrawn(comment)
        else:
            visible = kind == "ai_answer" or (kind == "ai_draft" and ai.get("state") == "draft")
        if visible:
            for citation in ai.get("citations") or []:
                if isinstance(citation, dict) and isinstance(citation.get("articleId"), str):
                    found.setdefault(citation["articleId"], citation.get("title") or "")
    return found


def cited_article_ids(ticket: Dict[str, Any], *, for_requester: bool) -> List[str]:
    """The allow-list of article ids a viewer may open from this ticket."""
    return list(cited_articles(ticket, for_requester=for_requester))


# ---------------------------------------------------------------- the tray window (D-05, D-11, D-14)

TRAY_WITH_IT_PHASES = ("handed_off", "withdrawn", "helped")


def _tray_citations(comment: Dict[str, Any]) -> List[Dict[str, Any]]:
    ai = comment.get("ai") if isinstance(comment.get("ai"), dict) else {}
    return [{"articleId": c["articleId"], "title": c.get("title") or ""}
            for c in (ai.get("citations") or []) if isinstance(c, dict) and isinstance(c.get("articleId"), str)]


def _tray_entry(ticket: Dict[str, Any], comment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One tray entry for a requester-visible comment, or None for a comment the tray never shows. An allow-list
    by comment kind: a draft, a staff note, the withdrawal notice (the withdrawn answer itself stands for it)
    and any kind not named here stay out."""
    kind = comment.get("kind")
    text = comment.get("text") if isinstance(comment.get("text"), str) else ""
    at = iso(comment.get("created_at"))
    if kind == "ai_answer":
        if _withdrawn(comment):
            ai = comment["ai"]
            return {"kind": "withdrawn", "at": iso(ai.get("withdrawnAt")) or at, "heading": "",
                    "text": messages.WITHDRAWN_NOTICE, "citations": []}
        return {"kind": "answer", "at": at, "heading": messages.TRAY_HEADINGS["answer"], "text": text,
                "citations": _tray_citations(comment)}
    if kind == "requester_reply":
        return {"kind": "you", "at": at, "heading": messages.TRAY_HEADINGS["you"], "text": text, "citations": []}
    if kind == "handoff_notice":
        return {"kind": "notice", "at": at, "heading": "", "text": text, "citations": []}
    if not kind and not same_person(ticket.get("reporter"), comment.get("author")):
        return {"kind": "reply", "at": at, "heading": messages.TRAY_HEADINGS["reply"], "text": text, "citations": []}
    return None


def tray_status(ticket: Dict[str, Any]) -> str:
    """The key of ``messages.TRAY_STATUS_TEXT`` for the ticket. A waiting draft is not a state the requester
    can know about, so it reads as received."""
    status = ticket.get("status") or ""
    desk = ticket.get("desk") if isinstance(ticket.get("desk"), dict) else {}
    if status in CLOSED_STATUSES:
        return status
    if confirmable(ticket):
        return "answer_ready"
    if status == "pending_customer":
        return "waiting_for_you"
    if desk.get("phase") in TRAY_WITH_IT_PHASES or status in ("in_progress", "on_hold") or person_replied(ticket):
        return "with_it"
    return "received"


def tray_view(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """The one ticket entry of the tray's My tickets list (``tray_contract.TICKET_FIELDS``), built field by field
    from what the requester may see and never a copy of the ticket (T-85-71): the requester-visible comments by
    kind (answers with their citations, replies from IT, the requester's own notes, notices, a withdrawn answer as
    the withdrawal notice), the status in the tray's words and whether the two buttons are on. A draft, a staff
    note, a hand-off reason and the text of a withdrawn answer are never read into it. ``answerIds`` lists the
    answers that are still the requester's to read (a withdrawn one is not)."""
    visible = [c for c in (ticket.get("comments") or []) if isinstance(c, dict) and c.get("visibility") == "requester"]
    entries = []
    for comment in visible:
        entry = _tray_entry(ticket, comment)
        if entry is not None:
            entries.append((entry["at"] or "", str(comment.get("id") or ""), entry))
    entries.sort(key=lambda row: (row[0], row[1]))
    answer_ids = [cid for _, cid, entry in entries if entry["kind"] == "answer"]
    key = tray_status(ticket)
    can_confirm = confirmable(ticket)
    desk = ticket.get("desk") if isinstance(ticket.get("desk"), dict) else {}
    reason = ""
    if key in CLOSED_STATUSES:
        reason = messages.TRAY_REASON_LINES["resolved"]
    elif not can_confirm and desk.get("phase") == "withdrawn":
        reason = messages.TRAY_REASON_LINES["withdrawn"]
    elif not can_confirm and key == "with_it":
        reason = messages.TRAY_REASON_LINES["with_it"]
    return {"id": ticket.get("id"), "number": ticket.get("ticket_number"), "title": ticket.get("title") or "",
            "status": ticket.get("status") or "", "statusText": messages.TRAY_STATUS_TEXT[key],
            "canConfirm": can_confirm, "canHelp": can_confirm, "reasonLine": reason,
            "entries": [entry for _, _, entry in entries], "answerIds": answer_ids,
            "updatedAt": iso(ticket.get("updated_at"))}


def tray_display(user: str) -> Dict[str, str]:
    """The three display strings of the list response: the footnote (it says what is shown and does not claim
    it is private, D-34), the line under the answer buttons and the empty-list text."""
    return {"footnote": messages.TRAY_FOOTNOTE.format(user=user), "footer": messages.FOOTER,
            "empty": messages.TRAY_EMPTY}
