"""Migrations 036 and 037 (88.1, stage 1), against a real MongoDB (skips without one).

Value: protects=stats samples expire after 8 days as the data terms say, a legacy NDR collection that still holds
rows is never dropped, and each tenant whose IDS/IPS control flips gets exactly one notice; fails_when=the TTL is
missing or changed, a non-empty collection is dropped, or a re-run posts the notice again; no_claim=that MongoDB
deletes on time (the index definition is asserted, not the deletion).
"""
import importlib
from datetime import datetime, timedelta, timezone

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

sensors_migration = importlib.import_module("migrations.036_ndr_sensors")
notice_migration = importlib.import_module("migrations.037_ids_check_notice")


async def test_036_indexes_the_sensor_collections_and_is_safe_to_run_twice(mongo_db):
    await sensors_migration.up(mongo_db)
    await sensors_migration.up(mongo_db)

    stats = await mongo_db.ndr_sensor_stats.index_information()
    assert stats["sampled_at_ttl"]["key"] == [("sampledAt", 1)]
    assert stats["sampled_at_ttl"]["expireAfterSeconds"] == 691_200
    assert stats["tenant_sensor_minute_unique"]["unique"] is True
    assert (await mongo_db.ndr_sensors.index_information())["tenant_sensor_unique"]["unique"] is True


async def test_036_drops_an_empty_legacy_collection_and_keeps_one_with_rows(mongo_db):
    await mongo_db.create_collection("network_flows")
    await mongo_db.ndr_anomalies.insert_one({"tenant_id": "tenant-a", "type": "beaconing"})

    await sensors_migration.up(mongo_db)

    names = await mongo_db.list_collection_names()
    assert "network_flows" not in names
    assert await mongo_db.ndr_anomalies.count_documents({}) == 1


async def test_037_posts_one_notice_to_each_tenant_the_old_rule_passed(mongo_db):
    now = datetime.now(timezone.utc)
    await mongo_db.tenants.insert_many([{"id": tenant, "name": tenant} for tenant in ("tenant-a", "tenant-b", "tenant-c")])
    await mongo_db.security_alerts.insert_many([
        {"tenantId": "tenant-a", "created_at": (now - timedelta(days=1)).isoformat()},
        {"tenantId": "tenant-a", "created_at": (now - timedelta(hours=2)).isoformat()},
        {"tenantId": "tenant-b", "created_at": (now - timedelta(days=10)).isoformat()},
        {"tenantId": "deleted-tenant", "created_at": now.isoformat()},
    ])

    await notice_migration.up(mongo_db)
    await notice_migration.up(mongo_db)

    notices = await mongo_db.notifications.find({}, {"_id": 0}).to_list(length=None)
    assert [(notice["tenantId"], notice["title"], notice["metadata"]) for notice in notices] == [
        ("tenant-a", notice_migration.TITLE, {"kind": "ids_check_corrected", "audience": "tenant_admins"})]
    assert "A firewall IPS is not verified by this platform." in notices[0]["message"]
