import sys
import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json
from datetime import datetime

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)

async def debug_compliance():
    print("Connecting to database...")
    from database import connect_to_mongo, get_database
    await connect_to_mongo()
    db = get_database()
    
    output = {}
    
    # 1. Check for specific asset and control
    asset_id = "asset-desktop-rust-agent"
    control_id = "PCI-1.1.1" 
    
    doc = await db.asset_compliance.find_one({
        "assetId": asset_id, 
        "controlId": control_id
    })
    
    if doc:
        doc["_id"] = str(doc["_id"])
        output["target_doc"] = doc
    else:
        output["target_doc"] = None
        
    # 2. List ALL records for this asset
    output["all_records"] = []
    async for rec in db.asset_compliance.find({"assetId": asset_id}):
        output["all_records"].append({
            "controlId": rec.get('controlId'),
            "status": rec.get('status'),
            "evidence_count": len(rec.get('evidence', [])),
            "evidence_names": [e.get('name') for e in rec.get('evidence', [])]
        })

    with open("debug_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, cls=DateTimeEncoder)
    print("Done writing to debug_output.json")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(debug_compliance())
