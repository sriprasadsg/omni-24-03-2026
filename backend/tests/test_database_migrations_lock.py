"""Regression tests for DB-F08 (2026-08-25 audit): startup migrations in
database_migrations.py had no distributed lock, so every horizontally-scaled
replica re-scanned and re-wrote the same backlog on every restart (wasted
work growing with replica count), and seed_compliance_frameworks could spawn
duplicate concurrent child-process seeders. A Mongo-upsert-based lock (the
standard atomic acquire-via-unique-index-collision pattern) now ensures only
one replica actually runs a given migration at a time, self-healing via TTL
if the holder crashes.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock
from pymongo.errors import DuplicateKeyError

import database_migrations as dm


class _EmptyAsyncCursor:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class TestAcquireReleaseLock:

    @pytest.mark.asyncio
    async def test_acquire_succeeds_when_no_existing_lock(self):
        db = MagicMock()
        db._db._migration_locks.find_one_and_update = AsyncMock(return_value=None)
        token = await dm._acquire_migration_lock(db, "some-migration")
        assert token is not None
        db._db._migration_locks.find_one_and_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acquire_returns_none_when_held_by_another_replica(self):
        """A live, unexpired lock means the upsert's insert path collides
        with the existing _id — pymongo surfaces that as DuplicateKeyError."""
        db = MagicMock()
        db._db._migration_locks.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError("dup"))
        token = await dm._acquire_migration_lock(db, "some-migration")
        assert token is None

    @pytest.mark.asyncio
    async def test_release_filters_by_own_token(self):
        """Must never delete a lock some other replica has since
        (re)acquired — only ever delete the exact token we were holding."""
        db = MagicMock()
        db._db._migration_locks.delete_one = AsyncMock()
        await dm._release_migration_lock(db, "some-migration", "my-token")
        db._db._migration_locks.delete_one.assert_awaited_once_with(
            {"_id": "some-migration", "token": "my-token"}
        )


class TestMigrationsRespectTheLock:

    @pytest.mark.asyncio
    async def test_compliance_migration_skips_work_when_lock_not_acquired(self, monkeypatch):
        db = MagicMock()
        monkeypatch.setattr(dm, "get_database", lambda: db)
        monkeypatch.setattr(dm, "_acquire_migration_lock", AsyncMock(return_value=None))
        release_mock = AsyncMock()
        monkeypatch.setattr(dm, "_release_migration_lock", release_mock)

        await dm.migrate_compliance_tenant_ids()

        db._db.asset_compliance.find.assert_not_called()
        release_mock.assert_not_called()  # never acquired, nothing to release

    @pytest.mark.asyncio
    async def test_compliance_migration_runs_and_releases_lock_when_acquired(self, monkeypatch):
        db = MagicMock()
        monkeypatch.setattr(dm, "get_database", lambda: db)
        monkeypatch.setattr(dm, "_acquire_migration_lock", AsyncMock(return_value="tok-1"))
        release_mock = AsyncMock()
        monkeypatch.setattr(dm, "_release_migration_lock", release_mock)
        db._db.asset_compliance.find = MagicMock(return_value=_EmptyAsyncCursor())

        await dm.migrate_compliance_tenant_ids()

        db._db.asset_compliance.find.assert_called_once()
        release_mock.assert_awaited_once_with(db, "compliance_tenant_ids", "tok-1")

    @pytest.mark.asyncio
    async def test_instructions_migration_skips_work_when_lock_not_acquired(self, monkeypatch):
        db = MagicMock()
        monkeypatch.setattr(dm, "get_database", lambda: db)
        monkeypatch.setattr(dm, "_acquire_migration_lock", AsyncMock(return_value=None))
        monkeypatch.setattr(dm, "_release_migration_lock", AsyncMock())

        await dm.migrate_instructions_tenant_ids()

        db._db.agent_instructions.find.assert_not_called()

    @pytest.mark.asyncio
    async def test_seed_compliance_frameworks_skips_when_lock_not_acquired(self, monkeypatch):
        db = MagicMock()
        monkeypatch.setattr(dm, "get_database", lambda: db)
        monkeypatch.setattr(dm, "_acquire_migration_lock", AsyncMock(return_value=None))
        monkeypatch.setattr(dm, "_release_migration_lock", AsyncMock())

        await dm.seed_compliance_frameworks()

        db._db.compliance_frameworks.count_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_seed_compliance_frameworks_releases_lock_when_already_seeded(self, monkeypatch):
        """Covers the early `return` inside the try block (count > 0) —
        finally must still run and release the lock."""
        db = MagicMock()
        db._db.compliance_frameworks.count_documents = AsyncMock(return_value=5)
        monkeypatch.setattr(dm, "get_database", lambda: db)
        monkeypatch.setattr(dm, "_acquire_migration_lock", AsyncMock(return_value="tok-2"))
        release_mock = AsyncMock()
        monkeypatch.setattr(dm, "_release_migration_lock", release_mock)

        await dm.seed_compliance_frameworks()

        release_mock.assert_awaited_once_with(db, "seed_compliance_frameworks", "tok-2")

    @pytest.mark.asyncio
    async def test_registration_key_migration_skips_when_lock_not_acquired(self, monkeypatch):
        db = MagicMock()
        monkeypatch.setattr(dm, "get_database", lambda: db)
        monkeypatch.setattr(dm, "_acquire_migration_lock", AsyncMock(return_value=None))
        monkeypatch.setattr(dm, "_release_migration_lock", AsyncMock())

        await dm.migrate_tenant_registration_keys()

        db._db.tenants.find.assert_not_called()
