"""Migration 029: partner channel indexes (phase 87, PART-07).

Indexes only, nothing is backfilled (D-12): a ``tenants`` document that existed before this runs keeps
no ``partnerId`` and no ``type``, which is exactly what a direct customer is.
* ``tenants.partnerId`` and ``tenants.type``: partial indexes, so the many direct customers cost nothing;
  they back the partner portal's customer list and the pool reconcile.
* ``invites.tokenHash`` (unique) and ``invites (email, createdAt)``: the partner invitation lookups.

``create_index`` with an unchanged definition is a no-op, so a second run changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Partner channel: tenants partnerId/type partial indexes, invites tokenHash and email indexes"

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    await db.tenants.create_index([("partnerId", 1)], name="partnerId_1",
                                  partialFilterExpression={"partnerId": {"$type": "string"}})
    await db.tenants.create_index([("type", 1)], name="type_1",
                                  partialFilterExpression={"type": {"$type": "string"}})
    await db.invites.create_index([("tokenHash", 1)], name="tokenHash_1", unique=True)
    await db.invites.create_index([("email", 1), ("createdAt", -1)], name="email_1_createdAt_-1")
    logger.info("migration 029: partner channel indexes ensured")
