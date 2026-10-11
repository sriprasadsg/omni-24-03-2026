"""
Secure file sharing — uploaded files behind time-limited, optionally
password-protected, access-counted links.

Shares live in Mongo (file_shares) through the tenant-isolated handle; the files
themselves are stored privately under FILE_SHARE_DIR (default backend/data/
file_shares, gitignored). Replaces an in-memory service that was seeded with a
demo share and only stored a URL string, so nothing real was ever shared.
"""
import os
import pathlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt

SHARE_DIR = os.getenv("FILE_SHARE_DIR", "") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "file_shares"
)
os.makedirs(SHARE_DIR, mode=0o700, exist_ok=True)

MAX_FILE_BYTES = 20 * 1024 * 1024

# Fields never returned to clients
_PRIVATE_FIELDS = {"_id", "password_hash", "stored_name"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def public_view(share: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in share.items() if k not in _PRIVATE_FIELDS}


def stored_path(stored_name: str) -> pathlib.Path:
    root = pathlib.Path(SHARE_DIR).resolve()
    path = (root / stored_name).resolve()
    if not str(path).startswith(str(root) + os.sep):
        raise ValueError("Invalid stored file name")
    return path


async def create_share(
    db, *, file_name: str, contents: bytes, mimetype: str, created_by: str, tenant_id: Optional[str],
    expires_in_days: int, password: Optional[str], max_accesses: Optional[int],
) -> Dict[str, Any]:
    share_id = f"share-{uuid.uuid4().hex[:12]}"
    safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", os.path.basename(file_name)) or "file"
    stored_name = f"{share_id}_{safe_name}"
    with open(stored_path(stored_name), "wb") as fh:
        fh.write(contents)
    share = {
        "id": share_id,
        "file_name": os.path.basename(file_name) or "file",
        "stored_name": stored_name,
        "size": len(contents),
        "mimetype": mimetype,
        "created_by": created_by,
        "tenantId": tenant_id,
        "created_at": _now().isoformat(),
        "expires_at": (_now() + timedelta(days=expires_in_days)).isoformat(),
        "access_token": secrets.token_urlsafe(24),
        "password_protected": bool(password),
        "password_hash": bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8") if password else None,
        "access_count": 0,
        "max_accesses": max_accesses,
        "is_active": True,
    }
    await db.file_shares.insert_one(dict(share))
    return public_view(share)


async def list_shares(db, created_by: str) -> List[Dict[str, Any]]:
    docs = await db.file_shares.find({"created_by": created_by, "is_active": True}, {"_id": 0}).to_list(length=500)
    return [public_view(d) for d in docs]


async def revoke_share(db, share_id: str, created_by: str) -> bool:
    share = await db.file_shares.find_one({"id": share_id, "created_by": created_by, "is_active": True}, {"_id": 0})
    if not share:
        return False
    await db.file_shares.update_one({"id": share_id}, {"$set": {"is_active": False}})
    try:
        stored_path(share["stored_name"]).unlink(missing_ok=True)
    except ValueError:
        pass
    return True


async def open_share(raw_db, token: str, password: Optional[str]) -> Dict[str, Any]:
    """Check a recipient's token/password and count the access.

    Runs before any sign-in, so it reads the raw (non tenant-scoped) database by
    the share's unique token. Returns {"share": ...} or {"error": ..., "status": ...}.
    """
    share = await raw_db.file_shares.find_one({"access_token": token, "is_active": True}, {"_id": 0})
    if not share or not secrets.compare_digest(share["access_token"], token):
        return {"error": "This link is invalid or has been revoked", "status": 404}
    if share.get("expires_at") and _now().isoformat() > share["expires_at"]:
        return {"error": "This link has expired", "status": 410}
    if share.get("password_protected"):
        if not password or not bcrypt.checkpw(password.encode("utf-8"), share["password_hash"].encode("utf-8")):
            return {"error": "Password required", "status": 403, "password_required": True}
    flt: Dict[str, Any] = {"id": share["id"]}
    if share.get("max_accesses"):
        # Atomic check-and-increment so parallel downloads can't exceed the limit
        flt["access_count"] = {"$lt": share["max_accesses"]}
    result = await raw_db.file_shares.update_one(flt, {"$inc": {"access_count": 1}})
    if getattr(result, "modified_count", 1) == 0:
        return {"error": "This link has reached its download limit", "status": 410}
    return {"share": share}
