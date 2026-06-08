"""
IP Ban Service
Persistent IP block list with in-memory cache for fast middleware checks.
Auto-ban is triggered by UEBA on critical-risk events.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from database import get_database

logger = logging.getLogger(__name__)

# In-process cache: ip → (banned: bool, expires_at: float)
_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL = 60  # seconds


def _cache_get(ip: str) -> Optional[bool]:
    entry = _cache.get(ip)
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    _cache.pop(ip, None)
    return None


def _cache_set(ip: str, banned: bool) -> None:
    _cache[ip] = (banned, time.monotonic() + _CACHE_TTL)


async def is_banned(ip: str, tenant_id: Optional[str] = None) -> bool:
    """Return True if the IP is on the platform-wide or tenant ban list."""
    cached = _cache_get(ip)
    if cached is not None:
        return cached

    db = get_database()
    query: dict = {"ip": ip, "active": True}
    # Ban can be platform-wide (no tenant_id) or tenant-specific
    if tenant_id:
        query = {"ip": ip, "active": True, "$or": [{"tenant_id": None}, {"tenant_id": tenant_id}]}
    doc = await db.ip_bans.find_one(query, {"_id": 0, "ip": 1})
    banned = doc is not None
    _cache_set(ip, banned)
    return banned


async def ban_ip(
    ip: str,
    reason: str,
    tenant_id: Optional[str] = None,
    banned_by: str = "system",
    auto: bool = False,
    expires_hours: Optional[int] = None,
) -> dict:
    """Add an IP to the ban list. Returns the created document."""
    db = get_database()
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(hours=expires_hours)).isoformat() if expires_hours else None
    doc = {
        "ip": ip,
        "reason": reason,
        "tenant_id": tenant_id,
        "banned_by": banned_by,
        "auto": auto,
        "active": True,
        "banned_at": now.isoformat(),
        "expires_at": expires_at,
    }
    await db.ip_bans.update_one(
        {"ip": ip, "tenant_id": tenant_id},
        {"$set": doc},
        upsert=True,
    )
    _cache_set(ip, True)
    logger.warning("IP BANNED: %s | reason=%s | auto=%s | tenant=%s", ip, reason, auto, tenant_id)
    return doc


async def unban_ip(ip: str, tenant_id: Optional[str] = None) -> bool:
    """Deactivate the ban on an IP. Returns True if a document was updated."""
    db = get_database()
    query: dict = {"ip": ip}
    if tenant_id:
        query["tenant_id"] = tenant_id
    result = await db.ip_bans.update_many(query, {"$set": {"active": False}})
    _cache_set(ip, False)
    return result.modified_count > 0


async def list_bans(tenant_id: Optional[str] = None, active_only: bool = True) -> list:
    """Return all bans, optionally filtered by tenant and active status."""
    db = get_database()
    query: dict = {}
    if tenant_id:
        query["$or"] = [{"tenant_id": None}, {"tenant_id": tenant_id}]
    if active_only:
        query["active"] = True
    docs = await db.ip_bans.find(query, {"_id": 0}).sort("banned_at", -1).to_list(500)
    return docs


async def expire_bans() -> int:
    """Deactivate bans whose expires_at has passed. Returns count expired."""
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    result = await db.ip_bans.update_many(
        {"active": True, "expires_at": {"$lte": now, "$ne": None}},
        {"$set": {"active": False}},
    )
    if result.modified_count:
        _cache.clear()
    return result.modified_count
