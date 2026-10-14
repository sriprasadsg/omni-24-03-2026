"""Limited-use install keys (spec C4).

An install key enrolls new agents into one tenant. It can be capped (``maxUses``),
time-boxed (``expiresAt``), revoked, and can put the agents it enrolls into a default
agent group. Only a SHA-256 of the key is stored; the key itself is shown once, at
creation. Each new enrollment claims one use with a conditional atomic increment, so
concurrent installs never exceed the cap; an enrollment whose key cannot be used is
held Pending with reason ``key_exhausted``.

Every tenant's original ``registrationKey`` (shipped in installers) becomes a "Legacy
key" row with no cap, so current installers keep working until a platform user revokes
it. That row is valid only while it still matches the tenant's registrationKey. The
registrationKey also stays the X-Tenant-Key credential of the routes that accept one
(agent_auth.verify_agent_key, tunnel and PowerShell-evidence endpoints, tenant key
lookup); revoking the legacy row stops new enrollments only, and enrolled agents use
their own tokens either way.
"""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

LEGACY_KEY_NAME = "Legacy key"
_PROJECTION = {"_id": 0, "keyHash": 0}


def _raw(db):
    return getattr(db, "_db", db)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def problem(row: Dict[str, Any], now_iso: Optional[str] = None) -> Optional[str]:
    """Why the key cannot enroll an agent right now, or None."""
    now_iso = now_iso or _now_iso()
    if row.get("revokedAt"):
        return "revoked"
    if row.get("expiresAt") and row["expiresAt"] <= now_iso:
        return "expired"
    if isinstance(row.get("maxUses"), int) and row.get("uses", 0) >= row["maxUses"]:
        return "exhausted"
    return None


async def _legacy_row(raw, tenant: Dict[str, Any], key: str) -> Dict[str, Any]:
    """The tenant's Legacy key row, created on first use (tenants made after migration 013)."""
    row = {
        "id": f"ek-{uuid.uuid4().hex[:16]}", "tenantId": tenant["id"], "name": LEGACY_KEY_NAME,
        "keyHash": hash_key(key), "prefix": key[:8], "legacy": True, "maxUses": None, "uses": 0,
        "expiresAt": None, "defaultGroupId": None, "revokedAt": None, "createdBy": "migration",
        "createdAt": _now_iso(),
    }
    try:
        await raw.enrollment_keys.insert_one(dict(row))
    except DuplicateKeyError:  # created concurrently
        return await raw.enrollment_keys.find_one({"keyHash": row["keyHash"]})
    return row


async def resolve(db, key: Optional[str]) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """(tenant, key row) for an install key, whatever the row's state; None if unknown."""
    if not isinstance(key, str) or not key:
        return None
    raw = _raw(db)
    row = await raw.enrollment_keys.find_one({"keyHash": hash_key(key)})
    if row:
        tenant = await raw.tenants.find_one({"id": row["tenantId"]})
        if not tenant:
            return None
        if row.get("legacy") and tenant.get("registrationKey") != key:
            return None  # the tenant's key was replaced; the old one is no key at all
        return tenant, row
    tenant = await raw.tenants.find_one({"registrationKey": key})
    if not tenant:
        return None
    return tenant, await _legacy_row(raw, tenant, key)


async def claim_use(db, row: Dict[str, Any]) -> bool:
    """Atomically take one use of the key; False when it is revoked, expired or used up."""
    now = _now_iso()
    claimed = await _raw(db).enrollment_keys.find_one_and_update(
        {"id": row["id"], "revokedAt": None,
         "$and": [{"$or": [{"expiresAt": None}, {"expiresAt": {"$gt": now}}]},
                  {"$or": [{"maxUses": None}, {"$expr": {"$lt": ["$uses", "$maxUses"]}}]}]},
        {"$inc": {"uses": 1}, "$set": {"lastUsedAt": now}},
        return_document=ReturnDocument.AFTER,
    )
    return claimed is not None


async def release_use(db, row: Dict[str, Any]) -> None:
    """Give a use back after an enrollment that claimed it failed to be recorded."""
    await _raw(db).enrollment_keys.update_one({"id": row["id"], "uses": {"$gt": 0}}, {"$inc": {"uses": -1}})


async def create(db, tenant_id: str, name: str, actor: str, max_uses: Optional[int] = None,
                 expires_at: Optional[str] = None, default_group_id: Optional[str] = None) -> Dict[str, Any]:
    """A new key. The returned dict carries the plaintext ``key``: show it once, never store it."""
    key = f"ek_{secrets.token_urlsafe(24)}"
    row = {
        "id": f"ek-{uuid.uuid4().hex[:16]}", "tenantId": tenant_id, "name": name, "keyHash": hash_key(key),
        "prefix": key[:8], "legacy": False, "maxUses": max_uses, "uses": 0, "expiresAt": expires_at,
        "defaultGroupId": default_group_id, "revokedAt": None, "createdBy": actor, "createdAt": _now_iso(),
    }
    await _raw(db).enrollment_keys.insert_one(dict(row))
    row.pop("keyHash")
    return {**row, "key": key}


async def revoke(db, tenant_id: str, key_id: str, actor: str) -> Optional[Dict[str, Any]]:
    """Stop the key enrolling new agents (idempotent). None when no such key in the tenant."""
    raw = _raw(db)
    await raw.enrollment_keys.update_one(
        {"id": key_id, "tenantId": tenant_id, "revokedAt": None},
        {"$set": {"revokedAt": _now_iso(), "revokedBy": actor}})
    return await raw.enrollment_keys.find_one({"id": key_id, "tenantId": tenant_id}, _PROJECTION)


async def list_keys(db, tenant_id: str) -> List[Dict[str, Any]]:
    """The tenant's keys, newest first, each with its current ``problem`` (or None)."""
    rows = await _raw(db).enrollment_keys.find({"tenantId": tenant_id}, _PROJECTION) \
        .sort("createdAt", -1).to_list(length=500)
    now = _now_iso()
    for row in rows:
        row["problem"] = problem(row, now)
    return rows


def public(row: Dict[str, Any]) -> Dict[str, Any]:
    """A key row without its hash."""
    return {k: v for k, v in row.items() if k not in ("_id", "keyHash")}
