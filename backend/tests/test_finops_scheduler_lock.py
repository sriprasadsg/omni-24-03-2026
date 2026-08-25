"""Regression tests for ARCH-001 (2026-08-25 audit): finops_scheduler.py's
hourly recalculate_all_finops_costs ran on every replica with no lock —
with N replicas that multiplies real per-tenant cost-recalculation work
(often backed by external cloud billing API calls) by N, plus duplicate
audit_logs entries every hour. Now uses the shared distributed_lock module.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock

import finops_scheduler


def _mock_db_with_no_tenants():
    db = MagicMock()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    db.tenants.find = MagicMock(return_value=cursor)
    db.audit_logs.insert_one = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_skips_when_lock_not_acquired(monkeypatch):
    db = _mock_db_with_no_tenants()
    monkeypatch.setattr("database.get_database", lambda: db)
    monkeypatch.setattr(finops_scheduler, "acquire_lock", AsyncMock(return_value=None))
    release_mock = AsyncMock()
    monkeypatch.setattr(finops_scheduler, "release_lock", release_mock)

    await finops_scheduler.recalculate_all_finops_costs()

    db.tenants.find.assert_not_called()
    release_mock.assert_not_called()


@pytest.mark.asyncio
async def test_runs_and_releases_lock_when_acquired(monkeypatch):
    db = _mock_db_with_no_tenants()
    monkeypatch.setattr("database.get_database", lambda: db)
    monkeypatch.setattr(finops_scheduler, "acquire_lock", AsyncMock(return_value="tok-1"))
    release_mock = AsyncMock()
    monkeypatch.setattr(finops_scheduler, "release_lock", release_mock)

    await finops_scheduler.recalculate_all_finops_costs()

    db.tenants.find.assert_called_once()
    release_mock.assert_awaited_once_with(db, "recalculate_all_finops_costs", "tok-1")


@pytest.mark.asyncio
async def test_lock_ttl_stays_under_the_one_hour_interval(monkeypatch):
    db = _mock_db_with_no_tenants()
    monkeypatch.setattr("database.get_database", lambda: db)
    acquire_mock = AsyncMock(return_value="tok-1")
    monkeypatch.setattr(finops_scheduler, "acquire_lock", acquire_mock)
    monkeypatch.setattr(finops_scheduler, "release_lock", AsyncMock())

    await finops_scheduler.recalculate_all_finops_costs()

    _, kwargs = acquire_mock.call_args
    assert kwargs["ttl_seconds"] < 3600
