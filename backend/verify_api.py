import asyncio
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database, close_mongo_connection

async def verify_api():
    await connect_to_mongo()
    db = get_database()
    
    framework_id = "iso27001"
    f = await db.compliance_frameworks.find_one({"id": framework_id})
    
    if not f:
        print("Framework not found!")
        await close_mongo_connection()
        return
        
    print(f"✅ Framework Found: {f.get('name')}")
    
    compliance_docs = await db.asset_compliance.find({}).to_list(length=None)
    
    evidence_by_control = {}
    for doc in compliance_docs:
        cid = doc.get("controlId")
        if cid not in evidence_by_control:
            evidence_by_control[cid] = []
        evidence_by_control[cid].extend(doc.get("evidence", []))
    
    key_controls = ["A.8.12", "A.8.13", "A.8.24", "A.8.32", "A.8.25", "A.8.10", "A.8.14", "A.8.17", "A.8.6", "A.8.20", "A.8.4", "A.8.34"]
    
    print("\n📊 Verification of New Comprehensive Tech Controls:")
    for c in key_controls:
        evs = evidence_by_control.get(c, [])
        status = "✅ HAS EVIDENCE" if len(evs) > 0 else "❌ NO EVIDENCE"
        print(f"  • Control {c}: {len(evs)} items -> {status}")
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(verify_api())
