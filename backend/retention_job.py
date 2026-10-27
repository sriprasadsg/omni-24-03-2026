"""The one scheduled retention job (phase 82, HEAL-06, D-15).

Per tenant and per data type of ``retention_gate.RETENTION_TYPES`` the job either counts what
would be deleted (first run, shortened period: D-18, D-19) or deletes in bounded batches
(confirmed, adopted). Every filter names the tenant through the type's stored tenant field on the
raw Mongo handle, never the tenant wrapper.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from bson import ObjectId

import retention_gate as gate
from autonomous_ops.scope import raw
from retention_gate import RetentionType

logger = logging.getLogger(__name__)

COUNT_MAX_TIME_MS = 30000


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


async def run_tenant(db, tenant_id: str, *, now: datetime, lost: Optional[Callable[[], bool]] = None,
                     deadline: Optional[float] = None, trigger: str = "scheduled") -> Dict:
    """One tenant: evaluate the gate per type, then count (first run) for each."""
    policies = await gate.load_policy_days(db, tenant_id)
    summary = {"tenantId": tenant_id, "counted": 0, "deleted": 0, "types": {}, "stoppedEarly": False}
    for rtype in gate.RETENTION_TYPES:
        days = gate.effective_days(policies, rtype)
        await gate.mark_seen(db, tenant_id, rtype.id, now)
        count = await _record_count(db, tenant_id, rtype, days, now)
        summary["counted"] += count or 0
        summary["types"][rtype.id] = {"days": days, "count": count}
    return summary


async def run_all(db, *, now: Optional[datetime] = None, lost: Optional[Callable[[], bool]] = None,
                  trigger: str = "scheduled") -> Dict:
    """Every tenant, in ascending id order; one summary document per run."""
    now = now or datetime.now(timezone.utc)
    rdb = raw(db)
    summary = {"startedAt": now, "trigger": trigger, "counted": 0, "deleted": 0, "tenants": 0,
               "stoppedEarly": False}
    async for tenant in rdb.tenants.find({}, {"_id": 0, "id": 1}).sort("id", 1):
        tenant_id = tenant.get("id")
        if not tenant_id:
            continue
        result = await run_tenant(db, tenant_id, now=now, lost=lost, trigger=trigger)
        summary["tenants"] += 1
        summary["counted"] += result["counted"]
        summary["deleted"] += result["deleted"]
    summary["finishedAt"] = datetime.now(timezone.utc)
    await rdb[gate.RUNS].insert_one(dict(summary))
    return summary
