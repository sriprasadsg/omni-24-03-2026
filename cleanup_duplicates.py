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
    
    print("Fetching agents for EILT0197...")
    agents = await db.agents.find({"hostname": "EILT0197"}).to_list(length=100)
    
    if not agents:
        print("No agents found.")
        return

    print(f"Found {len(agents)} agents.")
    
    # Sort by lastSeen descending (most recent first)
    agents.sort(key=lambda x: x.get("lastSeen", ""), reverse=True)
    
    keeper = agents[0]
    to_delete = agents[1:]
    
    print(f"Keeping Active Agent: {keeper.get('id')} | LastSeen: {keeper.get('lastSeen')}")
    
    for a in to_delete:
        print(f"Deleting Duplicate: {a.get('id')} | LastSeen: {a.get('lastSeen')}")
        await db.agents.delete_one({"id": a.get("id")})
        
    print("Cleanup Complete.")

if __name__ == "__main__":
    asyncio.run(main())
