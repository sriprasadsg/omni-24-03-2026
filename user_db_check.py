import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    for db_name in ['omni_agent_db', 'omni_platform']:
        db = client[db_name]
        try:
            u = await db.users.find_one({'email': 'admin@exafluence.com'})
            if u:
                print(f'User found in {db_name}: TenantId={u.get("tenantId")}, Role={u.get("role")}')
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(check())
