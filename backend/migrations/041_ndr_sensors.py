"""Migration 041: network sensor indexes, and the end of the fake NDR collections (88.1, stage 1).

* ``ndr_sensors``: unique (tenantId, sensorId).
* ``ndr_sensor_stats``: unique (tenantId, sensorId, sampledAt), which also serves "newest samples of a sensor",
  and a TTL on ``sampledAt`` of 8 days, so the 7-day report can read a full week of samples.
* ``network_flows`` and ``ndr_anomalies`` held only hand-posted or demo-seeded rows, and nothing reads them any
  more. Each is dropped when it is empty. One that still holds documents is left alone and named in the log, to
  be archived by hand first. ``ndr_baselines`` is not touched.

``create_index`` with an unchanged definition is a no-op, so a second run changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Network sensor indexes (88.1 stage 1); drops the empty fake-NDR collections."
STATS_TTL_SECONDS = 8 * 86_400
LEGACY_COLLECTIONS = ("network_flows", "ndr_anomalies")

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    await db.ndr_sensors.create_index([("tenantId", 1), ("sensorId", 1)], unique=True, name="tenant_sensor_unique")
    await db.ndr_sensor_stats.create_index([("tenantId", 1), ("sensorId", 1), ("sampledAt", 1)], unique=True,
                                           name="tenant_sensor_minute_unique")
    await db.ndr_sensor_stats.create_index([("sampledAt", 1)], expireAfterSeconds=STATS_TTL_SECONDS,
                                           name="sampled_at_ttl")
    existing = set(await db.list_collection_names())
    for name in LEGACY_COLLECTIONS:
        if name not in existing:
            continue
        if await db[name].count_documents({}, limit=1):
            logger.warning("migration 041: %s still holds documents and was kept; archive it, then drop it", name)
            continue
        await db.drop_collection(name)
        logger.info("migration 041: dropped the empty collection %s", name)
