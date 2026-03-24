"""
Cleanup script to remove duplicate agents from MongoDB
Keeps the most recent version of each agent based on lastSeen timestamp
"""

import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection
from datetime import datetime
from collections import defaultdict

async def cleanup_duplicate_agents():
    """Remove duplicate agents, keeping the most recent one"""
    
    await connect_to_mongo()
    db = get_database()
    
    print("🔍 Searching for duplicate agents...")
    
    # Find all agents
    agents = await db.agents.find({}).to_list(length=None)
    print(f"📊 Total agents in database: {len(agents)}")
    
    # Group by agent ID
    agents_by_id = defaultdict(list)
    for agent in agents:
        agent_id = agent.get('id')
        if agent_id:
            agents_by_id[agent_id].append(agent)
    
    # Find duplicates
    duplicates = {aid: alist for aid, alist in agents_by_id.items() if len(alist) > 1}
    
    if not duplicates:
        print("✅ No duplicate agents found!")
        await close_mongo_connection()
        return
    
    print(f"\n⚠️  Found {len(duplicates)} agent IDs with duplicates:")
    
    total_deleted = 0
    
    for agent_id, agent_list in duplicates.items():
        print(f"\n  Agent ID: {agent_id}")
        print(f"  Duplicate count: {len(agent_list)}")
        
        # Sort by lastSeen (most recent first)
        sorted_agents = sorted(
            agent_list,
            key=lambda x: x.get('lastSeen', '1970-01-01T00:00:00Z'),
            reverse=True
        )
        
        # Keep the first (most recent)
        keep = sorted_agents[0]
        delete = sorted_agents[1:]
        
        print(f"  ✅ Keeping: {keep.get('hostname', 'unknown')} (lastSeen: {keep.get('lastSeen', 'N/A')})")
        print(f"  ❌ Deleting: {len(delete)} older duplicates")
        
        # Delete older duplicates by MongoDB _id
        for agent in delete:
            result = await db.agents.delete_one({"_id": agent['_id']})
            if result.deleted_count > 0:
                total_deleted += 1
                print(f"    ➖ Deleted: {agent.get('hostname', 'unknown')} (lastSeen: {agent.get('lastSeen', 'N/A')})")
    
    print(f"\n✅ Cleanup complete!")
    print(f"📊 Removed {total_deleted} duplicate agents")
    print(f"📊 Unique agents remaining: {len(agents_by_id)}")
    
    await close_mongo_connection()

if __name__ == "__main__":
    print("=" * 60)
    print("🧹 Agent Duplicate Cleanup Script")
    print("=" * 60)
    asyncio.run(cleanup_duplicate_agents())
