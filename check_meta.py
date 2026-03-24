
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from database import connect_to_mongo, get_database

async def check_meta():
    await connect_to_mongo()
    db = get_database()
    
    agent_id = 'agent-cd82b8d0'
    print(f"--- 🔬 Metadata Check for {agent_id} ---")
    agent = await db.agents.find_one({'id': agent_id})
    if not agent:
        print("Agent not found!")
        return
        
    meta = agent.get('meta', {})
    print(f"Meta Keys: {list(meta.keys())}")
    
    sw_inv = meta.get('software_inventory', [])
    print(f"Software Inventory Count: {len(sw_inv)}")
    
    inst_sw = meta.get('installed_software', [])
    print(f"Installed Software Count: {len(inst_sw)}")
    if inst_sw:
        print(f"  First 3 items: {inst_sw[:3]}")
    
    os_p = meta.get('os_patches', {})
    print(f"OS Patches: {os_p}")

if __name__ == "__main__":
    asyncio.run(check_meta())
