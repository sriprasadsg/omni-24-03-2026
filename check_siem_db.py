import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection
from tenant_context import set_tenant_id

async def check_events():
    await connect_to_mongo()
    db = get_database()
    
    # We need to bypass isolation to see everything
    set_tenant_id("platform-admin")
    
    events = await db.security_events.find({}).to_list(length=100)
    print(f"Total events in DB: {len(events)}")
    for e in events:
        print(f"- ID: {e.get('id')}, Tenant: {e.get('tenantId')}, Source: {e.get('metadata', {}).get('product')}")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check_events())
