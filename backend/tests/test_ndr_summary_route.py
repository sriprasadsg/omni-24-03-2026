"""GET /api/ndr/summary and the removed fake-NDR routes (88.1, stage 1), against a real MongoDB (skips without one).

Value: protects=the summary reports only what sensor records say, for the caller's tenant alone, and the routes
that served invented data stay gone; fails_when=a hard-coded "running" value returns, a sensor of another tenant is
listed, a token hash is served, or a removed route is mounted again; no_claim=sign-in and the catalogue guard (the
route function is called directly, and the router is inspected rather than served).
"""
from datetime import datetime, timedelta, timezone

import ndr_endpoints
from database import TenantIsolatedDatabase
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


async def _summary(db, tenant):
    token = set_tenant_id(tenant)
    try:
        return await ndr_endpoints.get_summary(user=None, db=TenantIsolatedDatabase(db))
    finally:
        reset_tenant_id(token)


async def test_a_tenant_without_sensors_gets_an_empty_list_and_no_running_flag(mongo_db):
    summary = await _summary(mongo_db, "tenant-a")

    assert summary == {"sensors": []}
    assert "detection_running" not in str(summary)


async def test_the_summary_lists_only_the_callers_sensors_with_their_real_state(mongo_db):
    now = datetime.now(timezone.utc)
    await mongo_db.ndr_sensors.insert_many([
        {"tenantId": "tenant-a", "sensorId": "s1", "name": "core switch", "tokenHash": "f" * 64,
         "lastStatsAt": now - timedelta(hours=2)},
        {"tenantId": "tenant-a", "sensorId": "s2", "name": "new box"},
        {"tenantId": "tenant-b", "sensorId": "s9", "name": "other tenant", "lastStatsAt": now},
    ])

    summary = await _summary(mongo_db, "tenant-a")

    assert [(row["sensorId"], row["name"], row["state"]) for row in summary["sensors"]] == [
        ("s1", "core switch", "silent"), ("s2", "new box", "awaiting_first_report")]
    assert "tokenHash" not in str(summary) and "f" * 64 not in str(summary)


async def test_a_fresh_sensor_with_growing_packets_reads_live(mongo_db):
    now = datetime.now(timezone.utc)
    await mongo_db.ndr_sensors.insert_one({"tenantId": "tenant-a", "sensorId": "s1", "name": "core switch",
                                           "lastStatsAt": now})
    await mongo_db.ndr_sensor_stats.insert_many([
        {"tenantId": "tenant-a", "sensorId": "s1", "sampledAt": now - timedelta(minutes=1), "packets": 100,
         "drops": 0, "uptime": 60},
        {"tenantId": "tenant-a", "sensorId": "s1", "sampledAt": now, "packets": 900, "drops": 1, "uptime": 120},
    ])

    assert (await _summary(mongo_db, "tenant-a"))["sensors"][0]["state"] == "live"


def test_only_the_summary_route_is_left_on_the_ndr_router():
    routes = {(method, route.path) for route in ndr_endpoints.router.routes for method in route.methods}

    assert routes == {("GET", "/api/ndr/summary")}
