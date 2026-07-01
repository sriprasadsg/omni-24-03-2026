"""
Migration 002: Add compound and TTL indexes required for 5 000–100 000+ endpoint scale.

Without these indexes, MongoDB performs full-collection scans on the hottest query
paths (agent instruction polling, deployment job listing, heartbeat lookups, metrics
retention), which degrades linearly as the fleet grows.
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger(__name__)

MIGRATION_ID = "002_scale_indexes"
DESCRIPTION = "Compound and TTL indexes for enterprise-scale fleet operations"


async def up(db: AsyncIOMotorDatabase) -> None:
    """Create indexes idempotently — MongoDB silently skips existing ones."""

    # agent_instructions: agents poll pending instructions by agent_id + status on every heartbeat
    await db.agent_instructions.create_index(
        [("agent_id", ASCENDING), ("status", ASCENDING)],
        name="idx_agent_instructions_agent_status",
        background=True,
    )

    # patch_deployment_jobs: dashboard and background worker list jobs per tenant + status
    await db.patch_deployment_jobs.create_index(
        [("tenantId", ASCENDING), ("status", ASCENDING)],
        name="idx_patch_jobs_tenant_status",
        background=True,
    )

    # assets: heartbeat upserts and asset detail lookups by tenant + agentId
    await db.assets.create_index(
        [("tenantId", ASCENDING), ("agentId", ASCENDING)],
        name="idx_assets_tenant_agentid",
        background=True,
    )

    # agents: "recently-seen active agents per tenant" is the most common fleet query
    await db.agents.create_index(
        [("tenantId", ASCENDING), ("lastSeen", DESCENDING)],
        name="idx_agents_tenant_lastseen",
        background=True,
    )

    # agent_metrics_history: TTL — auto-expire records older than 30 days to bound
    # collection growth proportional to fleet size × polling frequency
    await db.agent_metrics_history.create_index(
        [("timestamp", ASCENDING)],
        name="idx_agent_metrics_ttl_30d",
        expireAfterSeconds=30 * 24 * 3600,
        background=True,
    )

    logger.info("[Migration 002] Scale indexes created/verified.")
