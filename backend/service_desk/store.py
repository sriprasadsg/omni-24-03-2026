"""Desk collections and every desk index (migration 032 in 85-17 calls ``ensure_indexes``).

Everything goes through the raw handle (``autonomous_ops.scope.raw``) with an explicit tenantId.
"""
from autonomous_ops.scope import raw

NINETY_DAYS = 7776000       # seconds: finished jobs and gap rows are kept 90 days


def jobs(db):
    """The desk's queue of attempts (one per ticket)."""
    return raw(db).service_desk_jobs


def gaps(db):
    """Tickets the desk could not answer for lack of an article (the Knowledge Base gap list)."""
    return raw(db).service_desk_gaps


def runtime_settings(db):
    """The collection holding the operator-measured model timings (system_settings, type service_desk_runtime)."""
    return raw(db).system_settings


async def ensure_indexes(db) -> None:
    """Create every desk index. Idempotent: creating an index that already exists is a no-op."""
    handle = raw(db)
    await handle.service_desk_jobs.create_index([("tenantId", 1), ("ticketId", 1)], unique=True,
                                                name="one_attempt_per_ticket")
    await handle.service_desk_jobs.create_index([("state", 1), ("createdAt", 1)], name="state_created")
    await handle.service_desk_jobs.create_index([("finishedAt", 1)], expireAfterSeconds=NINETY_DAYS,
                                                name="finished_ttl")
    await handle.service_desk_gaps.create_index([("tenantId", 1), ("status", 1), ("createdAt", 1)],
                                                name="tenant_status_created")
    await handle.service_desk_gaps.create_index([("createdAt", 1)], expireAfterSeconds=NINETY_DAYS,
                                                name="created_ttl")
    await handle.knowledge_docs.create_index([("tenantId", 1), ("helpdesk", 1)], name="tenant_helpdesk")
    await handle.knowledge_docs.create_index([("tenantId", 1), ("starterKey", 1)], unique=True,
                                             partialFilterExpression={"starterKey": {"$type": "string"}},
                                             name="one_starter_copy")
    await handle.tickets.create_index([("tenantId", 1), ("agent_id", 1), ("raised_via", 1), ("created_at", 1)],
                                      name="tray_list")
    await handle.tickets.create_index([("tenantId", 1), ("desk.phase", 1), ("desk.postedAt", 1)],
                                      partialFilterExpression={"desk.postedAt": {"$type": "date"}},
                                      name="desk_return_due")
