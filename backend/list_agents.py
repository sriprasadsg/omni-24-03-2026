
import asyncio
import sys
import io

# Set stdout to utf-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from database import connect_to_mongo, get_database

async def main():
    try:
        await connect_to_mongo()
        db = get_database()
        agents = await db.agents.find().to_list(100)
        print(f"Total Agents: {len(agents)}")
        for a in agents:
            print(f"Agent: {a.get('hostname')}")
            print(f"  ID: {a.get('id')}")
            print(f"  AssetID: {a.get('assetId')}")
            print(f"  Status: {a.get('status')}")
            print("-" * 20)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
