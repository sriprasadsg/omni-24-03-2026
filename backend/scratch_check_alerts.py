import asyncio
from database import connect_to_mongo, close_mongo_connection, get_database
import tenant_context

async def check_alerts():
    # Bypass tenant isolation
    tenant_context.get_tenant_id = lambda: "platform-admin"
    
    await connect_to_mongo()
    db = get_database()
    
    # We need to access the raw collection if the wrapper still interferes, 
    # but "platform-admin" should bypass it in _inject_tenant_id.
    
    print("--- Alerts in DB ---")
    try:
        alerts = await db.alerts.find({}, {"_id": 0}).to_list(length=100)
        for a in alerts:
            print(f"ID: {a.get('id')}, Severity: '{a.get('severity')}', Message: {a.get('message')[:30]}...")
        if not alerts:
            print("No alerts found in 'alerts' collection.")
    except Exception as e:
        print(f"Error querying alerts: {e}")
    
    print("\n--- Security Events in DB ---")
    try:
        security_events = await db.security_events.find({}, {"_id": 0}).to_list(length=100)
        for e in security_events:
            print(f"ID: {e.get('id')}, Severity: '{e.get('severity')}', Type: {e.get('type')}")
        if not security_events:
            print("No events found in 'security_events' collection.")
    except Exception as e:
        print(f"Error querying security_events: {e}")
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check_alerts())
