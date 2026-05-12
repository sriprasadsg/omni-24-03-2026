import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    frameworks = await db.compliance_frameworks.find().to_list(100)
    print(f"Total frameworks: {len(frameworks)}")
    for f in frameworks:
        print(f"ID: {f.get('id')} Name: {f.get('name')} Status: {f.get('status')}")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
