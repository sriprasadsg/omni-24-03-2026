import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client.omni_platform
    
    tenant_id = "tenant_e5172ba0e"
    
    for col_name in ['ai_models', 'ai_policies']:
        count = await db[col_name].count_documents({'tenantId': tenant_id})
        print(f"{col_name} for {tenant_id}: {count}")
        if count > 0:
            doc = await db[col_name].find_one({'tenantId': tenant_id})
            print(f"  Example {col_name}: {doc.get('name')}")

if __name__ == "__main__":
    asyncio.run(check())
