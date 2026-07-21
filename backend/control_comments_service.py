"""Control comment threads (Phase 42, CMT-01).

Stores comments in a dedicated `control_comments` collection — NOT appended
onto any shared/tenant-exempt controls document. `control_comments` is
absent from database.py's tenant-isolation exemption allowlists, so every
read/write here is automatically scoped by TenantIsolatedCollection; no
manual tenantId filter is added in this module.
"""
import uuid
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def add_comment(db, control_id: str, author: str, text: str) -> dict:
    """Insert a new comment for the given control_id and return it."""
    comment = {
        "id": str(uuid.uuid4()),
        "control_id": control_id,
        "author": author,
        "text": text,
        "created_at": _now_iso(),
    }
    await db.control_comments.insert_one(dict(comment))
    return comment


async def list_comments(db, control_id: str) -> list:
    """Return all comments for a control_id, oldest first."""
    cursor = db.control_comments.find({"control_id": control_id}, {"_id": 0})
    return await cursor.sort("created_at", 1).to_list(length=200)
