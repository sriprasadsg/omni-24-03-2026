import asyncio
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database, close_mongo_connection

async def analyze_compliance():
    await connect_to_mongo()
    db = get_database()
    
    docs = await db.asset_compliance.find({}).to_list(length=None)
    print(f"\n📊 Total Compliance Records: {len(docs)}")
    
    legacy_count = 0
    new_count = 0
    dupe_evidence_count = 0
    
    framework_stats = {}
    
    for doc in docs:
        cid = doc.get("controlId", "unknown")
        fid = cid.split('-')[0] if '-' in cid else "2022_ISO"
        framework_stats[fid] = framework_stats.get(fid, 0) + 1
        
        if cid.startswith("iso27001-"):
            legacy_count += 1
            
        evidence = doc.get("evidence", [])
        names = [e.get("name") for e in evidence]
        if len(names) != len(set(names)):
            dupe_evidence_count += 1
            
    print("\n📈 Framework Distribution:")
    for fid, count in framework_stats.items():
        print(f"  • {fid}: {count}")
        
    print(f"\n🚩 Legacy Records (iso27001- prefix): {legacy_count}")
    print(f"🚩 Records with Duplicate Evidence: {dupe_evidence_count}")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(analyze_compliance())
