import asyncio
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database, close_mongo_connection

async def check_ids():
    await connect_to_mongo()
    db = get_database()
    
    print("📋 Checking Framework Control IDs...")
    f = await db.compliance_frameworks.find_one({"id": "iso27001"})
    if f:
        print(f"Framework: {f.get('name')} (ID: {f.get('id')})")
        controls = f.get("controls", [])
        print(f"Control IDs (sample): {[c['id'] for c in controls[:5]]}")
    else:
        print("❌ ISO 27001 framework not found!")

    print("\n📋 Checking Asset Compliance Record IDs (All unique ControlIDs)...")
    pipeline = [{"$group": {"_id": "$controlId", "count": {"$sum": 1}}}]
    results = await db.asset_compliance.aggregate(pipeline).to_list(length=None)
    for r in results:
        print(f"  • {r['_id']} (Count: {r['count']})")
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check_ids())
