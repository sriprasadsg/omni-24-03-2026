import requests
import asyncio
from database import connect_to_mongo, get_database

BASE_URL = "http://localhost:5000/api"

async def check_logs():
    print("🔍 Checking MongoDB for Audit Logs...")
    await connect_to_mongo()
    db = get_database()
    
    # Find most recent log
    logs = await db.audit_logs.find().sort("timestamp", -1).limit(1).to_list(length=1)
    
    if logs:
        log = logs[0]
        print(f"✅ Found Audit Log:")
        print(f"   Timestamp: {log.get('timestamp')}")
        print(f"   Action: {log.get('action')}")
        print(f"   Actor: {log.get('actor')}")
        print(f"   Details: {log.get('details')}")
        return True
    else:
        print("❌ No audit logs found.")
        return False

def run_test():
    print("🚀 Verifying Audit Logging...")
    
    # 1. Perform an Auditable Action (Ingest Knowledge)
    print("👉 Triggering Action: Ingest Knowledge")
    try:
        resp = requests.post(f"{BASE_URL}/knowledge/ingest", json={"content": "Audit Log Test Entry", "source": "verify_script"})
        resp.raise_for_status()
        print("Action Complete.")
    except Exception as e:
        print(f"❌ API Call Failed: {e}")
        return

    # 2. Check Database directly (async wrapper)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(check_logs())

if __name__ == "__main__":
    run_test()
