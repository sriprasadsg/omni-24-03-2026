"""Best-effort Mongo-backed distributed lock for startup/periodic work that
must run on only one replica at a time in a horizontally-scaled deployment
(DB-F08/ARCH-001, 2026-08-25 audit).

Uses the standard Mongo upsert-via-unique-index-collision pattern: a single
atomic find_one_and_update() with upsert=True, filtered on the lock being
either absent or expired. When a live (unexpired) lock already exists for
this name, the upsert's implicit insert path collides with the existing
_id's unique index and pymongo raises DuplicateKeyError — treated here as
"another replica holds it, skip this run". Self-healing via TTL: a crashed
holder's lock becomes re-acquirable automatically once it expires, no
separate crash-recovery path needed.

Uses db._db (raw, unwrapped) deliberately — this lock collection is
cross-tenant/global by nature, not something tenant isolation applies to.
"""
import asyncio
import logging
import time
import uuid as _uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

DEFAULT_LOCK_TTL_SECONDS = 300


async def acquire_lock(db, name: str, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS) -> Optional[str]:
    """Try to acquire the named lock. Returns a token to pass to
    release_lock() on success, or None if another replica currently holds
    an unexpired lock of the same name."""
    now = datetime.now(timezone.utc)
    token = str(_uuid.uuid4())
    try:
        await db._db["_distributed_locks"].find_one_and_update(
            {"_id": name, "expiresAt": {"$lt": now}},
            {"$set": {"expiresAt": now + timedelta(seconds=ttl_seconds), "token": token}},
            upsert=True,
        )
        return token
    except DuplicateKeyError:
        return None


async def release_lock(db, name: str, token: str) -> None:
    """Release promptly on completion so the next run doesn't have to wait
    out the full TTL. Filtered on our own token so we never delete a lock
    some other replica has since (re)acquired after our TTL lapsed."""
    await db._db["_distributed_locks"].delete_one({"_id": name, "token": token})


async def renew_lock(db, name: str, token: str, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS) -> bool:
    """Extend a lock we hold. Succeeds only while the lock is still held by this token
    and has not yet expired; returns False once it is lost (expired, taken by another
    replica, or deleted). An expired lock is never resurrected, because another replica
    may already have started the same work."""
    now = datetime.now(timezone.utc)
    result = await db._db["_distributed_locks"].update_one(
        {"_id": name, "token": token, "expiresAt": {"$gt": now}},
        {"$set": {"expiresAt": now + timedelta(seconds=ttl_seconds)}},
    )
    return result.matched_count == 1


@dataclass
class LockHandle:
    """Yielded by lock_with_renewal. `token` is None and `acquired` False when another
    replica holds the lock; `lost` flips to True if a renewal finds the lock gone, and the
    caller should stop its work."""
    token: Optional[str]
    acquired: bool
    lost: bool = False


@asynccontextmanager
async def lock_with_renewal(db, name: str, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
                            renew_every: Optional[float] = None):
    """Acquire `name`, keep it alive from a background task while the body runs, and
    release it by token on exit. A long sweep can thus hold a short-TTL lock: a crashed
    holder's lock still expires within `ttl_seconds` because renewals stop with it."""
    if renew_every is None:
        renew_every = max(ttl_seconds / 3.0, 0.1)
    token = await acquire_lock(db, name, ttl_seconds)
    handle = LockHandle(token=token, acquired=token is not None)
    if token is None:
        yield handle
        return

    async def _renew_loop() -> None:
        last_ok = time.monotonic()
        while True:
            await asyncio.sleep(renew_every)
            try:
                if await renew_lock(db, name, token, ttl_seconds):
                    last_ok = time.monotonic()
                    continue
                handle.lost = True
                logger.warning("[distributed_lock] lock %s lost (not renewable)", name)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[distributed_lock] renewing %s failed: %s", name, exc)
                if time.monotonic() - last_ok >= ttl_seconds:
                    handle.lost = True
                    return

    task = asyncio.create_task(_renew_loop())
    try:
        yield handle
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        try:
            await release_lock(db, name, token)
        except Exception as exc:
            logger.warning("[distributed_lock] releasing %s failed (TTL will expire it): %s", name, exc)
