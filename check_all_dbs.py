import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    dbs = await client.list_database_names()
    print(f'Databases: {dbs}')
    for db_name in dbs:
        if db_name in ['admin', 'config', 'local']: continue
        db = client[db_name]
        try:
            count = await db.compliance_frameworks.count_documents({})
            print(f'Database "{db_name}" has {count} frameworks.')
            if count > 0:
                f = await db.compliance_frameworks.find_one()
                print(f'  Example: {f.get("name")}')
            
            t = await db.tenants.find_one({'name': 'Exafluence'})
            if t:
                 print(f'  Found Exafluence tenant (ID: {t.get("id")})')
        except Exception as e:
            # print(f"Error checking {db_name}: {e}")
            pass

if __name__ == "__main__":
    asyncio.run(check())
