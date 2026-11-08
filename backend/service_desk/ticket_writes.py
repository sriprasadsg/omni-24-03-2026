"""The desk's writes to a ticket: a comment, a guarded status change and the ``desk`` subdocument.

Each write is one filtered update on the raw handle (id and tenantId in every filter), so a
ticket of another tenant can never be touched and a write that lost a race changes nothing. The
status change mirrors the hold bookkeeping of ``TicketsService.update_ticket`` (entering a hold
status starts the clock, leaving it adds the elapsed seconds). Nothing here notifies anyone: a
desk comment never goes out through the ticket notification path.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from autonomous_ops.scope import raw

_HOLD_STATUSES = {"on_hold", "pending_customer"}


def _aware(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _history(actor: str, action: str, changes: Dict[str, Any], at: str) -> Dict[str, Any]:
    return {"id": str(uuid.uuid4()), "actor": actor, "action": action, "changes": changes, "created_at": at}


async def add_comment(db, tenant_id: str, ticket_id: str, *, comment_id: str, kind: str, visibility: str,
                      text: str, author: str, ai: Optional[Dict[str, Any]] = None,
                      now: Optional[datetime] = None) -> bool:
    """Add one comment. Idempotent on ``comment_id``: a second call with the same id adds nothing and
    returns False. The history entry names the kind and the visibility, never the text."""
    at = _aware(now).isoformat()
    comment = {"id": comment_id, "author": author, "text": text, "created_at": at, "edited": False,
               "visibility": visibility, "kind": kind, "ai": ai}
    result = await raw(db).tickets.update_one(
        {"id": ticket_id, "tenantId": tenant_id, "comments.id": {"$ne": comment_id}},
        {"$push": {"comments": comment,
                   "history": _history(author, "commented", {"kind": kind, "visibility": visibility}, at)},
         "$set": {"updated_at": at}})
    return result.matched_count == 1


def _hold_seconds(existing: Dict[str, Any], at: str) -> Optional[float]:
    started = existing.get("hold_started_at")
    if not started:
        return None
    try:
        begun = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        ended = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    begun = begun if begun.tzinfo else begun.replace(tzinfo=timezone.utc)
    ended = ended if ended.tzinfo else ended.replace(tzinfo=timezone.utc)
    return (ended - begun).total_seconds()


async def move_status(db, tenant_id: str, ticket_id: str, from_statuses: Iterable[str], to_status: str, *,
                      actor: str, now: Optional[datetime] = None, extra: Optional[Dict[str, Any]] = None) -> bool:
    """Compare-and-set on the status: moves the ticket only while it is still in one of ``from_statuses``
    (a person who already moved it is never overridden). True when the ticket moved."""
    allowed = list(from_statuses)
    at = _aware(now).isoformat()
    handle = raw(db).tickets
    existing = await handle.find_one({"id": ticket_id, "tenantId": tenant_id, "status": {"$in": allowed}}, {"_id": 0})
    if existing is None:
        return False
    old = existing.get("status", "")
    patch: Dict[str, Any] = {"status": to_status, "updated_at": at, **(extra or {})}
    if to_status in _HOLD_STATUSES and old not in _HOLD_STATUSES:
        patch["hold_started_at"] = at
    elif to_status not in _HOLD_STATUSES and old in _HOLD_STATUSES:
        elapsed = _hold_seconds(existing, at)
        if elapsed is not None:
            patch["total_hold_duration"] = (existing.get("total_hold_duration") or 0) + elapsed
        patch["hold_started_at"] = None
    result = await handle.update_one(
        {"id": ticket_id, "tenantId": tenant_id, "status": old},
        {"$set": patch, "$push": {"history": _history(actor, "updated", {"status": {"from": old, "to": to_status}}, at)}})
    return result.matched_count == 1


async def set_desk(db, tenant_id: str, ticket_id: str, fields: Dict[str, Any],
                   now: Optional[datetime] = None) -> bool:
    """Set ``desk.<key>`` for each field. True when the ticket exists in this tenant."""
    sets = {f"desk.{key}": value for key, value in fields.items()}
    sets["updated_at"] = _aware(now).isoformat()
    result = await raw(db).tickets.update_one({"id": ticket_id, "tenantId": tenant_id}, {"$set": sets})
    return result.matched_count == 1
