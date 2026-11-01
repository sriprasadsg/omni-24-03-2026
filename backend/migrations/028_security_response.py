"""Migration 028: Autonomous Ops security response indexes (phase 83, RESP-07 / RESP-08).

Indexes only, nothing is backfilled and nothing is deleted:
* ``autonomy_signals``: unique (tenantId, agentId, kind, indicator), and a 30-day TTL on ``lastSeenAt``
  so a signal nobody has seen for a month is dropped.
* ``edr_ioc``: (ioc_type, ioc_value) and (ioc_type, source_ip), the two lookups the sweep makes on the
  shared threat-feed rows.

``create_index`` with an unchanged definition is a no-op, so a second run changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Security response: autonomy_signals unique + TTL indexes, edr_ioc lookup indexes"

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    from autonomous_ops import signals

    await signals.ensure_indexes(db)
    logger.info("migration 028: security response indexes ensured")
