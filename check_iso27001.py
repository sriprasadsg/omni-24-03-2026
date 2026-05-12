import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    f = await db.compliance_frameworks.find_one({'id': 'iso27001'})
    if f:
        print(f"Found: {f.get('name')} (ID: iso27001)")
    else:
        print("iso27001 NOT found")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
