"""Incidents (Phase 83, RESP-09 / D-16 / D-24): the alerts on one host belong to one incident until an hour
passes with nothing new.

* ``attach`` puts one piece of new evidence on the host's open incident when that incident saw evidence
  less than ``QUIET_GAP`` before it; otherwise it closes the open incident and opens a new one. The edge is
  exact: evidence 60 minutes after ``lastAlertAt`` opens a new incident, 59 minutes extends the old one.
  ``lastAlertAt`` only moves forward (``$max``) and only on EVIDENCE time, never on the process clock, so
  evidence that arrives out of order attaches without moving it back. ``alertCount`` counts evidence
  items; the caller passes only evidence that was first seen now (``signals.observe``'s ``new_evidence``),
  so a finding seen on ten sweep cycles counts once.
* Every field lives in Mongo, and a unique partial index allows one open incident per host, so a backend
  restart neither splits nor loses an incident and two racing attaches end with one (the loser of the
  insert reads the winner and attaches to it).
* ``claim_isolate`` is the compare-and-set that lets an incident propose isolating its host at most once
  (D-24). Nothing here dispatches anything.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .scope import raw

logger = logging.getLogger(__name__)

COLLECTION = "autonomy_incidents"
QUIET_GAP = timedelta(hours=1)                  # D-16
_TRIES = 4                                      # a race on opening settles within a retry or two


def _coll(db):
    return getattr(raw(db), COLLECTION)


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


def _ms(value: datetime) -> datetime:
    value = _aware(value)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)       # BSON datetimes are milliseconds


def _normalize(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if doc is None:
        return None
    doc.pop("_id", None)
    return {k: _aware(v) for k, v in doc.items()}


async def ensure_indexes(db) -> None:
    """One open incident per host (unique, partial on ``closed`` false), the lookup by last alert, and the
    ledger lookup by incident id. Re-running with the same definitions changes nothing."""
    await _coll(db).create_index([("tenantId", 1), ("agentId", 1)], unique=True,
                                 partialFilterExpression={"closed": False}, name="incident_one_open")
    await _coll(db).create_index([("tenantId", 1), ("closed", 1), ("lastAlertAt", -1)], name="incident_last_alert")
    await raw(db).autonomy_actions.create_index(
        [("tenantId", 1), ("reason.inputs.incidentId", 1), ("state", 1)], name="action_by_incident")


async def _extend(db, tenant_id: str, agent_id: str, at: datetime, count: int) -> Optional[Dict[str, Any]]:
    """Attach to the open incident when it saw evidence less than the quiet gap before ``at``."""
    return _normalize(await _coll(db).find_one_and_update(
        {"tenantId": tenant_id, "agentId": agent_id, "closed": False, "lastAlertAt": {"$gt": at - QUIET_GAP}},
        {"$max": {"lastAlertAt": at}, "$min": {"startedAt": at}, "$inc": {"alertCount": count}},
        return_document=ReturnDocument.AFTER))


async def attach(db, tenant_id: str, agent_id: str, at: datetime, *, count: int = 1) -> Dict[str, Any]:
    """Put ``count`` pieces of evidence dated ``at`` on the host's incident and return it. Raises only
    when the database does, or when opening keeps losing races (it does not in practice)."""
    at = _ms(at)
    for _ in range(_TRIES):
        found = await _extend(db, tenant_id, agent_id, at, count)
        if found is not None:
            return found
        # Quiet for an hour (or none yet): close what is open and start a new one.
        await _coll(db).update_many(
            {"tenantId": tenant_id, "agentId": agent_id, "closed": False, "lastAlertAt": {"$lte": at - QUIET_GAP}},
            {"$set": {"closed": True, "closedAt": at}})
        doc = {"id": f"INC-{uuid.uuid4().hex[:12]}", "tenantId": tenant_id, "agentId": agent_id, "startedAt": at,
               "lastAlertAt": at, "alertCount": count, "closed": False, "isolateProposed": False}
        try:
            await _coll(db).insert_one(dict(doc))
        except DuplicateKeyError:
            continue                                # another writer opened one first: read it and attach
        return _normalize(doc)
    raise RuntimeError(f"incident for {agent_id} could not be opened")


async def get_open(db, tenant_id: str, agent_id: str, now: datetime) -> Optional[Dict[str, Any]]:
    """The host's open incident, only while it has not been quiet for ``QUIET_GAP`` at ``now``."""
    return _normalize(await _coll(db).find_one(
        {"tenantId": tenant_id, "agentId": agent_id, "closed": False, "lastAlertAt": {"$gt": _ms(now) - QUIET_GAP}}))


async def current(db, tenant_id: str, agent_id: str, at: datetime) -> Dict[str, Any]:
    """The incident a decision on this host belongs to: the host's open incident, however long ago its last
    evidence was (closing is lazy and happens only when new evidence arrives), else a new one dated ``at``
    (the finding's own evidence time) holding no evidence of its own."""
    found = _normalize(await _coll(db).find_one({"tenantId": tenant_id, "agentId": agent_id, "closed": False}))
    return found if found is not None else await attach(db, tenant_id, agent_id, at, count=0)


async def claim_isolate(db, tenant_id: str, incident_id: str) -> bool:
    """False to true, once: True only for the caller that made the change (D-24: at most one isolate line
    per incident)."""
    done = await _coll(db).update_one({"id": incident_id, "tenantId": tenant_id, "isolateProposed": False},
                                      {"$set": {"isolateProposed": True}})
    return done.modified_count == 1


async def release_isolate(db, tenant_id: str, incident_id: str) -> None:
    """Give the claim back when the gate refused the line without recording it."""
    await _coll(db).update_one({"id": incident_id, "tenantId": tenant_id}, {"$set": {"isolateProposed": False}})
