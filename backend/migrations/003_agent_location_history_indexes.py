"""
Migration 003: Compound + timestamp indexes for agent_location_history
(Phase 46, GAUD-01).

agent_location_history is a new append-only collection (46-02). Two access
patterns need indexing:
  - Tenant-scoped GET-by-agent read, sorted ascending by timestamp (GAUD-02
    timeline panel): compound index on (agent_id, tenantId, timestamp).
  - The 365-day retention sweep's `$lt` cutoff comparison (D-01, routed
    through the existing retention module): standalone index on timestamp.

No auto-expiring index is created here — retention for
this collection is an app-level cleanup_agent_location_history() sweep, not
a Mongo auto-expiry index (46-RESEARCH.md anti-pattern:
migrations/002_scale_indexes.py already created an auto-expiring index on
agent_metrics_history.timestamp, which is a silent no-op because that field
is written as an ISO string, not a BSON Date. agent_location_history.timestamp
IS a real Date, so an auto-expiring index would actually function here — but
this phase's retention design is the explicit app-level sweep, so none is
added, to keep exactly one enforcement mechanism instead of two racing ones).
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING

logger = logging.getLogger(__name__)

MIGRATION_ID = "003_agent_location_history_indexes"
DESCRIPTION = "Compound + timestamp indexes for the agent_location_history append-only audit collection"


async def up(db: AsyncIOMotorDatabase) -> None:
    """Create indexes idempotently — MongoDB silently skips existing ones."""

    # Tenant-scoped GET-by-agent read, sorted ascending by timestamp
    # (GAUD-02's location-history timeline panel).
    await db.agent_location_history.create_index(
        [("agent_id", ASCENDING), ("tenantId", ASCENDING), ("timestamp", ASCENDING)],
        name="idx_agent_location_history_agent_tenant_timestamp",
        background=True,
    )

    # Standalone timestamp index supporting the app-level 365-day retention
    # $lt sweep (D-01) — not an auto-expiring index (see module docstring).
    await db.agent_location_history.create_index(
        [("timestamp", ASCENDING)],
        name="idx_agent_location_history_timestamp",
        background=True,
    )

    logger.info("[Migration 003] agent_location_history indexes created/verified.")
