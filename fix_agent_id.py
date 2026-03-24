import sys
import os
import asyncio

# Setup API path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, get_database

async def main():
    print("Connecting to DB...")
    await connect_to_mongo()
    db = get_database()
    
    hostname = "EILT0197"
    target_id = f"agent-{hostname}"
    
    print(f"Aligning Agent ID to: {target_id}")
    
    # 1. Delete any existing doc with target_id to avoid collision
    await db.agents.delete_one({"id": target_id})
    
    # 2. Find the existing agent with hostname
    agent = await db.agents.find_one({"hostname": hostname})
    
    if not agent:
        print("No agent found with hostname EILT0197. Creating one...")
        new_agent = {
            "id": target_id,
            "hostname": hostname,
            "status": "Offline",
            "lastSeen": "",
            "tenantId": "tenant_82dda0f33bc4"
        }
        await db.agents.insert_one(new_agent)
    else:
        print(f"Updating Agent {agent['id']} -> {target_id}")
        await db.agents.update_one(
            {"_id": agent["_id"]},
            {"$set": {"id": target_id}}
        )
        
    print("Agent ID Aligned.")

if __name__ == "__main__":
    asyncio.run(main())
