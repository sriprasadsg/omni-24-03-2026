"""The rollout controller loop (Phase 84, PTCH-01 / PTCH-07): runs ``controller.tick`` by itself.

One copy at a time: ``run_once`` holds ``distributed_lock.lock_with_renewal`` on ``patch_rollout_controller``
(a second copy gets None) and passes the lock's ``lost`` signal to the tick, which stops between tenants when
the lock is gone. Nothing runs without the unique partial index ``one_active_rollout_per_host``: a missing one
is made again, and when it cannot be made (duplicate active claims already exist) the pass logs and does
nothing instead of letting a computer join a second rollout.

The state lives only in the database, so a restart of the backend resumes at the next tick from what is
stored. The tick itself is in ``controller.py`` and is read through the module, so a reload is picked up.

Raw Mongo handle with an explicit tenantId inside the tick; this module only guards and repeats it.
"""
import asyncio
import logging
import os
from datetime import datetime
from types import SimpleNamespace
from typing import Dict, Optional

from ..scope import raw
from . import LOCK_NAME, controller, store

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
_DEFAULT_INTERVAL_SEC = 60
_REQUIRED_INDEXES = (("patch_rollout_hosts", "one_active_rollout_per_host"),)


def _env_number(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _interval() -> float:
    return _env_number("PATCH_ROLLOUT_INTERVAL_SEC", _DEFAULT_INTERVAL_SEC)


async def _indexes_ready(db) -> bool:
    """A missing required index is made again (the call migration 031 makes). When that fails, for example
    because duplicate active claims already exist, the pass must not run unprotected."""
    try:
        for coll, name in _REQUIRED_INDEXES:
            if name not in await raw(db)[coll].index_information():
                await store.ensure_indexes(db)
                break
        return True
    except Exception as exc:
        logger.error("autonomous_ops: rollout pass skipped, the unique index it relies on (%s) is missing and "
                     "could not be made: %s", ", ".join(n for _, n in _REQUIRED_INDEXES), exc)
        return False


async def run_once(db, *, now: Optional[datetime] = None) -> Optional[Dict[str, int]]:
    """One tick under the single-copy lock; None when another copy holds it or when the claim index is
    missing and cannot be made."""
    import distributed_lock
    lock_db = SimpleNamespace(_db=raw(db))        # distributed_lock reads db._db
    async with distributed_lock.lock_with_renewal(lock_db, LOCK_NAME, ttl_seconds=LOCK_TTL_SECONDS,
                                                  renew_every=LOCK_RENEW_EVERY) as handle:
        if not handle.acquired:
            return None
        if not await _indexes_ready(db):
            return None
        return await controller.tick(db, now=now, lost=lambda: handle.lost)


async def rollout_loop() -> None:
    """Run a tick every PATCH_ROLLOUT_INTERVAL_SEC. A failing pass is logged and the loop goes on."""
    from database import get_database
    while True:
        try:
            counts = await run_once(get_database())
            if counts and any(v for k, v in counts.items() if k != "tenants"):
                logger.info("autonomous_ops: rollout pass %s", counts)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("autonomous_ops: rollout pass failed: %s", exc)
        await asyncio.sleep(_interval())
