"""Control comment threads (Phase 42, CMT-01).

Stores comments in a dedicated `control_comments` collection — NOT appended
onto any shared/tenant-exempt controls document. `control_comments` is
absent from database.py's tenant-isolation exemption allowlists, so every
read/write here is automatically scoped by TenantIsolatedCollection; no
manual tenantId filter is added in this module.
"""
import re
import uuid
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_mention_tokens(text: str) -> list:
    """Extract plain-identifier @tokens from comment text (D-04 / Pitfall 3).

    Deliberately NOT the tickets email-shaped regex
    (`r'@([\\w.+-]+@[\\w.+-]+\\.[a-z]+)'`), which requires a full email after
    `@` and would match nothing for a plain `@bob` mention.
    """
    return re.findall(r'@([\w.-]+)', text)


async def resolve_mentions(db, text: str) -> list:
    """Resolve @token strings extracted from `text` to recipient emails.

    Resolution order (RESEARCH.md Assumption A1): exact `username` match,
    then email-local-part match, then case-insensitive exact `name` match.
    Unresolved tokens are silently skipped — this never raises, so a typo'd
    or unknown @mention never fails the comment POST. Resolved emails are
    de-duplicated so a token repeated in one comment notifies once.
    """
    emails = []
    seen = set()
    for token in extract_mention_tokens(text):
        escaped = re.escape(token)
        user = await db.users.find_one({"username": token})
        if not user:
            user = await db.users.find_one({"email": {"$regex": f"^{escaped}@"}})
        if not user:
            user = await db.users.find_one({"name": {"$regex": f"^{escaped}$", "$options": "i"}})
        if user and user.get("email") and user["email"] not in seen:
            seen.add(user["email"])
            emails.append(user["email"])
    return emails


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
