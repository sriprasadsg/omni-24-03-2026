"""The one scheduled retention job (phase 82, HEAL-06, D-15).

Per tenant and per data type of ``retention_gate.RETENTION_TYPES`` the job either counts what
would be deleted (first run, shortened period: D-18, D-19) or deletes in bounded batches
(confirmed, adopted). Every filter names the tenant through the type's stored tenant field on the
raw Mongo handle, never the tenant wrapper.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from bson import ObjectId

import retention_gate as gate
from autonomous_ops.scope import raw
from retention_gate import RetentionType

logger = logging.getLogger(__name__)

COUNT_MAX_TIME_MS = 30000

_sleep = asyncio.sleep          # indirection so tests can observe and speed up the pauses


def _env_number(name: str, default, cast):
    try:
        value = cast(os.environ.get(name, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


BATCH_SIZE = _env_number("RETENTION_BATCH_SIZE", 500, int)
PAUSE_SECONDS = _env_number("RETENTION_BATCH_PAUSE_SECONDS", 0.5, float)
RUN_MAX_MINUTES = _env_number("RETENTION_RUN_MAX_MINUTES", 60, int)


def cutoff_filter(rtype: RetentionType, tenant_id: str, days: int, now: datetime) -> dict:
    """The tenant-scoped filter for records strictly older than ``days`` at ``now`` (UTC).

    The cutoff is rendered the way the collection stores its time: an ISO string (``isoformat()``
    of an aware UTC datetime, as the writers do), a UTC datetime, or an ObjectId (second
    precision). ``$lt`` is strict, so a record exactly ``days`` old is kept.
    """
    cutoff = now - timedelta(days=int(days))
    if rtype.time_kind == "iso":
        clause = {rtype.time_field: {"$lt": cutoff.isoformat()}}
    elif rtype.time_kind == "date":
        clause = {rtype.time_field: {"$lt": cutoff}}
    elif rtype.time_kind == "objectid":
        clause = {"_id": {"$lt": ObjectId.from_datetime(cutoff)}}
    else:
        raise ValueError(f"unknown time kind {rtype.time_kind!r}")
    return {rtype.tenant_field: tenant_id, **clause}


async def count_type(db, rtype: RetentionType, tenant_id: str, days: int, now: datetime) -> int:
    return await raw(db)[rtype.collection].count_documents(
        cutoff_filter(rtype, tenant_id, days, now), maxTimeMS=COUNT_MAX_TIME_MS)


async def _record_count(db, tenant_id: str, rtype: RetentionType, days: int, now: datetime) -> Optional[int]:
    """Count one (tenant, type); a failure is stored on that row and never raised."""
    try:
        count, error = await count_type(db, rtype, tenant_id, days, now), None
    except Exception as exc:  # a timeout or a driver error must not stop the other rows
        count, error = None, f"{type(exc).__name__}: {exc}"[:300]
        logger.warning("retention: counting %s for %s failed: %s", rtype.id, tenant_id, error)
    await raw(db)[gate.COUNTS].update_one(
        {"tenantId": tenant_id, "type": rtype.id},
        {"$set": {"tenantId": tenant_id, "type": rtype.id, "days": days, "count": count,
                  "countedAt": now, "error": error}}, upsert=True)
    return count


async def delete_type(db, rtype: RetentionType, tenant_id: str, days: int, now: datetime, *,
                      lost: Optional[Callable[[], bool]] = None, deadline: Optional[float] = None,
                      sleep: Optional[Callable] = None) -> Dict:
    """Delete one tenant's records of one type older than ``days`` in bounded batches.

    Each pass finds at most BATCH_SIZE ``_id`` values (ascending, tenant-scoped), deletes exactly
    those ids, pauses PAUSE_SECONDS and repeats. It stops on an empty or short batch, on a lost lock
    or when ``deadline`` (a ``time.monotonic()`` value) is reached, reporting ``stoppedEarly``.
    """
    if rtype.collection in gate.NEVER_DELETED:
        raise RuntimeError(f"retention must never delete from {rtype.collection}")
    sleep = sleep or _sleep
    coll = raw(db)[rtype.collection]
    flt = cutoff_filter(rtype, tenant_id, days, now)
    deleted, stopped = 0, False
    while True:
        if (lost is not None and lost()) or (deadline is not None and time.monotonic() >= deadline):
            stopped = True
            break
        batch = BATCH_SIZE
        ids = [d["_id"] async for d in coll.find(flt, {"_id": 1}).sort("_id", 1).limit(batch)]
        if not ids:
            break
        result = await coll.delete_many({"_id": {"$in": ids}, rtype.tenant_field: tenant_id})
        deleted += result.deleted_count
        if len(ids) < batch:
            break
        await sleep(PAUSE_SECONDS)
    return {"deleted": deleted, "stoppedEarly": stopped}


async def run_tenant(db, tenant_id: str, *, now: datetime, lost: Optional[Callable[[], bool]] = None,
                     deadline: Optional[float] = None, trigger: str = "scheduled") -> Dict:
    """One tenant: evaluate the gate per type, then count (first run, shortened) or delete
    (confirmed, adopted). A shortened period only sends that tenant's data type back to counting."""
    policies = await gate.load_policy_days(db, tenant_id)
    global_at = await gate.global_confirmed_at(db)
    summary = {"tenantId": tenant_id, "counted": 0, "deleted": 0, "types": {}, "stoppedEarly": False}
    for rtype in gate.RETENTION_TYPES:
        if (lost is not None and lost()) or (deadline is not None and time.monotonic() >= deadline):
            summary["stoppedEarly"] = True
            break
        days = gate.effective_days(policies, rtype)
        row = await gate.mark_seen(db, tenant_id, rtype.id, now)
        state = gate.gate_state(days, row.get("confirmedDays"), global_at, row.get("firstSeenAt"))
        if state in ("confirmed", "adopt"):
            try:
                result = await delete_type(db, rtype, tenant_id, days, now, lost=lost, deadline=deadline)
            except Exception as exc:
                logger.error("retention: deleting %s for %s failed: %s", rtype.id, tenant_id, exc)
                summary["types"][rtype.id] = {"state": state, "days": days, "error": str(exc)[:300]}
                continue
            summary["deleted"] += result["deleted"]
            summary["stoppedEarly"] = summary["stoppedEarly"] or result["stoppedEarly"]
            summary["types"][rtype.id] = {"state": state, "days": days, **result}
            # a lengthened period is adopted here, so a later shortening compares against it
            await gate.set_confirmed_days(db, tenant_id, rtype.id, days, now)
            if result["deleted"]:
                logger.info("retention: %s/%s deleted %d record(s) older than %d day(s)",
                            tenant_id, rtype.id, result["deleted"], days)
        else:
            count = await _record_count(db, tenant_id, rtype, days, now)
            summary["counted"] += count or 0
            summary["types"][rtype.id] = {"state": state, "days": days, "count": count}
    return summary


async def run_all(db, *, now: Optional[datetime] = None, lost: Optional[Callable[[], bool]] = None,
                  trigger: str = "scheduled") -> Dict:
    """Every tenant, in ascending id order, inside one wall-clock budget; one summary per run."""
    now = now or datetime.now(timezone.utc)
    rdb = raw(db)
    deadline = time.monotonic() + RUN_MAX_MINUTES * 60
    summary = {"startedAt": now, "trigger": trigger, "counted": 0, "deleted": 0, "tenants": 0,
               "stoppedEarly": False}
    async for tenant in rdb.tenants.find({}, {"_id": 0, "id": 1}).sort("id", 1):
        tenant_id = tenant.get("id")
        if not tenant_id:
            continue
        if (lost is not None and lost()) or time.monotonic() >= deadline:
            summary["stoppedEarly"] = True
            break
        result = await run_tenant(db, tenant_id, now=now, lost=lost, deadline=deadline, trigger=trigger)
        summary["tenants"] += 1
        summary["counted"] += result["counted"]
        summary["deleted"] += result["deleted"]
        summary["stoppedEarly"] = summary["stoppedEarly"] or result["stoppedEarly"]
    summary["finishedAt"] = datetime.now(timezone.utc)
    await rdb[gate.RUNS].insert_one(dict(summary))
    return summary
