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
import uuid as _uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from pymongo.errors import DuplicateKeyError

DEFAULT_LOCK_TTL_SECONDS = 300


async def acquire_lock(db, name: str, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS) -> Optional[str]:
    """Try to acquire the named lock. Returns a token to pass to
    release_lock() on success, or None if another replica currently holds
    an unexpired lock of the same name."""
    now = datetime.now(timezone.utc)
    token = str(_uuid.uuid4())
    try:
        await db._db._distributed_locks.find_one_and_update(
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
    await db._db._distributed_locks.delete_one({"_id": name, "token": token})
