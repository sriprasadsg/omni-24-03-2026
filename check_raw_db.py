import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    count = await db.compliance_frameworks.count_documents({})
    print(f'RAW Count: {count}')
    
    if count > 0:
        docs = await db.compliance_frameworks.find({}, {"_id": 0}).to_list(length=1)
        if docs:
            print(f"FULL DOC ID: {docs[0].get('id')}")
            print(f"FULL DOC NAME: {docs[0].get('name')}")
            # Check if it has tenantId
            print(f"HAS TENANT ID: {'tenantId' in docs[0]}")
            if 'tenantId' in docs[0]:
                print(f"TENANT ID VALUE: {docs[0]['tenantId']}")
            
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
