import asyncio
import sys
import os
import json

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database, close_mongo_connection

async def find_empty_a8():
    await connect_to_mongo()
    db = get_database()
    
    frameworks = await db.compliance_frameworks.find_one({"id": "iso27001"})
    tech_controls = [c['id'] for c in frameworks['controls'] if c['id'].startswith('A.5.') or c['id'].startswith('A.6.') or c['id'].startswith('A.7.') or c['id'].startswith('A.8.')]
    
    docs = await db.asset_compliance.find({"controlId": {"$in": tech_controls}}).to_list(length=None)
    
    controls_with_evidence = set()
    for doc in docs:
        if doc.get("evidence") and len(doc["evidence"]) > 0:
            controls_with_evidence.add(doc["controlId"])
            
    empty_controls = sorted(list(set(tech_controls) - controls_with_evidence), key=lambda x: [int(p) for p in x.replace('A.', '').split('.')])
    
    with open('missing_controls.json', 'w') as f:
        json.dump(empty_controls, f, indent=2)
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(find_empty_a8())
