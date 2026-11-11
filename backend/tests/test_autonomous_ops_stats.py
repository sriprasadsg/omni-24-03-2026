"""Autonomous Ops statistics and time saved (Phase 86, plan 86-01, ACTV-05, ACTV-07, D-05..D-08, D-19).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the per-rule counts, the simulation column kept apart from the real ones, the fixed
minutes-per-kind estimate, the period edges, and the tenant boundary of GET /api/autonomous-ops/statistics;
fails_when=a simulation or control row is counted as a real decision, an undone action adds minutes, a
period edge moves, one tenant sees another's numbers, or the minutes table misses a registered command;
no_claim=the Statistics card rendering (autonomousOpsStats.test.tsx) and the export and digest, which
read this module in later plans.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rbac_utils
from api_key_auth import get_current_user_or_api_key
from auth_types import TokenData
from autonomous_ops import ledger, protected, registry
from autonomous_ops.reporting import DEFAULT_WINDOW, MINUTES_PER_KIND, stats
from catalogue_mounts import mount_dependencies
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

PLATFORM = "platform-admin"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


class StatsApi:
    """The reporting router behind its catalogue guard; the caller's identity is chosen per request."""

    def __init__(self, db, monkeypatch):
        import autonomous_ops_endpoints
        import autonomous_ops_reporting_endpoints as reporting
        self.user = None
        monkeypatch.setattr(autonomous_ops_endpoints, "get_database", lambda: db)
        monkeypatch.setattr(reporting, "get_database", lambda: db)
        monkeypatch.setattr(rbac_utils, "get_database", lambda: db)
        self.app = FastAPI()
        self.app.include_router(reporting.router,
                                dependencies=mount_dependencies("autonomous_ops_reporting_endpoints", "router"))
        self.app.dependency_overrides[get_current_user_or_api_key] = lambda: self.user

    async def get(self, path, *, role="tenant_admin", tenant="t1"):
        platform = role in ("super_admin", "platform_support", "platform_billing")
        self.user = TokenData(username=f"{role}@example.test", role=role,
                              tenant_id=PLATFORM if platform else tenant, scopes=None, auth_source="session")
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_tenant(mongo_db, "t2", shadow=False)
    return mongo_db, StatsApi(mongo_db, monkeypatch)


async def seed_row(db, tenant, command, state, *, rule=None, kind="security", approver=None, when=None):
    """One decision row with only the fields the statistics read."""
    row = {"id": "AO-" + uuid.uuid4().hex, "tenantId": tenant, "kind": kind, "command": command, "state": state,
           "reason": {"ruleId": rule or f"sweep:{command}"}, "approval": {"approver": approver},
           "createdAt": when or datetime.now(timezone.utc) - timedelta(days=1)}
    await db.autonomy_actions.insert_one(row)
    return row


# ================================================================== task 1: the tracer

async def test_the_route_counts_this_tenants_ledger_with_the_estimate_labelled(world):
    db, api = world
    await seed_row(db, "t1", "isolate_host", "executed")
    await seed_row(db, "t1", "isolate_host", "verified")
    await seed_row(db, "t1", "block_ip", "undone")
    await seed_row(db, "t1", "block_ip", "shadow")
    await seed_row(db, "t1", "isolate_host", "recorded", kind="control")
    await seed_row(db, "t1", "isolate_host", "recorded", kind="platform_health")
    await seed_row(db, "t2", "isolate_host", "executed")
    got = await api.get("/api/autonomous-ops/statistics")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["days"] == 30 and body["tenantId"] == "t1"
    assert body["totals"]["fired"] == 3 and body["totals"]["done"] == 2
    assert body["totals"]["undone"] == 1 and body["totals"]["wouldHaveDone"] == 1
    assert body["timeSaved"]["minutes"] == 30 and body["timeSaved"]["estimate"] is True


async def test_a_period_outside_seven_thirty_ninety_is_rejected(world):
    _, api = world
    assert (await api.get("/api/autonomous-ops/statistics?days=14")).status_code == 422
    assert (await api.get("/api/autonomous-ops/statistics?days=7")).status_code == 200


def test_the_default_period_is_thirty_days():
    assert DEFAULT_WINDOW == 30


def test_minutes_format_in_plain_words():
    assert stats.format_minutes(0) == "0 min"
    assert stats.format_minutes(45) == "About 45 min"
    assert stats.format_minutes(338) == "About 5 h 40 min"
    assert stats.format_minutes(120) == "About 2 h"


def test_minutes_per_kind_is_read_only_and_names_the_isolation_value():
    assert MINUTES_PER_KIND["isolate_host"] == 15
    with pytest.raises(TypeError):
        MINUTES_PER_KIND["isolate_host"] = 1   # type: ignore[index]
    assert registry.ACTIONS  # the full completeness check follows in task 2
