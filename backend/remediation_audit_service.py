"""Append-only remediation audit trail (Phase 53-03/53-04, AUTO-04).

Only `write_audit` (insert) and `list_audit` (read) are exposed — there is
no update/delete function anywhere in this module, so a record, once
written, can never be altered or removed by anything importing it.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def write_audit(db, tenant_id: str, record: Dict[str, Any]) -> str:
    """Inserts one immutable audit record. Never updates an existing one —
    each transition (selected/dispatched/verified/override) is its own
    fresh document."""
    doc = dict(record)
    doc.setdefault("tenantId", tenant_id)
    doc.setdefault("ts", datetime.now(timezone.utc).isoformat())
    result = await db.remediation_audit.insert_one(doc)
    return str(result.inserted_id)


async def list_audit(
    db,
    tenant_id: str,
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"tenantId": tenant_id}
    if filters:
        query.update(filters)
    cursor = db.remediation_audit.find(query, {"_id": 0}).sort("ts", -1).limit(limit)
    return await cursor.to_list(length=limit)
