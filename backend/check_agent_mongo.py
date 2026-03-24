import asyncio
import sys
from database import connect_to_mongo, get_database

async def main():
    await connect_to_mongo()
    db = get_database()
    agents = await db.agents.find().to_list(100)
    print(f"Total agents in DB: {len(agents)}")
    for a in agents:
        print("-------------")
        print(f"Agent ID: {a.get('id')}")
        print(f"Hostname: {a.get('hostname')}")
        print(f"Status: {a.get('status')}")
        print(f"LastSeen: {a.get('lastSeen')}")
        print(f"DeviceID: {a.get('deviceId')}")

if __name__ == "__main__":
    asyncio.run(main())
