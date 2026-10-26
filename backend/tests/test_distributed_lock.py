"""Regression tests for distributed_lock.py (DB-F08/ARCH-001, 2026-08-25
audit): a shared Mongo-upsert-based lock used by database_migrations.py's
startup migrations and scheduler.py's periodic jobs to ensure only one
replica runs a given piece of work at a time in a horizontally-scaled
deployment.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock
from pymongo.errors import DuplicateKeyError

from distributed_lock import acquire_lock, release_lock


@pytest.mark.asyncio
async def test_acquire_succeeds_when_no_existing_lock():
    db = MagicMock()
    db._db._distributed_locks.find_one_and_update = AsyncMock(return_value=None)
    token = await acquire_lock(db, "some-job")
    assert token is not None
    db._db._distributed_locks.find_one_and_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_acquire_returns_none_when_held_by_another_replica():
    """A live, unexpired lock means the upsert's insert path collides with
    the existing _id — pymongo surfaces that as DuplicateKeyError."""
    db = MagicMock()
    db._db._distributed_locks.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError("dup"))
    token = await acquire_lock(db, "some-job")
    assert token is None


@pytest.mark.asyncio
async def test_release_filters_by_own_token():
    """Must never delete a lock some other replica has since (re)acquired
    — only ever delete the exact token we were holding."""
    db = MagicMock()
    db._db._distributed_locks.delete_one = AsyncMock()
    await release_lock(db, "some-job", "my-token")
    db._db._distributed_locks.delete_one.assert_awaited_once_with(
        {"_id": "some-job", "token": "my-token"}
    )


@pytest.mark.asyncio
async def test_acquire_passes_custom_ttl_into_the_expiry_filter():
    db = MagicMock()
    db._db._distributed_locks.find_one_and_update = AsyncMock(return_value=None)
    await acquire_lock(db, "some-job", ttl_seconds=55)
    args, kwargs = db._db._distributed_locks.find_one_and_update.call_args
    filter_arg, update_arg = args[0], args[1]
    assert filter_arg["_id"] == "some-job"
    assert "expiresAt" in update_arg["$set"]


# --- GATE-11 (81-03): lock renewal, proven against a real MongoDB ----------------------
# Self-contained: a throwaway omni_test_* database, wrapped so the lock helpers' `db._db`
# access works. Skips when no MongoDB is reachable.
import asyncio as _asyncio
from types import SimpleNamespace as _NS

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


def _real_db(mongo_db):
    return _NS(_db=mongo_db)


@pytest.mark.asyncio
async def test_renew_extends_a_held_lock_and_fails_once_it_is_lost(mongo_db):
    from distributed_lock import acquire_lock, renew_lock

    db = _real_db(mongo_db)
    token = await acquire_lock(db, "renew-job", ttl_seconds=1)
    assert token
    before = (await mongo_db["_distributed_locks"].find_one({"_id": "renew-job"}))["expiresAt"]
    assert await renew_lock(db, "renew-job", token, ttl_seconds=30) is True
    after = (await mongo_db["_distributed_locks"].find_one({"_id": "renew-job"}))["expiresAt"]
    assert after > before

    # A different token never renews someone else's lock.
    assert await renew_lock(db, "renew-job", "not-the-token", ttl_seconds=30) is False

    # Let a fresh lock expire, let another holder take it: the old token is out.
    token_b = await acquire_lock(db, "lost-job", ttl_seconds=1)
    await _asyncio.sleep(1.2)
    token_c = await acquire_lock(db, "lost-job", ttl_seconds=30)
    assert token_c and token_c != token_b
    assert await renew_lock(db, "lost-job", token_b, ttl_seconds=30) is False
    assert await renew_lock(db, "lost-job", token_c, ttl_seconds=30) is True


@pytest.mark.asyncio
async def test_renew_does_not_resurrect_an_expired_lock(mongo_db):
    from distributed_lock import acquire_lock, renew_lock

    db = _real_db(mongo_db)
    token = await acquire_lock(db, "expired-job", ttl_seconds=1)
    await _asyncio.sleep(1.2)
    assert await renew_lock(db, "expired-job", token, ttl_seconds=30) is False


@pytest.mark.asyncio
async def test_lock_with_renewal_holds_past_the_ttl_then_releases(mongo_db):
    from distributed_lock import acquire_lock, lock_with_renewal

    db = _real_db(mongo_db)
    async with lock_with_renewal(db, "held-job", ttl_seconds=1, renew_every=0.3) as handle:
        assert handle.acquired is True and handle.token and handle.lost is False
        for _ in range(6):  # 3 seconds, three times the TTL
            await _asyncio.sleep(0.5)
            assert await acquire_lock(db, "held-job", ttl_seconds=1) is None
        assert handle.lost is False
    # Released on exit: immediately acquirable again.
    assert await acquire_lock(db, "held-job", ttl_seconds=5)


@pytest.mark.asyncio
async def test_without_renewal_a_short_lock_is_reacquirable_after_expiry(mongo_db):
    from distributed_lock import acquire_lock

    db = _real_db(mongo_db)
    assert await acquire_lock(db, "plain-job", ttl_seconds=1)
    assert await acquire_lock(db, "plain-job", ttl_seconds=1) is None
    await _asyncio.sleep(1.2)
    assert await acquire_lock(db, "plain-job", ttl_seconds=1)


@pytest.mark.asyncio
async def test_lock_with_renewal_reports_not_acquired_when_held_elsewhere(mongo_db):
    from distributed_lock import acquire_lock, lock_with_renewal

    db = _real_db(mongo_db)
    assert await acquire_lock(db, "busy-job", ttl_seconds=30)
    async with lock_with_renewal(db, "busy-job", ttl_seconds=30, renew_every=0.3) as handle:
        assert handle.acquired is False and handle.token is None
    # The other holder's lock is untouched by our exit.
    assert await acquire_lock(db, "busy-job", ttl_seconds=30) is None


@pytest.mark.asyncio
async def test_lock_with_renewal_flags_lost_when_the_lock_document_vanishes(mongo_db):
    from distributed_lock import lock_with_renewal

    db = _real_db(mongo_db)
    async with lock_with_renewal(db, "vanish-job", ttl_seconds=2, renew_every=0.2) as handle:
        assert handle.acquired is True and handle.lost is False
        await mongo_db["_distributed_locks"].delete_one({"_id": "vanish-job"})
        for _ in range(20):
            if handle.lost:
                break
            await _asyncio.sleep(0.1)
        assert handle.lost is True
