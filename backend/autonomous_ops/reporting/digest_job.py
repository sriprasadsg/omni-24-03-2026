"""The 07:00 UTC digest loop (Phase 86, ACTV-04, D-02).

Wakes every WAKE_EVERY seconds. From 07:00 UTC on it gives every ticked organization (the platform organization is
never ticked) its digest for the day, once: the unique (tenantId, day) claim in ``digest.send_for_tenant`` is the
guard, the distributed lock only keeps parallel workers from doing the same work. A stop does not suppress the
digest (it reports, it does not act). There is no catch-up beyond the same UTC day.
"""
import asyncio
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, Optional

from autonomous_ops import sweep
from autonomous_ops.scope import raw

from . import DIGEST_HOUR_UTC, DIGESTS, digest

logger = logging.getLogger(__name__)

LOCK_NAME = "autonomous_ops_digest"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
WAKE_EVERY = 300                # seconds between checks of the schedule
STARTUP_DELAY = 120             # let the backend settle before the first check

_sleep = asyncio.sleep          # indirection so tests can observe and speed up the pauses
_indexes_ready_once = False     # the indexes were made (or found) by this process


def _utc(now: datetime) -> datetime:
    return (now if now.tzinfo else now.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def due(now: datetime) -> bool:
    """True from 07:00:00 UTC on, false at 06:59:59."""
    return _utc(now).hour >= DIGEST_HOUR_UTC


async def _indexes_ready(db) -> bool:
    """Make the claim index once per process (migration 035 may not have run yet). Without it the once-a-day guard
    does not exist, so a failure skips the pass instead of running unprotected."""
    global _indexes_ready_once
    if _indexes_ready_once:
        return True
    try:
        await digest.ensure_indexes(db)
    except Exception as exc:
        logger.error("autonomous_ops digest: pass skipped, its claim index could not be made: %s", exc)
        return False
    _indexes_ready_once = True
    return True


async def run_once(db, *, now: Optional[datetime] = None) -> Optional[Dict[str, int]]:
    """One pass under the single-runner lock: None before 07:00 UTC, when another worker holds the lock or when the
    index is missing; else {sent, quiet, skipped, failed} over the ticked organizations not yet claimed today."""
    import distributed_lock
    now = _utc(now or datetime.now(timezone.utc))
    if not due(now):
        return None
    day = now.date().isoformat()
    lock_db = SimpleNamespace(_db=raw(db))                  # distributed_lock reads db._db
    async with distributed_lock.lock_with_renewal(lock_db, LOCK_NAME, ttl_seconds=LOCK_TTL_SECONDS,
                                                  renew_every=LOCK_RENEW_EVERY) as handle:
        if not handle.acquired or not await _indexes_ready(db):
            return None
        claimed = set(await raw(db)[DIGESTS].distinct("tenantId", {"day": day}))
        counts = {"sent": 0, "quiet": 0, "skipped": 0, "failed": 0}
        for tenant_id in await sweep._ticked_tenants(db):
            if handle.lost:
                break
            if tenant_id in claimed:
                continue
            try:
                outcome = await digest.send_for_tenant(db, tenant_id, day, now)
            except asyncio.CancelledError:
                raise
            except Exception as exc:                          # one organization never stops the others
                logger.error("autonomous_ops digest: %s failed: %s", tenant_id, type(exc).__name__)
                counts["failed"] += 1
                continue
            counts["skipped" if outcome in ("already_claimed", "skipped") else outcome] += 1
        return counts


async def digest_loop() -> None:
    """Wake every WAKE_EVERY seconds and run the digest pass. A failing pass is logged and the loop goes on."""
    from database import get_database
    await _sleep(STARTUP_DELAY)
    logger.info("autonomous_ops digest loop started")
    while True:
        try:
            counts = await run_once(get_database())
            if counts and (counts["sent"] or counts["failed"]):
                logger.info("autonomous_ops digest: %s", counts)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("autonomous_ops digest: pass failed: %s", exc)
        await _sleep(WAKE_EVERY)
