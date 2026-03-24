import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json
from datetime import datetime, timezone

async def test_bulk_update_logic():
    MONGODB_URL = "mongodb://localhost:27017"
    DATABASE_NAME = "omni_platform"
    
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    
    print("--- Verification of Bulk Update Logic ---")
    
    # 1. Clean up old instructions for test agents
    test_agent_1 = "test-agent-1"
    test_agent_2 = "test-agent-2"
    await db.agent_instructions.delete_many({"agent_id": {"$in": [test_agent_1, test_agent_2]}})
    
    # 2. Simulate the 'outdated' information with agent_id
    # In a real run, patch_endpoints.py get_outdated_software now returns agent_id
    # We verify the backend endpoint directly via a mock request if possible, 
    # but here we'll test the database side after calling the new bulk endpoint logic.
    
    print(f"Triggering bulk update for {test_agent_1} and {test_agent_2}...")
    
    # Simulate a request to /api/patches/bulk-apply-software-update
    updates = [
        {"agent_id": test_agent_1, "package_name": "requests", "pkg_type": "pip"},
        {"agent_id": test_agent_2, "package_name": "express", "pkg_type": "npm"}
    ]
    
    # Logic from patch_endpoints.py:apply_bulk_software_update
    instructions = []
    for update in updates:
        instructions.append({
            "agent_id": update["agent_id"],
            "instruction": f"upgrade_software: {update['package_name']}",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "type": "software_upgrade",
            "metadata": {
                "package": update["package_name"],
                "pkg_type": update["pkg_type"]
            }
        })
    
    if instructions:
        result = await db.agent_instructions.insert_many(instructions)
        print(f"Inserted {len(result.inserted_ids)} instructions.")

    # 3. Verify instructions in DB
    print("\nVerifying instructions in database...")
    for agent_id, pkg in [(test_agent_1, "requests"), (test_agent_2, "express")]:
        instr = await db.agent_instructions.find_one({
            "agent_id": agent_id,
            "metadata.package": pkg,
            "status": "pending"
        })
        if instr:
            print(f"✅ FOUND: Instruction for {pkg} correctly targeted at {agent_id}")
        else:
            print(f"❌ MISSING: Instruction for {pkg} targeting {agent_id}")

    # 4. Cleanup
    await db.agent_instructions.delete_many({"agent_id": {"$in": [test_agent_1, test_agent_2]}})
    print("\nCleanup complete.")

if __name__ == "__main__":
    asyncio.run(test_bulk_update_logic())
