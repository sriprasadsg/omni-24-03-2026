import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to sys.path to import backend modules
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, get_database, close_mongo_connection

async def fetch_recent():
    await connect_to_mongo()
    db = get_database()
    
    print(f"\n📢 Fetching the 20 most recent compliance records...")
    
    cursor = db.asset_compliance.find().sort("lastUpdated", -1).limit(20)
    records = await cursor.to_list(length=20)
    
    if not records:
        print("❌ No recently updated compliance records found.")
        # Check all records to see what the latest one is
        latest = await db.asset_compliance.find().sort("lastUpdated", -1).limit(1).to_list(length=1)
        if latest:
            print(f"DEBUG: Latest record in DB is from {latest[0].get('lastUpdated')} (ID: {latest[0].get('controlId')})")
        return

    print(f"✅ Found {len(records)} recent compliance records:")
    print("-" * 60)
    print(f"{'Control ID':<20} | {'Status':<15} | {'Check Name'}")
    print("-" * 60)
    
    for r in sorted(records, key=lambda x: x.get('controlId')):
        print(f"{r.get('controlId'):<20} | {r.get('status'):<15} | {r.get('checkName')}")
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(fetch_recent())
