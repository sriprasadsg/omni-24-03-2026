"""The backend half of on-call delivery (Phase 82, plan 82-07, HEAL-05).

The backend never holds the on-call key. It keeps two small queues in MongoDB and the watchdog (a
separate process that owns the key) drains them through the sync round trip:

* ``oncall_outbox`` - one trigger message per Autonomous Ops notice (``notify`` feeds it, D-04).
  The sync response lists up to 20 undelivered, unexpired messages, oldest first. A ``delivered``
  entry in a later sync body (or in ``POST /results``) marks a message delivered, exactly once.
  Messages expire after 24 hours so a channel set up next week does not page about last week.
* ``oncall_test_requests`` - the Super Admin's "Send test alert" (D-21). One request is pending at
  a time; a click storm gets the same request back. The sync response carries it as ``testRequest``
  and the watchdog's ``testResult`` closes it and writes one ``test_alert`` platform-health row.

Nothing here carries a routing key or URL: messages hold the notice text and a severity, nothing
else. Raw Mongo handle (``scope.raw``) with explicit ids; ``enqueue`` never raises.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from . import ledger, selfheal
from .scope import raw

logger = logging.getLogger(__name__)

OUTBOX_TTL = timedelta(hours=24)
MAX_OUTBOX_PER_SYNC = 20
SUMMARY_MAX = 1024
ERROR_MAX = 300
# A test request the watchdog never picked up is closed as failed after this long, so one lost
# request cannot block every later test.
TEST_PENDING_MAX = timedelta(minutes=10)
TEST_NO_ANSWER = "The watchdog did not pick this request up."

_SEVERITY = {"critical": "critical", "warning": "warning", "info": "info"}     # A-82-A7; anything else: warning
_DETAIL_BLOCKED = frozenset({"token", "routing_key", "routingkey", "webhookurl", "heartbeaturl", "url", "key",
                             "secret", "password"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _outbox(db):
    return raw(db).oncall_outbox


def _requests(db):
    return raw(db).oncall_test_requests


def _iso(value: Any) -> Optional[str]:
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


async def ensure_indexes(db) -> None:
    """Idempotent. Messages expire through the TTL index; one request may be pending at a time."""
    await _outbox(db).create_index("id", unique=True, name="id_unique")
    await _outbox(db).create_index("expiresAt", expireAfterSeconds=0, name="expires_ttl")
    await _outbox(db).create_index("deliveredAt", name="delivered")
    await _requests(db).create_index("id", unique=True, name="id_unique")
    await _requests(db).create_index("requestedAt", name="requested")
    await _requests(db).create_index("state", unique=True, name="one_pending",
                                     partialFilterExpression={"state": "pending"})


# ---------------------------------------------------------------- outbox

def map_severity(severity: Any) -> str:
    """notify severity -> on-call severity: critical, warning and info stay; anything else is a warning."""
    return _SEVERITY.get(str(severity or "").lower(), "warning")


def _details(title: str, message: str, tenant_id: str, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Scalars only, strings capped; a key that could hold a credential is dropped."""
    details: Dict[str, Any] = {"title": selfheal.clean_text(title, 200), "message": selfheal.clean_text(message, SUMMARY_MAX),
                               "tenantId": selfheal.clean_text(tenant_id, 128)}
    for key, value in list((metadata or {}).items())[:16]:
        name = selfheal.clean_text(key, 64)
        if name.lower() in _DETAIL_BLOCKED or name in details:
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            details[name] = value
        elif isinstance(value, str) and value:
            details[name] = selfheal.clean_text(value, 200)
    return details


async def enqueue(db, *, tenant_id: str, title: str, message: str, severity: str = "warning",
                  metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Queue one trigger message for the watchdog; returns its id, or None when it could not be stored.
    Never raises (a failing queue must not undo a decision) and logs no message content."""
    try:
        now = _now()
        summary = selfheal.clean_text(f"{title}: {message}" if message else title, SUMMARY_MAX)
        doc = {"id": "OB-" + uuid.uuid4().hex, "kind": "trigger", "dedupKey": None, "severity": map_severity(severity),
               "summary": summary, "details": _details(title, message, tenant_id, metadata),
               "tenantId": tenant_id, "source": "autonomous_ops", "createdAt": now, "expiresAt": now + OUTBOX_TTL,
               "deliveredAt": None, "ok": None, "error": None}
        await _outbox(db).insert_one(doc)
        return doc["id"]
    except Exception as exc:
        logger.warning("autonomous_ops: on-call message for %s was not queued: %s", tenant_id, type(exc).__name__)
        return None


async def pending_outbox(db, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Up to 20 undelivered, unexpired messages, oldest first, in the shape the sync response carries:
    ``{id, kind, dedupKey, severity, summary, details}``."""
    now = now or _now()
    found = (_outbox(db).find({"deliveredAt": None, "expiresAt": {"$gt": now}},
                              {"_id": 0, "id": 1, "kind": 1, "dedupKey": 1, "severity": 1, "summary": 1, "details": 1})
             .sort([("createdAt", 1), ("id", 1)]).limit(MAX_OUTBOX_PER_SYNC))
    return [{"id": d["id"], "kind": d.get("kind", "trigger"), "dedupKey": d.get("dedupKey"),
             "severity": d.get("severity", "warning"), "summary": d.get("summary", ""),
             "details": d.get("details") or {}} async for d in found]


async def ack_delivered(db, delivered: Iterable[Any]) -> int:
    """Mark each reported message delivered. ``delivered`` entries are ``{id, ok, error?, at?}``; an entry
    for an unknown id, or for a message already marked, changes nothing. Returns how many were marked.
    Never raises: a failed acknowledgement only means the message is offered again."""
    marked = 0
    for entry in list(delivered or [])[:selfheal.MAX_EVENTS]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        ok = entry.get("ok") is True
        error = None if ok else (selfheal.clean_text(entry["error"], ERROR_MAX) if entry.get("error") else None)
        try:
            result = await _outbox(db).update_one({"id": entry["id"][:64], "deliveredAt": None},
                                                  {"$set": {"deliveredAt": _now(), "ok": ok, "error": error}})
        except Exception as exc:
            logger.warning("autonomous_ops: delivery of an on-call message was not recorded: %s", type(exc).__name__)
            continue
        marked += result.modified_count
    return marked


# ---------------------------------------------------------------- test alert

def _view(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return None
    return {"id": doc["id"], "requestedAt": _iso(doc.get("requestedAt")),
            "requestedBy": (doc.get("requestedBy") or {}).get("name"), "state": doc.get("state"),
            "sentAt": _iso(doc.get("sentAt")), "error": doc.get("error")}


async def _expire_stale(db, now: datetime) -> None:
    await _requests(db).update_many(
        {"state": "pending", "requestedAt": {"$lt": now - TEST_PENDING_MAX}},
        {"$set": {"state": "failed", "error": TEST_NO_ANSWER, "sentAt": None}})


async def request_test(db, actor: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """The pending test request, created when none is pending. ``actor`` is ``{username, display, ...}``.
    A second call while one is pending returns the same request."""
    now = (now or _now()).replace(microsecond=0)        # MongoDB keeps milliseconds; the answer matches the stored value
    await _expire_stale(db, now)
    for _ in range(3):
        pending = await _requests(db).find_one({"state": "pending"}, {"_id": 0})
        if pending:
            return pending
        doc = {"id": "TR-" + uuid.uuid4().hex, "requestedAt": now,
               "requestedBy": {"id": selfheal.clean_text(actor.get("username") or "unknown", 128),
                               "name": selfheal.clean_text(actor.get("display") or actor.get("username") or "unknown", 128)},
               "state": "pending", "sentAt": None, "error": None}
        try:
            await _requests(db).insert_one(dict(doc))
            return doc
        except DuplicateKeyError:           # another click won the race; read its request
            continue
    raise RuntimeError("test request could not be created")


async def pending_test(db, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """The sync response's ``testRequest`` ``{id, requestedAt}``, or None. A request nobody picked up
    for ``TEST_PENDING_MAX`` is closed as failed instead of handed out."""
    now = now or _now()
    await _expire_stale(db, now)
    doc = await _requests(db).find_one({"state": "pending"}, {"_id": 0, "id": 1, "requestedAt": 1})
    return {"id": doc["id"], "requestedAt": _iso(doc["requestedAt"])} if doc else None


async def record_test_result(db, result: Any, host: Optional[str]) -> bool:
    """The watchdog's ``testResult`` ``{id, ok, error?, at?}``: close the pending request as delivered or
    failed (once) and write one ``test_alert`` platform-health row naming the requester. Returns True
    when this call closed a request. Never raises."""
    if not isinstance(result, dict) or not isinstance(result.get("id"), str):
        return False
    ok = result.get("ok") is True
    error = None if ok else (selfheal.clean_text(result["error"], ERROR_MAX) if result.get("error") else None)
    now = _now()
    sent = min(selfheal._utc(result.get("at")) or now, now)
    try:
        doc = await _requests(db).find_one_and_update(
            {"id": result["id"][:64], "state": "pending"},
            {"$set": {"state": "delivered" if ok else "failed", "sentAt": sent, "error": error}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        if doc is None:
            return False
        by = doc.get("requestedBy") or {}
        params = {"requestId": doc["id"], "ok": ok, "by": by.get("name") or "unknown"}
        if error:
            params["error"] = error
        actor = {"username": by.get("id") or "unknown", "display": by.get("name") or "unknown", "tier": "platform"}
        await ledger.record_platform_health(db, "test-" + doc["id"], "test_alert", params, at=sent,
                                            host=selfheal.clean_text(host or "", selfheal.MAX_HOST) or None, actor=actor)
    except Exception as exc:
        logger.error("autonomous_ops: a test alert result was not recorded: %s", type(exc).__name__)
        return False
    return True


async def test_view(db) -> Optional[Dict[str, Any]]:
    """The latest test request ``{id, requestedAt, requestedBy, state, sentAt, error}`` or None."""
    doc = await _requests(db).find_one({}, {"_id": 0}, sort=[("requestedAt", -1)])
    return _view(doc)


def view(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A request document as the API shows it."""
    return _view(doc)
