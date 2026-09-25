"""
Migration 004: Unique compound index on (tenantId, hostname) for agents
(Task 16, D9).

/register in agent_registry_endpoints.py resolves an existing agent with
find_one({"tenantId": ..., "hostname": ...}) and then reuses that document's
id. That is correct for sequential registrations but is a TOCTOU race: two
concurrent /register calls for one hostname both read no match, both mint a
fresh agent-<uuid>, and both insert. No application-level check can close
this window, because the check and the write are not atomic.

The D9 write path already carries an `except E11000` branch whose comment
names this index as "the authoritative backstop" — but no such index existed,
so the branch was dead code and the race was fully open. This migration
creates the constraint the code already assumes.

Not a bootstrap index in database.py: the numbered-migration runner
(migrations/runner.py) gives ordered discovery and _migrations bookkeeping,
which the ad-hoc bootstrap path does not.

ponytail: create_index(unique=True) raises E11000 and aborts the migration
if the collection already holds two documents sharing a (tenantId,
hostname). The D9 race was live during Phase 66, so duplicates likely
exist. This migration deliberately does NOT dedupe — deleting agent
documents would orphan assets, instructions, and metrics history. Check for
duplicates by hand first; upgrade path is a reviewed dedupe pass that
repoints child collections at the surviving agent id before removing any
document.
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING

logger = logging.getLogger(__name__)

MIGRATION_ID = "004_agents_tenant_hostname_unique"
DESCRIPTION = "Unique compound index on (tenantId, hostname) for agents — backstop for the /register TOCTOU race"


async def up(db: AsyncIOMotorDatabase) -> None:
    """Create indexes idempotently — MongoDB silently skips existing ones."""

    # One agent document per (tenant, hostname). Scoped by tenantId because
    # the same hostname may legitimately appear across tenants.
    #
    # This index constrains inserts and upsert-insertions only. The ~25 other
    # writers to `agents` are plain update_one / update_many with no
    # upsert=True, so they cannot create a document and cannot trip it.
    await db.agents.create_index(
        [("tenantId", ASCENDING), ("hostname", ASCENDING)],
        name="idx_agents_tenant_hostname_unique",
        unique=True,
        background=True,
    )

    logger.info("[Migration 004] agents (tenantId, hostname) unique index created/verified.")
