"""Regression tests for ARCH-001 (2026-08-25 audit): scheduler.py's periodic
jobs run every minute via IntervalTrigger on every horizontally-scaled
replica, with no lock. Unlike database_migrations.py's idempotent
migrations, this was a genuine correctness bug: a deployment job read as
status="Scheduled" by two replicas in the same tick would both flip it to
"In Progress" and both fire off a duplicate simulation/scan task for the
same job. Both jobs now use the shared distributed_lock module.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock

import scheduler


class _EmptyAsyncCursor:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def _mock_find_to_list(return_value=None):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=return_value or [])
    return MagicMock(return_value=cursor)


class TestProcessScheduledDeploymentsLock:

    @pytest.mark.asyncio
    async def test_skips_when_lock_not_acquired(self, monkeypatch):
        db = MagicMock()
        monkeypatch.setattr(scheduler, "get_database", lambda: db)
        monkeypatch.setattr(scheduler, "acquire_lock", AsyncMock(return_value=None))
        release_mock = AsyncMock()
        monkeypatch.setattr(scheduler, "release_lock", release_mock)

        await scheduler.process_scheduled_deployments()

        db.patch_deployment_jobs.find.assert_not_called()
        release_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_and_releases_lock_when_acquired(self, monkeypatch):
        db = MagicMock()
        db.patch_deployment_jobs.find = _mock_find_to_list([])
        db.software_deployment_jobs.find = _mock_find_to_list([])
        monkeypatch.setattr(scheduler, "get_database", lambda: db)
        monkeypatch.setattr(scheduler, "acquire_lock", AsyncMock(return_value="tok-1"))
        release_mock = AsyncMock()
        monkeypatch.setattr(scheduler, "release_lock", release_mock)

        await scheduler.process_scheduled_deployments()

        db.patch_deployment_jobs.find.assert_called_once()
        release_mock.assert_awaited_once_with(db, "process_scheduled_deployments", "tok-1")

    @pytest.mark.asyncio
    async def test_lock_uses_ttl_under_the_one_minute_interval(self, monkeypatch):
        db = MagicMock()
        db.patch_deployment_jobs.find = _mock_find_to_list([])
        db.software_deployment_jobs.find = _mock_find_to_list([])
        monkeypatch.setattr(scheduler, "get_database", lambda: db)
        acquire_mock = AsyncMock(return_value="tok-1")
        monkeypatch.setattr(scheduler, "acquire_lock", acquire_mock)
        monkeypatch.setattr(scheduler, "release_lock", AsyncMock())

        await scheduler.process_scheduled_deployments()

        _, kwargs = acquire_mock.call_args
        assert kwargs["ttl_seconds"] < 60


class TestProcessPentestSchedulesLock:

    @pytest.mark.asyncio
    async def test_skips_when_lock_not_acquired(self, monkeypatch):
        db = MagicMock()
        monkeypatch.setattr(scheduler, "get_database", lambda: db)
        monkeypatch.setattr(scheduler, "acquire_lock", AsyncMock(return_value=None))
        release_mock = AsyncMock()
        monkeypatch.setattr(scheduler, "release_lock", release_mock)

        await scheduler.process_pentest_schedules()

        db.pentest_schedules.find.assert_not_called()
        release_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_and_releases_lock_when_acquired(self, monkeypatch):
        db = MagicMock()
        db.pentest_schedules.find = MagicMock(return_value=_EmptyAsyncCursor())
        monkeypatch.setattr(scheduler, "get_database", lambda: db)
        monkeypatch.setattr(scheduler, "acquire_lock", AsyncMock(return_value="tok-2"))
        release_mock = AsyncMock()
        monkeypatch.setattr(scheduler, "release_lock", release_mock)

        await scheduler.process_pentest_schedules()

        db.pentest_schedules.find.assert_called_once()
        release_mock.assert_awaited_once_with(db, "process_pentest_schedules", "tok-2")
