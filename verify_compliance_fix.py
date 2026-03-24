import asyncio
import os
import sys
from backend.database import get_database, connect_to_mongo

async def verify():
    print("Connecting to MongoDB...")
    await connect_to_mongo()
    db = get_database()
    
    print("\nChecking asset_compliance collection for control IDs...")
    cursor = db.asset_compliance.find({}, {"controlId": 1, "status": 1, "_id": 0}).limit(20)
    docs = await cursor.to_list(length=20)
    
    if not docs:
        print("❌ No compliance records found!")
        return
        
    print(f"✅ Found {len(docs)} records. Sample control IDs:")
    for doc in docs:
        print(f"  - {doc['controlId']} ({doc['status']})")
        
    # Check for prefixes
    prefixed = [d['controlId'] for d in docs if any(p in d['controlId'] for p in ["nistcsf-", "pci-dss-", "iso27001-", "hipaa-", "gdpr-"])]
    if prefixed:
        print(f"\n❌ Found {len(prefixed)} records with prefixes (e.g., {prefixed[0]})")
    else:
        print("\n✅ No records with framework prefixes found in sample. Fix appears successful!")

if __name__ == "__main__":
    asyncio.run(verify())
