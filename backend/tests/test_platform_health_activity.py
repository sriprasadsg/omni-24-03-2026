"""Platform-health rows in the Activity lists (Phase 82, plan 82-01, HEAL-07, D-23, PROH-82-06).

The Super Admin's platform list shows them (bucket "platform_health" and under "all"); no tenant
admin, tenant viewer or Platform Support view, and no tenant count or total, ever includes them.
Real Mongo through the throwaway database of tests/_mongo_test_db.py.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-platform-health-activity")

from autonomous_ops import PLATFORM_TENANT_ID, ledger, views
from tests._autonomous_ops_http import api  # noqa: F401  (fixture)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

TENANT_LIST = "/api/autonomous-ops/actions"
PLATFORM_LIST = "/api/platform/autonomous-ops/actions"


async def _health(db, event_id, kind="service_down", params=None, minutes_ago=0):
    return await ledger.record_platform_health(
        db, event_id, kind, params if params is not None else {"target": "mongod"},
        at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago), host="omni")


async def _platform_stop_row(db):
    return await ledger.record_control(db, PLATFORM_TENANT_ID, "platform_stop_pressed", scope="platform",
                                       actor={"username": "root", "display": "Root", "tier": "platform"}, reason=None)


@pytest.fixture
async def seeded(api):
    db = api.db
    await _health(db, "evt00000001", "service_down", minutes_ago=30)
    await _health(db, "evt00000002", "restart", {"target": "mongod", "attempt": 1, "ok": True, "seconds": 7},
                  minutes_ago=20)
    await _platform_stop_row(db)
    return api


def _ids(res):
    return [i["id"] for i in res.json()["items"]]


async def test_super_admin_all_bucket_mixes_health_and_stop_rows_newest_first(seeded):
    res = await seeded.call("GET", PLATFORM_LIST, role="super_admin")
    assert res.status_code == 200
    items = res.json()["items"]
    assert [i["bucket"] for i in items] == ["control", "platform_health", "platform_health"]
    assert [i["id"] for i in items[1:]] == ["PH-evt00000002", "PH-evt00000001"]
    assert res.json()["counts"]["platform_health"] == 2


async def test_super_admin_platform_health_bucket_returns_only_those_rows(seeded):
    res = await seeded.call("GET", PLATFORM_LIST + "?bucket=platform_health", role="super_admin")
    assert res.status_code == 200
    assert _ids(res) == ["PH-evt00000002", "PH-evt00000001"]
    assert res.json()["total"] == 2 and res.json()["counts"]["platform_health"] == 2


async def test_present_row_is_rendered_from_health_messages(seeded):
    res = await seeded.call("GET", PLATFORM_LIST + "?bucket=platform_health", role="super_admin")
    restart, down = res.json()["items"]
    assert down["actionLabel"] == "Service check" and down["reasonText"] == "Failed 2 checks in a row."
    assert down["ruleId"] == "service-down" and down["host"] == "omni" and down["target"] == "mongod"
    assert down["resultText"] == "MongoDB is down." and down["healthChip"] == "critical"
    assert down["source"] == "Watchdog" and down["state"] == "recorded"
    assert restart["actionLabel"] == "Restart MongoDB" and restart["healthChip"] == "healthy"
    assert restart["resultText"] == "Restart 1 of 3: restarted, healthy after 7 s."
    assert restart["classLine"] is None and restart["controlEvent"] is None and restart["by"] is None


async def test_other_rows_carry_null_health_keys_and_the_platform_stop_row_is_unchanged(seeded):
    res = await seeded.call("GET", PLATFORM_LIST, role="super_admin")
    control = res.json()["items"][0]
    assert control["bucket"] == "control" and control["controlEvent"] == "platform_stop_pressed"
    assert control["healthChip"] is None and control["source"] is None


def test_bucket_of_puts_platform_health_before_any_state_lookup():
    for state in ("recorded", "failed", "refused", "unknown_state", None):
        assert views.bucket_of({"kind": "platform_health", "state": state}) == "platform_health"
    assert views.bucket_of({"kind": "platform_health", "state": "failed"}) != "refused"


def test_bucket_states_is_unchanged():
    from autonomous_ops import BUCKET_STATES
    assert "platform_health" not in BUCKET_STATES


@pytest.mark.parametrize("role", ["tenant_admin", "analyst"])
async def test_a_tenant_list_never_contains_platform_health(seeded, role):
    res = await seeded.call("GET", TENANT_LIST, role=role, tenant="t1")
    assert res.status_code == 200
    body = res.json()
    assert all(i["bucket"] != "platform_health" for i in body["items"])
    assert "platform_health" not in body["counts"]
    # the tenant still sees the platform stop control row exactly as in Phase 81
    assert [i["controlEvent"] for i in body["items"]] == ["platform_stop_pressed"]
    assert body["total"] == 1


async def test_tenant_router_refuses_the_platform_health_bucket(seeded):
    res = await seeded.call("GET", TENANT_LIST + "?bucket=platform_health", role="tenant_admin", tenant="t1")
    assert res.status_code == 422


async def test_platform_support_naming_the_platform_tenant_sees_no_platform_health(seeded):
    res = await seeded.call("GET", TENANT_LIST + "?tenantId=platform-admin", role="platform_support")
    assert res.status_code == 200
    body = res.json()
    assert [i for i in body["items"] if i["bucket"] == "platform_health"] == []
    assert "platform_health" not in body["counts"] and body["total"] == 1
    assert (await seeded.call("GET", TENANT_LIST + "?tenantId=t1", role="platform_support")).status_code == 200


async def test_super_admin_on_the_tenant_router_naming_the_platform_tenant_sees_none_either(seeded):
    res = await seeded.call("GET", TENANT_LIST + "?tenantId=platform-admin", role="super_admin")
    assert res.status_code == 200 and all(i["bucket"] != "platform_health" for i in res.json()["items"])


async def test_platform_support_cannot_use_the_platform_route(seeded):
    res = await seeded.call("GET", PLATFORM_LIST + "?bucket=platform_health", role="platform_support")
    assert res.status_code == 403


async def test_other_tenants_state_buckets_are_not_affected_by_health_rows(seeded):
    res = await seeded.call("GET", PLATFORM_LIST + "?bucket=done", role="super_admin")
    assert res.status_code == 200 and res.json()["items"] == []
    counts = res.json()["counts"]
    assert counts["done"] == 0 and counts["refused"] == 0 and counts["platform_health"] == 2


async def test_pagination_keeps_health_rows_in_created_order(api):
    for n in range(5):
        await _health(api.db, f"evt0000010{n}", minutes_ago=50 - n)
    first = await api.call("GET", PLATFORM_LIST + "?bucket=platform_health&limit=2", role="super_admin")
    assert _ids(first) == ["PH-evt00000104", "PH-evt00000103"]
    cursor = first.json()["nextCursor"]
    second = await api.call("GET", PLATFORM_LIST + f"?bucket=platform_health&limit=3&cursor={cursor}",
                            role="super_admin")
    assert _ids(second) == ["PH-evt00000102", "PH-evt00000101", "PH-evt00000100"]
    assert "counts" not in second.json() and second.json()["nextCursor"] is None
