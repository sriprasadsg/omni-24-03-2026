import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
import asyncio
from database import connect_to_mongo, get_database

async def get_key():
    await connect_to_mongo()
    db = get_database()
    t = await db.tenants.find_one({"id": "tenant_test_123"})
    if t:
        print(f"KEY_START|{t.get('registrationKey')}|KEY_END")
    else:
        print("NO_TENANT")

if __name__ == "__main__":
    asyncio.run(get_key())
