"""The decision ledger: ``autonomy_actions`` (GATE-07).

Every autonomous decision is inserted here BEFORE anything is dispatched; when the insert
fails the caller refuses the decision (``LedgerUnavailable``) and nothing is written to an
agent. Every state change goes through ``transition``, one compare-and-set
``find_one_and_update`` that has exactly one winner, and every successful change is mirrored
by an awaited ``audit_ledger.event`` so the hash-chained audit log shows the same history.
The audit mirror never raises (the ledger row is the guard, not the mirror).

Raw Mongo handle with an explicit tenantId on every filter and document; the ambient tenant
ContextVar is never used. New timestamps are timezone-aware UTC BSON datetimes. Decision
records are outside generic retention (see ``PROTECTED_COLLECTIONS``).
"""
import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import audit_ledger

from . import BUCKET_STATES, OPEN_STATES, PLATFORM_TENANT_ID, TERMINAL_STATES, health_messages
from .scope import raw

logger = logging.getLogger(__name__)

_MAX_PAGE = 200
_HEALTH_MAX_FUTURE = timedelta(seconds=60)      # a platform-health row is never dated further ahead than this
_HEALTH_MAX_PAST = timedelta(days=7)            # nor further back (a replayed spool keeps its order)
_DENIED = ("refused", "denied", "expired", "cancelled_by_stop")


class LedgerUnavailable(Exception):
    """The decision could not be written ahead; the caller must refuse and dispatch nothing."""


def _actions(db):
    return raw(db).autonomy_actions


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


def _normalize(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Datetimes come back naive from a default Motor client; make them aware (UTC)."""
    if doc is None:
        return None
    doc.pop("_id", None)
    for key, value in list(doc.items()):
        if isinstance(value, datetime):
            doc[key] = _aware(value)
        elif isinstance(value, dict):
            for k2, v2 in list(value.items()):
                value[k2] = _aware(v2)
    return doc


def _audit_actor(actor) -> Dict[str, Any]:
    if isinstance(actor, dict) and (actor.get("username") or actor.get("display")):
        name = actor.get("username") or actor.get("display")
        return {"userId": name, "email": name, "role": actor.get("tier") or "user"}
    return {"userId": "autonomous_ops", "role": "system"}


async def _mirror(db, tenant_id: str, event: str, row: Dict[str, Any], actor=None) -> None:
    """Await the audit event for a ledger change. Never raises."""
    state = row.get("state")
    outcome = "denied" if state in _DENIED else "failure" if state == "failed" else "success"
    try:
        await audit_ledger.event(
            "autonomous_ops." + event, tenant_id, actor=_audit_actor(actor), outcome=outcome, db=raw(db),
            catalogue="autonomousOps", resourceId=row.get("id"),
            ruleId=(row.get("reason") or {}).get("ruleId"), reasonCode=row.get("reasonCode"),
            autonomyCommand=row.get("command"), target=row.get("target"))
    except Exception as exc:  # the mirror must not undo a decision that is already recorded
        logger.error("autonomous_ops: audit mirror failed for %s: %s", row.get("id"), exc)


async def ensure_indexes(db) -> None:
    coll = _actions(db)
    await coll.create_index("id", unique=True, name="id_unique")
    await coll.create_index([("tenantId", 1), ("createdAt", -1), ("id", -1)], name="tenant_created")
    await coll.create_index([("tenantId", 1), ("state", 1), ("createdAt", -1)], name="tenant_state_created")
    await coll.create_index([("state", 1), ("approval.expiresAt", 1)], name="state_expiry")
    # One open decision per (tenant, dedupeKey): a terminal transition leaves the index.
    await coll.create_index(
        [("tenantId", 1), ("dedupeKey", 1)], unique=True, name="open_dedupe",
        partialFilterExpression={"state": {"$in": list(OPEN_STATES)}, "dedupeKey": {"$type": "string"}})


async def create_intent(db, row: Dict[str, Any]) -> Dict[str, Any]:
    """Insert the decision row, then mirror it into the audit chain. Raises
    ``LedgerUnavailable`` when the insert fails for any reason except a duplicate key, which
    is re-raised as ``DuplicateKeyError`` (the open-dedupe guard)."""
    if not row.get("tenantId"):
        raise LedgerUnavailable("a decision row needs a tenantId")
    now = _now()
    doc = dict(row)
    doc.setdefault("id", "AO-" + uuid.uuid4().hex)
    doc.setdefault("createdAt", now)
    doc.setdefault("updatedAt", doc["createdAt"])
    doc.setdefault("finishedAt", doc["createdAt"] if doc.get("state") in TERMINAL_STATES else None)
    try:
        await _actions(db).insert_one(doc)
    except DuplicateKeyError:
        raise
    except Exception as exc:
        raise LedgerUnavailable(f"decision could not be recorded: {exc}") from exc
    doc.pop("_id", None)
    await _mirror(db, doc["tenantId"], doc["state"], doc)
    return doc


async def transition(db, tenant_id: str, action_id: str, from_states: Iterable[str], to_state: str, *,
                     actor=None, where: Optional[Dict[str, Any]] = None, **fields: Any) -> Optional[Dict[str, Any]]:
    """Move a row from one of ``from_states`` to ``to_state`` in one atomic update. Returns the
    updated row, or None when no row matched (lost the race, wrong state or wrong tenant).
    Exactly one audit event is written per successful change."""
    flt: Dict[str, Any] = {"id": action_id, "tenantId": tenant_id, "state": {"$in": list(from_states)}}
    if where:
        flt.update(where)
    now = _now()
    sets: Dict[str, Any] = {"state": to_state, "updatedAt": now, **fields}
    if to_state in TERMINAL_STATES:
        sets.setdefault("finishedAt", now)
    doc = await _actions(db).find_one_and_update(flt, {"$set": sets}, return_document=ReturnDocument.AFTER)
    if doc is None:
        return None
    doc = _normalize(doc)
    await _mirror(db, tenant_id, to_state, doc, actor)
    return doc


async def record_control(db, tenant_id: str, event: str, *, scope: str, actor: Dict[str, Any],
                         reason: Optional[str]) -> Dict[str, Any]:
    """A stop pressed or cleared, a breaker trip, a restore: a ``control`` row (state
    "recorded"), mirrored to the audit chain. Raises ``LedgerUnavailable`` on a failed insert."""
    now = _now()
    doc = {"id": "AO-" + uuid.uuid4().hex, "tenantId": tenant_id, "kind": "control", "state": "recorded",
           "scope": scope, "controlEvent": event, "actor": dict(actor or {}), "reasonText": reason,
           "reason": {"ruleId": "control:" + event, "inputs": {}}, "reasonCode": event, "origin": "operator",
           "createdAt": now, "updatedAt": now, "finishedAt": now}
    try:
        await _actions(db).insert_one(doc)
    except Exception as exc:
        raise LedgerUnavailable(f"control event could not be recorded: {exc}") from exc
    doc.pop("_id", None)
    await _mirror(db, tenant_id, event, doc, actor)
    return doc


def _clamp_at(at, now: datetime) -> datetime:
    at = _aware(at) if isinstance(at, datetime) else now
    return max(now - _HEALTH_MAX_PAST, min(now + _HEALTH_MAX_FUTURE, at))


async def record_platform_health(db, event_id: str, kind: str, params: Optional[Dict[str, Any]], *,
                                 at: Optional[datetime], host: Optional[str],
                                 actor: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """A watchdog (or backend) health event as a ``platform_health`` row at platform scope (HEAL-07).
    The row id is ``PH-<event id>``: a second insert of the same event is a duplicate key and returns
    None (already ingested, nothing mirrored again). Never kind ``control``: that shape is what the
    tenant query includes. Any other insert error raises ``LedgerUnavailable``. The row time is the
    event time clamped to at most 60 s ahead and 7 days back."""
    params = dict(params or {})
    now = _now()
    created = _clamp_at(at, now)
    rule_id = health_messages.render(kind, params, host)["ruleId"]
    doc = {"id": "PH-" + event_id, "tenantId": PLATFORM_TENANT_ID, "kind": "platform_health", "state": "recorded",
           "healthEvent": kind, "healthParams": params, "healthChip": health_messages.chip_for(kind, params),
           "host": host, "target": params.get("target"), "actor": dict(actor) if actor else None,
           "reason": {"ruleId": rule_id, "inputs": {}}, "origin": "operator" if actor else "watchdog",
           "createdAt": created, "updatedAt": created, "finishedAt": created}
    try:
        await _actions(db).insert_one(doc)
    except DuplicateKeyError:
        return None
    except Exception as exc:
        raise LedgerUnavailable(f"platform health event could not be recorded: {exc}") from exc
    doc.pop("_id", None)
    await _mirror(db, PLATFORM_TENANT_ID, "platform_health." + kind, doc, actor)
    return doc


async def get(db, tenant_id: str, action_id: str) -> Optional[Dict[str, Any]]:
    return _normalize(await _actions(db).find_one({"id": action_id, "tenantId": tenant_id}))


def _encode_cursor(row: Dict[str, Any]) -> str:
    created = _aware(row["createdAt"]).isoformat()
    return base64.urlsafe_b64encode(f"{created}|{row['id']}".encode()).decode()


def _decode_cursor(cursor: str):
    try:
        created, row_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        return datetime.fromisoformat(created), row_id
    except Exception as exc:
        raise ValueError("invalid cursor") from exc


async def list_actions(db, tenant_id: str, *, bucket: str = "all", limit: int = 25,
                       cursor: Optional[str] = None) -> Dict[str, Any]:
    """A page of the tenant's rows, newest first (createdAt then id, both descending, so rows
    sharing a createdAt keep a stable order across pages)."""
    flt: Dict[str, Any] = {"tenantId": tenant_id}
    if bucket != "all":
        if bucket not in BUCKET_STATES:
            raise ValueError(f"unknown bucket {bucket!r}")
        flt["state"] = {"$in": list(BUCKET_STATES[bucket])}
    if cursor:
        created, row_id = _decode_cursor(cursor)
        flt["$or"] = [{"createdAt": {"$lt": created}}, {"createdAt": created, "id": {"$lt": row_id}}]
    limit = max(1, min(int(limit), _MAX_PAGE))
    found = _actions(db).find(flt, {"_id": 0}).sort([("createdAt", -1), ("id", -1)]).limit(limit + 1)
    rows = [_normalize(r) async for r in found]
    page = rows[:limit]
    return {"items": page, "nextCursor": _encode_cursor(page[-1]) if len(rows) > limit else None}


async def counts(db, tenant_id: str) -> Dict[str, int]:
    """Row counts per Activity bucket (control rows are in none of them)."""
    totals = {name: 0 for name in BUCKET_STATES}
    by_state: Dict[str, int] = {}
    async for group in _actions(db).aggregate([{"$match": {"tenantId": tenant_id}},
                                               {"$group": {"_id": "$state", "n": {"$sum": 1}}}]):
        by_state[group["_id"]] = group["n"]
    for name, states in BUCKET_STATES.items():
        totals[name] = sum(by_state.get(s, 0) for s in states)
    return totals


_AUTO_ROWS = {"autoDispatched": True, "kind": {"$ne": "control"}, "state": {"$ne": "shadow"}}


async def count_auto_since(db, tenant_id: str, since: datetime) -> int:
    """Automatic decisions created strictly after ``since`` (shadow and control rows excluded)."""
    return await _actions(db).count_documents({"tenantId": tenant_id, **_AUTO_ROWS, "createdAt": {"$gt": since}})


async def recent_finished_auto(db, tenant_id: str, n: int = 3) -> list:
    """The tenant's ``n`` most recently finished automatic rows, newest first."""
    found = _actions(db).find({"tenantId": tenant_id, **_AUTO_ROWS, "finishedAt": {"$ne": None}},
                              {"_id": 0}).sort("finishedAt", -1).limit(n)
    return [_normalize(r) async for r in found]


async def open_row(db, tenant_id: str, dedupe_key: str, states: Iterable[str] = OPEN_STATES) -> Optional[Dict[str, Any]]:
    """The row holding ``dedupe_key`` open for the tenant (at most one, the open-dedupe index), else None."""
    return _normalize(await _actions(db).find_one(
        {"tenantId": tenant_id, "dedupeKey": dedupe_key, "state": {"$in": list(states)}}))


async def refresh_suggestion(db, tenant_id: str, action_id: str, *, inputs: Dict[str, Any], expires_at: datetime,
                             touch_created: bool, now: datetime) -> bool:
    """Keep a still-seen suggestion alive: one update of its inputs, expiry and updatedAt (and createdAt
    when ``touch_created``) while it is still ``suggested``. This is no state change, so no audit event is
    written. Returns whether a row was changed."""
    sets: Dict[str, Any] = {"reason.inputs": inputs, "approval.expiresAt": expires_at, "updatedAt": now}
    if touch_created:
        sets["createdAt"] = now
    done = await _actions(db).update_one({"id": action_id, "tenantId": tenant_id, "state": "suggested"}, {"$set": sets})
    return done.modified_count == 1
