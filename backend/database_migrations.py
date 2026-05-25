import logging
from database import get_database
from tenant_context import set_tenant_id, get_tenant_id

logger = logging.getLogger("database_migrations")

async def migrate_compliance_tenant_ids():
    """
    Self-healing migration:
    Finds all asset_compliance documents with no tenantId (or tenantId is None/missing)
    resolves the correct tenantId from the corresponding asset or agent.
    If the asset or agent no longer exists, prunes the orphaned record.
    """
    logger.info("[Migration] Starting compliance tenantId migration...")
    db = get_database()
    
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


async def migrate_instructions_tenant_ids():
    """
    Self-healing migration:
    Finds all agent_instructions with missing or orphaned tenantId and resolves it from the agent.
    If the agent no longer exists, prunes the orphaned record.
    """
    logger.info("[Migration] Starting agent instructions tenantId migration...")
    db = get_database()
    
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
