"""Migration 038: indexes for SOC case tasks and evidence (soc_case_tasks, soc_case_evidence).

Both collections are new and start empty; nothing existing is read or changed, so a second run changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Indexes for SOC case tasks and evidence. Nothing existing changed."

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    import soc_cases

    await soc_cases.ensure_indexes(db)
    logger.info("migration 038: SOC case task and evidence indexes in place")
