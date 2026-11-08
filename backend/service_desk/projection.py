"""What a requester may see of a ticket's desk activity.

Only comments marked ``requester`` are projected; a comment with no visibility reads as staff, so
every older comment stays staff-only without a data change. Plain data only; the portal and the tray
render the text as text.
"""
from typing import Any, Dict, List


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
