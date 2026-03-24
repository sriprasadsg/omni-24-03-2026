"""
Quick check of tenant billing activation - simplified version
"""
import asyncio
import sys
from pymongo import MongoClient

async def quick_check():
    try:
        # Direct MongoDB connection
        client = MongoClient('mongodb://localhost:27017/')
        db = client['omni_platform']
        
        print("BILLING DASHBOARD STATUS FOR ALL TENANTS")
        print("=" * 60)
        
        tenants = list(db.tenants.find(
            {"id": {"$ne": "platform-admin"}},
            {"id": 1, "name": 1, "finOpsData": 1}
        ))
        
        activated = 0
        not_activated = 0
        
        for tenant in tenants:
            name = tenant.get("name", "Unknown")
            has_data = "finOpsData" in tenant and tenant["finOpsData"] is not None
            
            if has_data:
                activated += 1
                cost = tenant["finOpsData"].get("currentMonthCost", 0)
                print(f"✅ {name}: ACTIVATED (Cost: ${cost:.2f})")
            else:
                not_activated += 1
                print(f"❌ {name}: NOT ACTIVATED (missing finOpsData)")
        
        print("=" * 60)
        print(f"Total: {len(tenants)} | Activated: {activated} | Not Activated: {not_activated}")
        print("=" * 60)
        
        client.close()
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(quick_check())
