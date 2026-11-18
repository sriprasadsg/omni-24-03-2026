"""Migration 037: SOC incidents (soc_incidents) for the alerts already stored.

Alerts on one endpoint less than an hour apart become one incident, endpoint by endpoint in time order;
each alert gets its ``incidentId``. An incident whose alerts are all closed is closed (with their most
common resolution); one whose last alert is under an hour old keeps taking new alerts. Indexes include
the unique "one grouping incident per endpoint". Nothing is deleted; alerts already on an incident are
left alone, so a second run changes nothing.

First, alerts that name their endpoint only in ``metadata.agent_id`` get it at the top level (036 lifted it
only together with a missing tenant, so the personal-data alerts kept none and would share one incident).
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "SOC incidents for existing alerts (an endpoint's alerts less than an hour apart). Nothing deleted."

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    import soc_incidents

    lifted = 0
    async for d in db.security_alerts.find({"agent_id": {"$in": [None, ""]}, "metadata.agent_id": {"$nin": [None, ""]}},
                                           {"_id": 1, "metadata.agent_id": 1}):
        await db.security_alerts.update_one({"_id": d["_id"]}, {"$set": {"agent_id": d["metadata"]["agent_id"]}})
        lifted += 1
    await soc_incidents.ensure_indexes(db)
    made = await soc_incidents.backfill(db)
    logger.info("migration 037: %d endpoint ids lifted, %d SOC incidents made from existing alerts", lifted, made)
