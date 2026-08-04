"""Append-only assignment-history module (Phase 57, ITAM-LIFE-04).

Only `write_history` (insert) and `list_history` (read) are exposed — this is the
entire public surface of this module. There is no update/delete/edit/purge/correction
function anywhere in it, so a written assignment-history record can never be altered
or removed by anything that imports this module. A correction is always a new
appended entry, never a rewrite of an existing one — that absence is the append-only
guarantee behind this plan's first authored prohibition (assignment history must
never gain an alter/remove path, including a TTL index).

Modelled 1:1 on remediation_audit_service.py, minus its OCSF push side-effect.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


async def write_history(db, tenant_id: str, record: Dict[str, Any]) -> str:
    """Inserts one immutable assignment-history record.

    Copies `record`, sets a freshly generated `id`, `setdefault`s `tenantId` to the
    passed tenant and `ts` to the current UTC ISO timestamp (a caller-supplied `ts`
    is preserved, never overwritten), inserts into `db.assignment_history`, and
    returns the generated `id`.
    """
    doc = dict(record)
    doc["id"] = f"ah-{uuid.uuid4().hex[:8]}"
    doc.setdefault("tenantId", tenant_id)
    doc.setdefault("ts", _now_iso())
    await db.assignment_history.insert_one(doc)
    return doc["id"]


async def list_history(
    db, tenant_id: str, asset_id: str, limit: int = 100
) -> List[Dict[str, Any]]:
    """Returns one asset's assignment-history entries, newest first.

    Sort is `ts` descending with `_id` descending as the tiebreak, so entries
    sharing an identical `ts` still come back in a stable, repeatable order. This
    function is deliberately per-asset by construction — no arbitrary-filter
    variant exists here.
    """
    cursor = (
        db.assignment_history.find({"tenantId": tenant_id, "assetId": asset_id}, {"_id": 0})
        .sort([("ts", -1), ("_id", -1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)
