
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from database import connect_to_mongo, get_database

async def check_inventory():
    await connect_to_mongo()
    db = get_database()
    
    print("--- 🔬 Agents Collection Check ---")
    agents = await db.agents.find({}, {"_id": 0, "id": 1, "hostname": 1, "status": 1, "installed_software": 1}).to_list(100)
    for agent in agents:
        sw_count = len(agent.get("installed_software", []))
        print(f"Agent: {agent.get('id')} ({agent.get('hostname')}) | Status: {agent.get('status')} | SW Count: {sw_count}")
        if sw_count > 0:
            print(f"  Sample SW: {agent.get('installed_software')[0]}")

    print("\n--- 📦 Software Inventory Collection ---")
    sw_inv_count = await db.software_inventory.count_documents({})
    print(f"Total documents: {sw_inv_count}")
    
    if sw_inv_count > 0:
        samples = await db.software_inventory.find({}, {"_id": 0}).to_list(10)
        for s in samples:
            print(f"  - {s.get('name')} ({s.get('current_version')}) type={s.get('pkg_type')}")

if __name__ == "__main__":
    asyncio.run(check_inventory())
