"""Regression tests for ARCH-018 (2026-08-25 audit): seed_database() used to
wrap every seeding step (migrations, super admin user, platform tenant,
Super Admin role, Tenant Admin role, ITAM backfill, 5 standard roles) in one
try/except. A failure partway through silently aborted every step after it
too, with only one generic "Database seeding error" log line and no
indication which step actually failed. Each step now runs in its own
try/except, so one broken step no longer prevents the others from running.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app_startup


def _mock_db():
    db = MagicMock()
    db._db = MagicMock()
    db._db.users.find_one = AsyncMock(return_value={"email": "super@omni.ai"})
    db._db.users.update_one = AsyncMock()
    db._db.users.insert_one = AsyncMock()
    db.tenants.find_one = AsyncMock(return_value={"id": "platform-admin"})
    db.tenants.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    db.roles.update_one = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_super_admin_role_failure_does_not_block_standard_roles(monkeypatch):
    """The exact scenario this fix targets: a failure on one role write
    used to silently kill the ITAM backfill and all 5 standard roles for
    that boot."""
    db = _mock_db()

    async def failing_or_ok_update_one(filter_, *args, **kwargs):
        if filter_.get("name") == "Super Admin":
            raise Exception("simulated Mongo validation error")
        return MagicMock()

    db.roles.update_one = AsyncMock(side_effect=failing_or_ok_update_one)

    monkeypatch.setattr(app_startup, "get_database", lambda: db)
    monkeypatch.setattr(app_startup, "run_migrations", AsyncMock())

    await app_startup.seed_database()

    role_names_written = [
        call.args[0].get("name") for call in db.roles.update_one.call_args_list
    ]
    assert "Tenant Admin" in role_names_written
    assert "analyst" in role_names_written
    assert "viewer" in role_names_written
    db.tenants.update_many.assert_awaited_once()


@pytest.mark.asyncio
async def test_migration_failure_does_not_block_super_admin_seeding(monkeypatch):
    db = _mock_db()
    monkeypatch.setattr(app_startup, "get_database", lambda: db)
    monkeypatch.setattr(app_startup, "run_migrations", AsyncMock(side_effect=Exception("migration broke")))

    await app_startup.seed_database()

    db._db.users.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_platform_tenant_failure_does_not_block_role_seeding(monkeypatch):
    db = _mock_db()
    db.tenants.find_one = AsyncMock(side_effect=Exception("tenants lookup broke"))
    monkeypatch.setattr(app_startup, "get_database", lambda: db)
    monkeypatch.setattr(app_startup, "run_migrations", AsyncMock())

    await app_startup.seed_database()

    role_names_written = [
        call.args[0].get("name") for call in db.roles.update_one.call_args_list
    ]
    assert "Super Admin" in role_names_written
    assert "analyst" in role_names_written


@pytest.mark.asyncio
async def test_all_steps_succeed_when_nothing_fails(monkeypatch):
    db = _mock_db()
    monkeypatch.setattr(app_startup, "get_database", lambda: db)
    monkeypatch.setattr(app_startup, "run_migrations", AsyncMock())

    await app_startup.seed_database()

    role_names_written = [
        call.args[0].get("name") for call in db.roles.update_one.call_args_list
    ]
    assert set(role_names_written) == {
        "Super Admin", "Tenant Admin", "analyst", "security_analyst",
        "incident_responder", "user", "viewer",
    }
