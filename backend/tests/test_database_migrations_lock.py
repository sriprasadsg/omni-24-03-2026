"""Regression tests for DB-F08 (2026-08-25 audit): startup migrations in
database_migrations.py had no distributed lock, so every horizontally-scaled
replica re-scanned and re-wrote the same backlog on every restart (wasted
work growing with replica count), and seed_compliance_frameworks could spawn
duplicate concurrent child-process seeders. These migrations now use the
shared distributed_lock module (see test_distributed_lock.py for the lock
mechanism's own tests) so only one replica actually runs a given migration
at a time, self-healing via TTL if the holder crashes.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock

import database_migrations as dm


class _EmptyAsyncCursor:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


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
