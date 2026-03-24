import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from motor.motor_asyncio import AsyncIOMotorClient
from ueba_engine import ueba_engine
import database

async def trigger_calculation():
    # Setup database connection for singleton
    await database.connect_to_mongo()
    
    db = database.get_database()
    print("Triggering UEBA Calculation...")
    
    tenant = await db.tenants.find_one({"id": "platform-admin"})
    if not tenant:
        print("Error: No platform-admin tenant found.")
        return
    tenant_id = tenant['id']
    
    # Get all users
    users_cursor = db._db.users.find({"tenantId": tenant_id})
    users = await users_cursor.to_list(None)
    print(f"Calculating scores for {len(users)} users...")
    
    for user in users:
        u_id = user.get('id')
        if u_id:
            print(f"Processing user: {u_id}")
            result = await ueba_engine.calculate_risk_score(tenant_id, u_id)
            print(f"Score: {result.get('score')}")

    print("UEBA Calculation Complete.")

if __name__ == "__main__":
    asyncio.run(trigger_calculation())
