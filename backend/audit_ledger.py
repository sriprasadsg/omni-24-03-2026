"""The one audit writer (spec C5).

Every audit entry — the request middleware's, the explicit events' (login, logout,
exports, licensing decisions...) and the two legacy writers' (audit_service,
audit.log_event, now adapters) — goes through ``record``, so ``audit_logs`` holds one
schema.

Each tenant's entries form a hash chain: entry ``seq`` n carries ``previousHash`` =
hash of entry n-1. The chain head lives in ``audit_chain_heads`` and is advanced with a
compare-and-swap on its ``seq``, so concurrent writers get contiguous seq numbers and
never fork the chain (the old writer read "the latest entry by timestamp", which two
concurrent writes could both see). Retention purges keep the last purged seq + hash in
``audit_chain_checkpoints`` so verification still starts from a known link.

A write failure never fails the request: the entry goes to an NDJSON spool
(AUDIT_SPOOL_PATH, default logs/audit-spool.ndjson), an ERROR is logged and the platform
is alerted (at most every 10 min); ``replay_spool`` writes spooled entries back.
"""
import asyncio
import hashlib
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

GENESIS = "0" * 64
DEFAULT_RETENTION_DAYS = 365
_HASH_EXCLUDE = ("_id", "hash")
_CAS_ATTEMPTS = 400
_ALERT_EVERY_S = 600
_last_alert = 0.0


def _raw_db():
    import database  # resolved per call, so a patched get_database is honoured
    db = database.get_database()
    raw = getattr(db, "_db", None)
    return raw if raw is not None and hasattr(raw, "audit_logs") else db


def spool_path() -> Path:
    return Path(os.getenv("AUDIT_SPOOL_PATH") or Path(__file__).parent.parent / "logs" / "audit-spool.ndjson")


def entry_hash(entry: Dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON of every field but the hash itself."""
    body = {k: v for k, v in entry.items() if k not in _HASH_EXCLUDE}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build(action: str, tenant_id: Optional[str], *, actor: Optional[Dict[str, Any]] = None,
          outcome: str = "success", **fields: Any) -> Dict[str, Any]:
    """An unchained entry. ``actor`` is {userId, email, role, tenantId, platformTier}."""
    if not tenant_id:  # callers without a tenant write to the request's tenant, as before
        from tenant_context import get_tenant_id
        tenant_id = get_tenant_id()
    entry = {"id": str(uuid.uuid4()), "timestamp": _now(), "tenantId": tenant_id or "platform-admin",
             "action": action, "outcome": outcome, "actor": actor or {}}
    entry.update({k: v for k, v in fields.items() if v is not None})
    # Fields the existing audit timeline UI reads.
    entry.setdefault("userName", (actor or {}).get("email") or (actor or {}).get("userId") or "system")
    entry.setdefault("resourceType", fields.get("catalogue") or "")
    entry.setdefault("resourceId", fields.get("resourceId") or "")
    return entry


_indexed: set = set()


async def _ensure_indexes(db) -> None:
    """The uniqueness the chain relies on (same names/options as migration 014), created
    once per database handle so a missed migration cannot let two heads fork a chain."""
    if id(db) in _indexed:
        return
    try:
        await db.audit_chain_heads.create_index("tenantId", unique=True, name="tenant_unique")
        await db.audit_logs.create_index([("tenantId", 1), ("seq", 1)], unique=True, name="tenant_seq_unique",
                                         partialFilterExpression={"seq": {"$exists": True}})
        _indexed.add(id(db))
    except Exception as exc:  # e.g. a test double without create_index
        logger.debug("Audit chain indexes not ensured: %s", exc)


async def _chain(db, entry: Dict[str, Any]) -> None:
    """Assign seq/previousHash/hash by advancing the tenant's chain head (CAS)."""
    await _ensure_indexes(db)
    heads = db.audit_chain_heads
    tenant = entry["tenantId"]
    for attempt in range(_CAS_ATTEMPTS):
        head = await heads.find_one({"tenantId": tenant})
        seq, prev = (head["seq"], head["hash"]) if head else (0, None)
        if prev is None:
            checkpoint = await db.audit_chain_checkpoints.find_one({"tenantId": tenant})
            seq, prev = (checkpoint["seq"], checkpoint["hash"]) if checkpoint else (0, GENESIS)
        entry["seq"], entry["previousHash"] = seq + 1, prev
        entry["hash"] = entry_hash(entry)
        if head:
            res = await heads.update_one({"tenantId": tenant, "seq": seq},
                                         {"$set": {"seq": seq + 1, "hash": entry["hash"]}})
            if res.modified_count == 1:
                return
        else:
            try:
                await heads.insert_one({"tenantId": tenant, "seq": seq + 1, "hash": entry["hash"]})
                return
            except DuplicateKeyError:
                pass
        await asyncio.sleep(random.uniform(0, 0.002 * min(attempt + 1, 20)))
    raise RuntimeError(f"audit chain head for {tenant} is too contended")


def _spool(entry: Dict[str, Any], error: Exception) -> None:
    global _last_alert
    try:
        path = spool_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in entry.items() if k != "_id"}, default=str) + "\n")
    except Exception as exc:  # last resort: the log line
        logger.error("AUDIT ENTRY LOST (spool failed: %s): %s", exc, entry)
    logger.error("Audit write failed (%s); entry %s spooled to %s", error, entry.get("id"), spool_path())
    if time.monotonic() - _last_alert > _ALERT_EVERY_S:
        _last_alert = time.monotonic()
        asyncio.ensure_future(_alert_write_failing(str(error)))


async def _alert_write_failing(error: str) -> None:
    try:
        import pending_agents
        await pending_agents.post_to_recipients(
            _raw_db(), {"id": "platform-admin"}, "Audit log writes are failing",
            f"Audit entries are being spooled to {spool_path()} and will be replayed: {error[:200]}",
            "critical", {"event": "platform.audit_write_failing"})
    except Exception as exc:
        logger.error("Could not raise platform.audit_write_failing: %s", exc)


async def record(entry: Dict[str, Any], db=None) -> Dict[str, Any]:
    """Chain and store one entry; never raises. A chain head that cannot be advanced
    stores the entry unchained (chainError, reported by verify) rather than losing it;
    a failed insert spools it for replay."""
    try:
        db = db if db is not None else _raw_db()
    except Exception as exc:
        _spool(entry, exc)
        return entry
    if "hash" not in entry:
        try:
            await _chain(db, entry)
        except Exception as exc:
            logger.error("Audit chain unavailable (%s); entry %s stored unchained", exc, entry.get("id"))
            for key in ("seq", "previousHash", "hash"):
                entry.pop(key, None)
            entry["chainError"] = str(exc)[:200]
    try:
        await db.audit_logs.insert_one(entry)
    except Exception as exc:
        entry.pop("_id", None)
        _spool(entry, exc)
    entry.pop("_id", None)
    return entry


def _unwrap(db):
    """The raw handle behind the tenant wrapper; anything else is used as given."""
    from database import TenantIsolatedDatabase
    return db._db if isinstance(db, TenantIsolatedDatabase) else db


_LEGACY_ACTOR_KEYS = ("performed_by", "actor", "user", "username", "user_id", "userName", "admin")


async def record_legacy(db, doc: Dict[str, Any]) -> Dict[str, Any]:
    """For code that used to insert straight into audit_logs: keeps the document's own
    fields, adds the ledger's (actor, outcome, chain) and records it through ``record``."""
    tenant = doc.get("tenantId") or doc.get("tenant_id")
    actor = doc.get("actor") if isinstance(doc.get("actor"), dict) else \
        {"email": next((str(doc[k]) for k in _LEGACY_ACTOR_KEYS if doc.get(k)), "system")}
    fields = {k: v for k, v in doc.items()
              if k not in ("_id", "action", "actor", "tenantId", "tenant_id", "outcome", "timestamp", "db")}
    entry = build(str(doc.get("action") or doc.get("event") or "legacy.event"), tenant, actor=actor,
                  outcome=str(doc.get("outcome") or "success"), **fields)
    if doc.get("id"):
        entry["id"] = doc["id"]
    if doc.get("timestamp") is not None:
        entry["originalTimestamp"] = doc["timestamp"]
    return await record(entry, db=_unwrap(db) if db is not None else None)


async def event(action: str, tenant_id: Optional[str], *, actor: Optional[Dict[str, Any]] = None,
                outcome: str = "success", db=None, **fields: Any) -> Dict[str, Any]:
    """Record an explicit event (login.success, export.audit_log, ...)."""
    return await record(build(action, tenant_id, actor=actor, outcome=outcome, **fields), db=db)


async def replay_spool(db=None) -> int:
    """Write spooled entries back (idempotent by id); returns how many were written."""
    db = db if db is not None else _raw_db()
    path = spool_path()
    if not path.exists() or path.stat().st_size == 0:
        return 0
    work = path.with_suffix(".replaying")
    path.replace(work)
    written, keep = 0, []
    for line in work.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        try:
            if await db.audit_logs.find_one({"id": entry["id"]}, {"_id": 1}):
                continue
            if "hash" not in entry:
                await _chain(db, entry)
            await db.audit_logs.insert_one(entry)
            written += 1
        except Exception as exc:
            logger.warning("Audit spool replay deferred (%s)", exc)
            keep.append(line)
    if keep:
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(keep) + "\n")
    work.unlink(missing_ok=True)
    if written:
        logger.info("Replayed %d spooled audit entries", written)
    return written


async def verify(tenant_id: str, db=None, limit: int = 100_000) -> Dict[str, Any]:
    """Walk the tenant's chain by seq from its checkpoint (or genesis)."""
    db = db if db is not None else _raw_db()
    checkpoint = await db.audit_chain_checkpoints.find_one({"tenantId": tenant_id})
    expected_seq, expected_prev = (checkpoint["seq"] + 1, checkpoint["hash"]) if checkpoint else (1, GENESIS)
    broken: List[Dict[str, Any]] = []
    total = 0
    cursor = db.audit_logs.find({"tenantId": tenant_id, "seq": {"$exists": True}}, {"_id": 0}).sort("seq", 1).limit(limit)
    async for entry in cursor:
        total += 1
        if entry["seq"] != expected_seq:
            broken.append({"seq": entry["seq"], "reason": f"gap: expected seq {expected_seq}"})
        if entry.get("previousHash") != expected_prev:
            broken.append({"seq": entry["seq"], "reason": "previous hash mismatch"})
        if entry_hash(entry) != entry.get("hash"):
            broken.append({"seq": entry["seq"], "reason": "entry altered (hash mismatch)"})
        expected_seq, expected_prev = entry["seq"] + 1, entry.get("hash")
    legacy = await db.audit_logs.count_documents({"tenantId": tenant_id, "seq": {"$exists": False}})
    return {"valid": not broken, "total_records": total, "legacy_unchained": legacy,
            "broken_links": broken[:100], "checkpoint": (checkpoint or {}).get("seq")}


async def purge_expired(db=None, now: Optional[datetime] = None) -> int:
    """Delete entries past each tenant's retention (tenants.auditRetentionDays, default 365),
    oldest first, recording the last purged link as the chain checkpoint."""
    db = db if db is not None else _raw_db()
    now = now or datetime.now(timezone.utc)
    purged = 0
    async for tenant in db.tenants.find({}, {"_id": 0, "id": 1, "auditRetentionDays": 1}):
        days = tenant.get("auditRetentionDays") if isinstance(tenant.get("auditRetentionDays"), int) else DEFAULT_RETENTION_DAYS
        cutoff = (now - timedelta(days=days)).isoformat()
        last = await db.audit_logs.find_one({"tenantId": tenant["id"], "seq": {"$exists": True},
                                             "timestamp": {"$lt": cutoff}}, sort=[("seq", -1)])
        if last:
            await db.audit_chain_checkpoints.update_one(
                {"tenantId": tenant["id"]}, {"$set": {"seq": last["seq"], "hash": last["hash"], "purgedAt": now.isoformat()}},
                upsert=True)
            res = await db.audit_logs.delete_many({"tenantId": tenant["id"], "seq": {"$lte": last["seq"]}})
            purged += res.deleted_count
        res = await db.audit_logs.delete_many({"tenantId": tenant["id"], "seq": {"$exists": False},
                                               "timestamp": {"$lt": cutoff}})
        purged += res.deleted_count
    return purged
