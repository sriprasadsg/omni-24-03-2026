"""Gap rows: the questions the desk could not answer for want of an article (D-26).

One row per ticket and reason, written only when a ticket is handed to a person because no article
matched or the ticket was not in English. The text is the cleaned question (no markup, links or
addresses) cut to ``GAP_TEXT_CAP`` characters, and the rows expire after 90 days (store.ensure_indexes).
85-15 adds the grouping, listing, dismiss and restore in this module.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from service_desk import GAP_REASONS, GAP_TEXT_CAP
from service_desk import sanitize, store


async def record(db, tenant_id: str, *, ticket_id: str, ticket_number: Optional[str], text: str, reason: str,
                 now: Optional[datetime] = None) -> bool:
    """Keep one gap row. True when this call wrote it; False when the row already existed or the question
    is empty once cleaned. A reason outside ``GAP_REASONS`` raises ValueError. Idempotent: the upsert key
    is the tenant, the ticket and the reason."""
    if reason not in GAP_REASONS:
        raise ValueError(f"not a gap reason: {reason!r}")
    question = sanitize.clean_text(text, GAP_TEXT_CAP)
    if not question:
        return False
    created = now or datetime.now(timezone.utc)
    created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
    document = {"id": "SDG-" + uuid.uuid4().hex, "tenantId": tenant_id, "ticketId": ticket_id,
                "ticketNumber": ticket_number, "text": question, "reason": reason, "createdAt": created,
                "status": "open"}
    result = await store.gaps(db).update_one(
        {"tenantId": tenant_id, "ticketId": ticket_id, "reason": reason}, {"$setOnInsert": document}, upsert=True)
    return result.upserted_id is not None
