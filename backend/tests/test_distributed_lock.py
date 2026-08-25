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
