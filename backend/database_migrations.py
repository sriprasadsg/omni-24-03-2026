import logging
import uuid as _uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from pymongo.errors import DuplicateKeyError
from database import get_database
from tenant_context import set_tenant_id, get_tenant_id

logger = logging.getLogger("database_migrations")

_MIGRATION_LOCK_TTL_SECONDS = 300


async def _acquire_migration_lock(db, name: str) -> Optional[str]:
    """Best-effort distributed lock so only one replica runs a given
    startup migration when horizontally scaled (DB-F08, 2026-08-25 audit).
    These migrations are individually idempotent (each write is by _id, so
    concurrent replicas re-doing the same update/delete isn't corrupting),
    but with no lock every replica re-scans and re-writes the same backlog
    on every restart — wasted work that grows with replica count, and log
    noise that makes real errors harder to spot.

    Returns a lock token to pass to _release_migration_lock() on success,
    or None if another replica currently holds the lock. Self-healing: a
    crashed holder's lock naturally becomes re-acquirable once
    _MIGRATION_LOCK_TTL_SECONDS elapses — no separate crash-recovery path
    needed, consistent with the "self-healing migration" design already
    used by the migrations themselves. Uses db._db (raw, unwrapped)
    deliberately: this lock is cross-tenant/global by nature, like the
    collections these migrations themselves operate on.
    """
    now = datetime.now(timezone.utc)
    token = str(_uuid.uuid4())
    try:
        await db._db._migration_locks.find_one_and_update(
            {"_id": name, "expiresAt": {"$lt": now}},
            {"$set": {"expiresAt": now + timedelta(seconds=_MIGRATION_LOCK_TTL_SECONDS), "token": token}},
            upsert=True,
        )
        return token
    except DuplicateKeyError:
        return None


async def _release_migration_lock(db, name: str, token: str) -> None:
    """Release promptly on success so a redeploy/restart doesn't have to
    wait out the full TTL. Filtered on our own token so we never delete a
    lock some other replica has since (re)acquired."""
    await db._db._migration_locks.delete_one({"_id": name, "token": token})

async def migrate_compliance_tenant_ids():
    """
    Self-healing migration:
    Finds all asset_compliance documents with no tenantId (or tenantId is None/missing)
    resolves the correct tenantId from the corresponding asset or agent.
    If the asset or agent no longer exists, prunes the orphaned record.
    """
    logger.info("[Migration] Starting compliance tenantId migration...")
    db = get_database()

    lock_token = await _acquire_migration_lock(db, "compliance_tenant_ids")
    if not lock_token:
        logger.info("[Migration] compliance tenantId migration already running on another replica, skipping.")
        return

    # We bypass isolation for migration
    old_tenant_id = get_tenant_id()
    set_tenant_id("platform-admin")

    try:
        # Find asset compliance records missing tenantId or where tenantId is None/invalid
        cursor = db._db.asset_compliance.find({
            "$or": [
                {"tenantId": {"$exists": False}},
                {"tenantId": None},
                {"tenantId": "ORPHANED_DATA_NO_TENANT_CONTEXT"},
                {"tenantId": "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"}
            ]
        })
        
        updated_count = 0
        deleted_count = 0
        async for doc in cursor:
            asset_id = doc.get("assetId")
            if not asset_id:
                await db._db.asset_compliance.delete_one({"_id": doc["_id"]})
                deleted_count += 1
                continue
                
            # Resolve tenantId from asset
            asset = await db._db.assets.find_one({"id": asset_id})
            tenant_id = asset.get("tenantId") if asset else None
            
            if not tenant_id:
                # Fall back to resolving from agent using hostname (assuming asset-hostname)
                hostname = asset_id.replace("asset-", "")
                agent = await db._db.agents.find_one({"hostname": hostname})
                tenant_id = agent.get("tenantId") if agent else None
                
            if tenant_id:
                await db._db.asset_compliance.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"tenantId": tenant_id}}
                )
                updated_count += 1
            else:
                # Prune orphaned record
                await db._db.asset_compliance.delete_one({"_id": doc["_id"]})
                deleted_count += 1
                
        logger.info(f"[Migration] Successfully migrated {updated_count} and pruned {deleted_count} compliance records.")
        print(f"[Migration] Successfully migrated {updated_count} and pruned {deleted_count} compliance records.")
        
    except Exception as e:
        logger.error(f"[Migration] Error migrating compliance records: {e}")
        print(f"[Migration] Error migrating compliance records: {e}")
    finally:
        set_tenant_id(old_tenant_id)
        await _release_migration_lock(db, "compliance_tenant_ids", lock_token)


async def migrate_instructions_tenant_ids():
    """
    Self-healing migration:
    Finds all agent_instructions with missing or orphaned tenantId and resolves it from the agent.
    If the agent no longer exists, prunes the orphaned record.
    """
    logger.info("[Migration] Starting agent instructions tenantId migration...")
    db = get_database()

    lock_token = await _acquire_migration_lock(db, "instructions_tenant_ids")
    if not lock_token:
        logger.info("[Migration] agent instructions tenantId migration already running on another replica, skipping.")
        return

    old_tenant_id = get_tenant_id()
    set_tenant_id("platform-admin")

    try:
        cursor = db._db.agent_instructions.find({
            "$or": [
                {"tenantId": {"$exists": False}},
                {"tenantId": None},
                {"tenantId": "ORPHANED_DATA_NO_TENANT_CONTEXT"},
                {"tenantId": "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"}
            ]
        })
        
        updated_count = 0
        deleted_count = 0
        async for doc in cursor:
            agent_id = doc.get("agent_id")
            if not agent_id:
                await db._db.agent_instructions.delete_one({"_id": doc["_id"]})
                deleted_count += 1
                continue
                
            agent = await db._db.agents.find_one({"id": agent_id})
            if not agent:
                agent = await db._db.agents.find_one({"hostname": agent_id})
            tenant_id = agent.get("tenantId") if agent else None
            
            if tenant_id:
                await db._db.agent_instructions.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"tenantId": tenant_id}}
                )
                updated_count += 1
            else:
                # Prune orphaned record
                await db._db.agent_instructions.delete_one({"_id": doc["_id"]})
                deleted_count += 1
                
        logger.info(f"[Migration] Successfully migrated {updated_count} and pruned {deleted_count} agent instructions.")
        print(f"[Migration] Successfully migrated {updated_count} and pruned {deleted_count} agent instructions.")

    except Exception as e:
        logger.error(f"[Migration] Error migrating agent instructions: {e}")
        print(f"[Migration] Error migrating agent instructions: {e}")
    finally:
        set_tenant_id(old_tenant_id)
        await _release_migration_lock(db, "instructions_tenant_ids", lock_token)


async def seed_compliance_frameworks():
    """
    Idempotent seed: runs seed_compliance.py as a child process when the
    compliance_frameworks collection is empty. No-ops on subsequent startups.
    Uses create_subprocess_exec (no shell) with a fixed script path — no injection risk.
    """
    import asyncio as _asyncio
    import os as _os
    import sys as _sys
    db = get_database()

    lock_token = await _acquire_migration_lock(db, "seed_compliance_frameworks")
    if not lock_token:
        logger.info("[Migration] compliance frameworks seed already running on another replica, skipping.")
        return

    old_tid = get_tenant_id()
    set_tenant_id("platform-admin")
    try:
        count = await db._db.compliance_frameworks.count_documents({})
        if count > 0:
            logger.debug("[Migration] Compliance frameworks already present (%d), skipping.", count)
            return
        script_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "seed_compliance.py")
        interpreter = _sys.executable
        proc = await _asyncio.create_subprocess_exec(
            interpreter, script_path,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=_os.path.dirname(_os.path.abspath(__file__)),
        )
        _stdout, _stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("[Migration] Compliance frameworks seeded via child process.")
        else:
            logger.error("[Migration] Compliance seed failed (rc=%d): %s",
                         proc.returncode, _stderr.decode(errors="replace")[-400:])
    except Exception as e:
        logger.error("[Migration] Error seeding compliance frameworks: %s", e)
    finally:
        set_tenant_id(old_tid)
        await _release_migration_lock(db, "seed_compliance_frameworks", lock_token)


async def migrate_tenant_registration_keys():
    """
    Backfill migration: ensures every tenant document has a registrationKey.
    Tenants created before the key generation was added will be missing this field.
    """
    import secrets as _secrets
    db = get_database()

    lock_token = await _acquire_migration_lock(db, "tenant_registration_keys")
    if not lock_token:
        logger.info("[Migration] tenant registration key backfill already running on another replica, skipping.")
        return

    old_tenant_id = get_tenant_id()
    set_tenant_id("platform-admin")
    try:
        cursor = db._db.tenants.find(
            {"$or": [{"registrationKey": {"$exists": False}}, {"registrationKey": None}]},
            {"_id": 1, "id": 1, "name": 1}
        )
        docs = await cursor.to_list(length=1000)
        count = 0
        for doc in docs:
            key = f"reg_{_secrets.token_hex(16)}"
            await db._db.tenants.update_one({"_id": doc["_id"]}, {"$set": {"registrationKey": key}})
            count += 1
        if count:
            logger.info("[Migration] Backfilled registrationKey for %d tenant(s).", count)
    except Exception as e:
        logger.error("[Migration] Error backfilling tenant registration keys: %s", e)
    finally:
        set_tenant_id(old_tenant_id)
        await _release_migration_lock(db, "tenant_registration_keys", lock_token)
