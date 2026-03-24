import asyncio
from backend.database import connect_to_mongo, get_database

async def list_agents():
    await connect_to_mongo()
    db = get_database()
    agents = await db.agents.find().to_list(None)
    with open("full_agent_dump.txt", "w") as f:
        f.write(f"Total Agents: {len(agents)}\n")
        for a in agents:
            f.write(f"ID: {a.get('id')}\n")
            f.write(f"Tenant: {a.get('tenantId')}\n")
            f.write(f"Host: {a.get('hostname')}\n")
            f.write(f"IP: {a.get('ipAddress')}\n")
            f.write("-" * 20 + "\n")

if __name__ == "__main__":
    asyncio.run(list_agents())
