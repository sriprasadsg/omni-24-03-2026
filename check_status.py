
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from database import connect_to_mongo, get_database

async def check_agents():
    await connect_to_mongo()
    db = get_database()
    agents = await db.agents.find({}, {"_id": 0, "id": 1, "hostname": 1, "status": 1, "lastSeen": 1}).to_list(100)
    print("--- 🤖 Agents in Database ---")
    if not agents:
        print("No agents found.")
    for agent in agents:
        print(f"ID: {agent.get('id')} | Hostname: {agent.get('hostname')} | Status: {agent.get('status')} | LastSeen: {agent.get('lastSeen')}")
    
    # Also check instructions
    instructions = await db.agent_instructions.find({"status": "pending"}).to_list(100)
    print("\n--- 📝 Pending Instructions ---")
    for ins in instructions:
        print(f"Agent ID: {ins.get('agent_id')} | Instruction: {ins.get('instruction')} | Created: {ins.get('created_at')}")

if __name__ == "__main__":
    asyncio.run(check_agents())
