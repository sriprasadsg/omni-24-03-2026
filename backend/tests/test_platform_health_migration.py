"""Migration 025: platform_health indexes (Phase 82, plan 82-01). Idempotent, like migration 024.

Real-Mongo cases use the throwaway database from tests/_mongo_test_db.py and skip when no server
is reachable.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-platform-health-migration")

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

migration = importlib.import_module("migrations.025_platform_health")


async def _indexes(db):
    return await db.platform_health.index_information()


async def test_up_creates_the_platform_health_indexes(mongo_db):
    await migration.up(mongo_db)
    info = await _indexes(mongo_db)
    assert "last_seen" in info and info["last_seen"]["key"] == [("lastSeenAt", 1)]


async def test_up_twice_leaves_the_same_index_set(mongo_db):
    await migration.up(mongo_db)
    first = await _indexes(mongo_db)
    await migration.up(mongo_db)
    assert await _indexes(mongo_db) == first


async def test_up_does_not_touch_stored_heartbeat_documents(mongo_db):
    await mongo_db.platform_health.insert_one({"_id": "heartbeat", "lastSeenAt": 1, "firstSeenAt": 1})
    await migration.up(mongo_db)
    assert await mongo_db.platform_health.find_one({"_id": "heartbeat"}) == {
        "_id": "heartbeat", "lastSeenAt": 1, "firstSeenAt": 1}


def test_migration_describes_itself():
    assert migration.DESCRIPTION and hasattr(migration, "up")
