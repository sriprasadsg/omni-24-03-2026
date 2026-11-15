"""ids_ips_enabled reads the tenant's own network sensors (88.1; D21, R3, R11), against a real MongoDB through
the tenant-scoped database (skips without one).

Value: protects=no IDS/IPS credit without a sensor that watched for the last day, and no tenant scored on another
tenant's sensor; fails_when=a dead, blind, retired or never-reporting sensor returns partial or pass, or the check
reads across tenants; no_claim=the exact 24-hour and 5% boundaries (test_ndr_sensors.py pins them with an injected
clock; run_check takes none, so the rows here sit well inside each case).
"""
from datetime import datetime, timedelta, timezone

import pytest

from database import TenantIsolatedDatabase
from frameworks._common_checks import run_check
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

CTRL = {"check_type": "ids_ips_enabled"}
NOT_VERIFIED = "A firewall IPS is not verified by this platform."
HEALTHY = ((1000, 0), (5000, 10))


async def _sensor(db, tenant, sensor_id="s1", age=timedelta(minutes=1), points=HEALTHY, **fields):
    """A sensor whose last stats arrived ``age`` ago (None: never), with one sample a minute up to then."""
    last = datetime.now(timezone.utc) - (age or timedelta(0))
    record = {"tenantId": tenant, "sensorId": sensor_id, "name": f"sensor-{sensor_id}", "rulesLoaded": 48000}
    if age is not None:
        record["lastStatsAt"] = last
    await db.ndr_sensors.insert_one({**record, **fields})
    for index, (packets, drops) in enumerate(points):
        await db.ndr_sensor_stats.insert_one({
            "tenantId": tenant, "sensorId": sensor_id, "packets": packets, "drops": drops,
            "uptime": 600 + 60 * index, "sampledAt": last - timedelta(minutes=len(points) - 1 - index)})


async def _check(db, tenant):
    token = set_tenant_id(tenant)
    try:
        return await run_check(TenantIsolatedDatabase(db), CTRL)
    finally:
        reset_tenant_id(token)


async def test_a_tenant_without_a_sensor_fails(mongo_db):
    assert await _check(mongo_db, "tenant-a") == ("fail", f"No network IDS sensor reporting. {NOT_VERIFIED}")


@pytest.mark.parametrize("sensor, reason", [
    ({"age": None, "points": ()}, "has never reported"),
    ({"age": timedelta(days=3)}, "has not reported in 24 hours"),
    ({"points": ((1000, 0), (1000, 0))}, "saw no packets in 24 hours"),
    ({"rulesLoaded": 0}, "has no detection rules loaded"),
])
async def test_a_sensor_that_is_not_watching_earns_nothing(mongo_db, sensor, reason):
    await _sensor(mongo_db, "tenant-a", **sensor)

    assert await _check(mongo_db, "tenant-a") == ("fail", f"Network sensor 'sensor-s1' {reason}. {NOT_VERIFIED}")


async def test_a_retired_sensor_counts_as_no_sensor(mongo_db):
    await _sensor(mongo_db, "tenant-a", retiredAt=datetime.now(timezone.utc))

    assert await _check(mongo_db, "tenant-a") == ("fail", f"No network IDS sensor reporting. {NOT_VERIFIED}")


async def test_a_watching_sensor_that_drops_five_percent_is_partial(mongo_db):
    await _sensor(mongo_db, "tenant-a", points=((0, 0), (1000, 50)))

    assert await _check(mongo_db, "tenant-a") == (
        "partial", "Network sensor 'sensor-s1' is watching but dropped 5.0% of packets in 24 hours")


async def test_a_sensor_that_watched_all_day_passes_and_the_evidence_names_it(mongo_db):
    await _sensor(mongo_db, "tenant-a")

    assert await _check(mongo_db, "tenant-a") == (
        "pass", "Network sensor 'sensor-s1' is reporting: 4000 packets in 24 hours, 0.2% dropped, 48000 rules loaded")


async def test_one_watching_sensor_is_enough_when_another_is_dead(mongo_db):
    await _sensor(mongo_db, "tenant-a", "s1", age=timedelta(days=3))
    await _sensor(mongo_db, "tenant-a", "s2")

    status, evidence = await _check(mongo_db, "tenant-a")

    assert status == "pass" and "'sensor-s2'" in evidence


async def test_a_tenant_is_never_scored_on_another_tenants_sensor(mongo_db):
    await _sensor(mongo_db, "tenant-b")
    await _sensor(mongo_db, "tenant-a", points=())

    assert (await _check(mongo_db, "tenant-b"))[0] == "pass"
    assert await _check(mongo_db, "tenant-a") == (
        "fail", f"Network sensor 'sensor-s1' saw no packets in 24 hours. {NOT_VERIFIED}")
