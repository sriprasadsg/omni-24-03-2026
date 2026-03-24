
import asyncio
from database import connect_to_mongo, mongodb, close_mongo_connection
import os
import sys

# Ensure we can import from current directory
sys.path.append(os.getcwd())

async def get_keys():
    print("Fetching Keys...")
    
    # Connect to DB
    await connect_to_mongo()
    db = mongodb.db
    
    if db is None:
        print("Failed to connect to database.")
        return

    tenants = await db.tenants.find({}).to_list(None)
    print(f"Found {len(tenants)} tenants.")
    
    keys = []
    for t in tenants:
        line = f"Tenant: {t.get('name')} (ID: {t.get('id')}) - Key: {t.get('registrationKey')}"
        print(line)
        keys.append(t.get('registrationKey'))
    
    if keys:
        with open("key.txt", "w") as f:
            f.write(keys[0])
        print(f"Updated key.txt with key: {keys[0]}")

    await close_mongo_connection()

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(get_keys())
