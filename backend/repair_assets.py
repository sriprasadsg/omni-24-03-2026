
import asyncio
import uuid
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

async def repair_assets():
    print("--- STARTING DATABASE REPAIR: ASSET SYNCHRONIZATION ---")
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client.omni_platform
    
    # 1. Get all agents
    agents = await db.agents.find({}).to_list(length=None)
    print(f"Total agents found: {len(agents)}")
    
    repaired_count = 0
    skipped_count = 0
    
    for agent in agents:
        agent_id = agent.get("id")
        hostname = agent.get("hostname")
        tenant_id = agent.get("tenantId", "default")
        
        if not hostname:
            print(f"⚠️ Skipping agent {agent_id} (no hostname)")
            skipped_count += 1
            continue
            
        # Check if asset exists matching THIS hostname
        asset_id = f"asset-{hostname}"
        existing_asset = await db.assets.find_one({"id": asset_id})
        
        if not existing_asset:
            # Create the asset
            asset_data = {
                "id": asset_id,
                "tenantId": tenant_id,
                "hostname": hostname,
                "osName": agent.get("platform", "Unknown"),
                "osVersion": agent.get("osVersion", agent.get("version", "Unknown")),
                "ipAddress": agent.get("ipAddress", "0.0.0.0"),
                "status": "active",
                "type": "server",
                "lastScanned": datetime.utcnow().isoformat(),
                "agentStatus": agent.get("status", "Online"),
                "agentVersion": agent.get("version", "1.0.0"),
                "agentCapabilities": agent.get("capabilities", []),
                "vulnerabilities": [],
                "criticalFiles": []
            }
            await db.assets.insert_one(asset_data)
            repaired_count += 1
            
            # Link agent to this asset if it wasn't already or has a different ID
            if agent.get("assetId") != asset_id:
                await db.agents.update_one(
                    {"id": agent_id},
                    {"$set": {"assetId": asset_id}}
                )
        else:
            # Asset exists, ensure it's linked
            if agent.get("assetId") != asset_id:
                await db.agents.update_one(
                    {"id": agent_id},
                    {"$set": {"assetId": asset_id}}
                )
                repaired_count += 1
            else:
                skipped_count += 1
                
    print(f"--------------------------------------")
    print(f"Repair Complete.")
    print(f"Assets Created/Linked: {repaired_count}")
    print(f"Already Synchronized: {skipped_count}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(repair_assets())
