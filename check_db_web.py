import asyncio
import motor.motor_asyncio

async def check():
    try:
        client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')
        db = client['omni_platform']
        cursor = db.agents.find({'meta.web_monitor': {'$exists': True}})
        results = await cursor.to_list(length=10)
        print(f'Found {len(results)} agents with web monitor data')
        for r in results:
            wm = r.get('meta', {}).get('web_monitor', {})
            conns = wm.get('web_connections', [])
            print(f"Agent {r['hostname']}: {len(conns)} connections")
            for c in conns[:3]:
                print(f"  - {c.get('process')} -> {c.get('remote_host')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(check())
