import sys
import os
import asyncio
from datetime import datetime

# Setup API path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, get_database

async def main():
    print("Connecting to DB...")
    await connect_to_mongo()
    db = get_database()
    
    hostname = "EILT0197"
    target_id = f"agent-{hostname}"
    
    print(f"Forcing Agent {target_id} to ONLINE...")
    
    res = await db.agents.update_one(
        {"id": target_id},
        {"$set": {
            "status": "Online", 
            "lastSeen": datetime.utcnow().isoformat()
        }}
    )
    
    print(f"Matched: {res.matched_count}, Modified: {res.modified_count}")
    
    # Verify
    agent = await db.agents.find_one({"id": target_id})
    print(f"New Status: {agent.get('status')} | LastSeen: {agent.get('lastSeen')}")

if __name__ == "__main__":
    asyncio.run(main())
