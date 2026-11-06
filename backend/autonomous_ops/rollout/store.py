"""Collections, indexes and small writers for staged patch rollouts (PTCH-07).

Every read and write goes through the raw Mongo handle with an explicit tenantId; the ambient tenant
ContextVar is never used. The host claim is a database guarantee: a unique partial index on
(tenantId, agentId) where ``active`` is true, so two active rollouts can never hold the same computer
whatever the code does (research Pattern 7). Migration 031 (plan 84-22) calls ``ensure_indexes`` too.

Times: the driver hands back naive datetimes and agents post ISO strings. ``aware`` and ``parse_time``
turn every one of them into an aware UTC datetime before it is compared (research Pitfall 4).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pymongo.errors import BulkWriteError

from ..scope import raw

logger = logging.getLogger(__name__)

HOST_INDEX = "one_active_rollout_per_host"
DUPLICATE_KEY = 11000


def rollouts(db):
    return raw(db).patch_rollouts


def hosts(db):
    return raw(db).patch_rollout_hosts


def settings_coll(db):
    return raw(db).patch_rollout_settings


def maintenance_settings(db):
    return raw(db).maintenance_settings


def aware(value: Any) -> Any:
    """A naive datetime is read as UTC; anything else is returned unchanged."""
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


def parse_time(value: Any) -> Optional[datetime]:
    """An aware UTC datetime from a datetime or an ISO string, else None."""
    if isinstance(value, datetime):
        return aware(value).astimezone(timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return aware(parsed).astimezone(timezone.utc)
    return None


def normalise(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Drop ``_id`` and make every datetime in the document (and one level of nesting, plus the ring
    snapshots) aware."""
    if doc is None:
        return None
    doc.pop("_id", None)
    for key, value in list(doc.items()):
        if isinstance(value, datetime):
            doc[key] = aware(value)
        elif isinstance(value, dict):
            normalise_inner(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    normalise_inner(item)
    return doc


def normalise_inner(doc: Dict[str, Any]) -> None:
    for key, value in list(doc.items()):
        if isinstance(value, datetime):
            doc[key] = aware(value)


async def ensure_indexes(db) -> None:
    """The unique host claim and the lookups the controller makes. Safe to call again."""
    claims = hosts(db)
    await claims.create_index([("tenantId", 1), ("agentId", 1)], unique=True, name=HOST_INDEX,
                              partialFilterExpression={"active": True})
    await claims.create_index([("tenantId", 1), ("rolloutId", 1), ("ring", 1)], name="tenant_rollout_ring")
    await rollouts(db).create_index([("tenantId", 1), ("status", 1)], name="tenant_status")
    await rollouts(db).create_index("id", unique=True, name="id_unique")


async def claim_hosts(db, tenant_id: str, rollout_id: str,
                      docs: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """Claim computers for a rollout in one unordered insert. Returns (claimed agent ids, agent ids left
    out because another active rollout already holds them). Any other write error propagates."""
    if not docs:
        return [], []
    prepared = [{**doc, "tenantId": tenant_id, "rolloutId": rollout_id, "active": True} for doc in docs]
    left_out: List[str] = []
    try:
        await hosts(db).insert_many(prepared, ordered=False)
    except BulkWriteError as exc:
        errors = (exc.details or {}).get("writeErrors") or []
        if any(e.get("code") != DUPLICATE_KEY for e in errors):
            raise
        left_out = [e["op"]["agentId"] for e in errors]
    lost = set(left_out)
    return [d["agentId"] for d in prepared if d["agentId"] not in lost], left_out


async def release(db, tenant_id: str, rollout_id: str, agent_ids: Optional[Iterable[str]] = None) -> int:
    """Let go of the rollout's claims (all of them, or only ``agent_ids``). Returns how many were released."""
    flt: Dict[str, Any] = {"tenantId": tenant_id, "rolloutId": rollout_id, "active": True}
    if agent_ids is not None:
        flt["agentId"] = {"$in": list(agent_ids)}
    result = await hosts(db).update_many(flt, {"$set": {"active": False, "releasedAt": datetime.now(timezone.utc)}})
    return result.modified_count


async def discard(db, tenant_id: str, rollout_id: str) -> None:
    """Remove a rollout that never started, its host documents (claims) included. Used by Start when it loses a
    race or fails part way, so a failed Start leaves nothing behind."""
    await hosts(db).delete_many({"tenantId": tenant_id, "rolloutId": rollout_id})
    await rollouts(db).delete_one({"id": rollout_id, "tenantId": tenant_id})


async def host_docs(db, tenant_id: str, rollout_id: str) -> List[Dict[str, Any]]:
    """The rollout's host documents in a stable order (ring, hostname, agent id)."""
    found = hosts(db).find({"tenantId": tenant_id, "rolloutId": rollout_id})
    docs = [normalise(d) async for d in found]
    return sorted(docs, key=lambda d: (d.get("ring", 0), str(d.get("hostname") or "").casefold(), d.get("agentId", "")))


async def set_host(db, tenant_id: str, rollout_id: str, agent_id: str, fields: Dict[str, Any]) -> None:
    await hosts(db).update_one({"tenantId": tenant_id, "rolloutId": rollout_id, "agentId": agent_id},
                               {"$set": fields})


async def set_ring(db, tenant_id: str, rollout: Dict[str, Any], index: int, fields: Dict[str, Any]) -> None:
    """Set fields on one ring of the rollout, in the database and on the in-memory document."""
    await rollouts(db).update_one({"id": rollout["id"], "tenantId": tenant_id},
                                  {"$set": {f"rings.{index}.{k}": v for k, v in fields.items()}})
    rollout["rings"][index].update(fields)


async def set_rollout(db, tenant_id: str, rollout: Dict[str, Any], fields: Dict[str, Any]) -> None:
    await rollouts(db).update_one({"id": rollout["id"], "tenantId": tenant_id}, {"$set": fields})
    rollout.update(fields)


async def active_rollouts(db, tenant_id: str, statuses: Iterable[str]) -> List[Dict[str, Any]]:
    found = rollouts(db).find({"tenantId": tenant_id, "status": {"$in": list(statuses)}}).sort("createdAt", 1)
    return [normalise(d) async for d in found]


async def tenants_with_rollouts(db, statuses: Iterable[str]) -> List[str]:
    ids = await rollouts(db).distinct("tenantId", {"status": {"$in": list(statuses)}})
    return sorted(t for t in ids if isinstance(t, str) and t)


# A finished rollout the controller still looks after: a completed one that has not closed yet and tracks computers
# it never reached (``closesAt``), and a cancelled one whose revert is still running (``revertOpen``).
TAIL_FILTER: Dict[str, Any] = {"$or": [
    {"status": "completed", "closesAt": {"$ne": None}, "closedAt": None},
    {"status": "cancelled", "revertOpen": True}]}


async def tail_rollouts(db, tenant_id: str) -> List[Dict[str, Any]]:
    found = rollouts(db).find({"tenantId": tenant_id, **TAIL_FILTER}).sort("createdAt", 1)
    return [normalise(d) async for d in found]


async def tenants_with_tails(db) -> List[str]:
    ids = await rollouts(db).distinct("tenantId", TAIL_FILTER)
    return sorted(t for t in ids if isinstance(t, str) and t)
