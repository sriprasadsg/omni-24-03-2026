"""Migration 032: the first-line service desk (phase 85, DESK-01 to DESK-07).

Indexes only, nothing is backfilled and nothing is deleted. ``service_desk.store.ensure_indexes`` makes them all:
* ``service_desk_jobs``: the unique ``one_attempt_per_ticket`` (tenantId, ticketId), the queue lookup
  (state, createdAt) and the 90-day TTL on ``finishedAt``;
* ``service_desk_gaps``: the list lookup (tenantId, status, createdAt) and the 90-day TTL;
* ``knowledge_docs``: the Help desk lookup and the unique partial ``one_starter_copy`` (tenantId, starterKey),
  which makes the starter copy safe against a double click or two administrators;
* ``tickets``: the tray list (``tray_list``) and the return sweep (``desk_return_due``).

A tenant with no ``serviceDesk`` setting keeps reading as Drafts only, and a comment with no ``visibility`` keeps
reading as staff-only, so no document needs a new field. ``create_index`` with an unchanged definition is a no-op,
so a second run changes nothing. The desk worker makes the two unique indexes again before every pass when they
are missing, so this migration is the first, not the only, place they are created.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Service desk indexes (Phase 85). Indexes only, nothing is backfilled."

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    from service_desk import store

    await store.ensure_indexes(db)
    logger.info("migration 032: service desk indexes ensured")
