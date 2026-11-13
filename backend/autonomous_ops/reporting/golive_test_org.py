"""The go-live test organization (Phase 86, plan 86-14, GATE-09, D-23).

One Super Admin-designated organization may leave shadow mode before the five live checks are recorded and
without the seven-day observation, so the checks that need real actions can be walked. The designation is a
single platform document with a fixed id in its own collection, so at most one organization is marked by
construction (a second insert raises). This module only stores, reads and removes that one document; the
gate that honours it is ``golive.lift_blockers``. It never touches the go-live evidence. Raw Mongo handle,
explicit fields, no model call.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from pymongo.errors import DuplicateKeyError

from autonomous_ops.scope import raw

from . import GOLIVE_TEST_ORG, TEST_ORG_DOC_ID


class AlreadyMarked(Exception):
    """A test organization is already marked; ``current`` is that mark."""

    def __init__(self, current: Optional[Dict[str, Any]]):
        super().__init__("a test organization is already marked")
        self.current = current


def _coll(db):
    return raw(db)[GOLIVE_TEST_ORG]


async def current(db) -> Optional[Dict[str, Any]]:
    """The mark: {tenantId, tenantName, markedBy, markedAt}, or None when no organization is marked."""
    return await _coll(db).find_one({"_id": TEST_ORG_DOC_ID}, {"_id": 0})


async def mark(db, tenant_id: str, tenant_name: str, actor: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """Mark one organization. ``AlreadyMarked`` (carrying the existing mark) when one is already marked."""
    doc = {"tenantId": tenant_id, "tenantName": tenant_name,
           "markedBy": {"username": str(actor.get("username") or "unknown"),
                        "display": str(actor.get("display") or actor.get("username") or "unknown")},
           "markedAt": now}
    try:
        await _coll(db).insert_one({"_id": TEST_ORG_DOC_ID, **doc})
    except DuplicateKeyError as exc:
        raise AlreadyMarked(await current(db)) from exc
    return doc


async def clear(db, tenant_id: str) -> bool:
    """Remove the mark, only when it is this organization's. True when a mark was removed."""
    result = await _coll(db).delete_one({"_id": TEST_ORG_DOC_ID, "tenantId": tenant_id})
    return result.deleted_count == 1
