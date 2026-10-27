"""Migration 027: scheduled retention gate indexes (phase 82, HEAL-06).

Creates the indexes of the four retention collections: ``retention_gate`` and
``retention_counts`` (unique per tenantId + type) and ``retention_job_runs`` (startedAt). The
gate documents themselves are created by the nightly job on first sight of each (tenant, type),
so nothing is backfilled here and nothing is deleted. ``create_index`` with an unchanged
definition is a no-op, so a second run changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Scheduled retention: gate, count and run-summary indexes"

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    import retention_gate

    await retention_gate.ensure_indexes(db)
    logger.info("migration 027: retention gate indexes ensured")
