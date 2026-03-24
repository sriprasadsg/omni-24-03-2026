
import asyncio
from database import connect_to_mongo, mongodb, close_mongo_connection
import os
import sys

# Ensure we can import from current directory
sys.path.append(os.getcwd())

async def verify_evidence():
    print("Starting Evidence Verification...")
    
    # Connect to DB
    await connect_to_mongo()
    db = mongodb.db
    
    if db is None:
        print("Failed to connect to database.")
        return

    # 1. Fetch all assets
    assets = await db.assets.find({}).to_list(None)
    asset_ids = {a["id"] for a in assets}
    print(f"Found {len(assets)} assets.")
    for a in assets:
        print(f" - {a.get('id', 'MISSING_ID')} (Hostname: {a.get('hostname', 'N/A')})")

    # 2. Fetch all compliance records
    compliance_records = await db.asset_compliance.find({}).to_list(None)
    print(f"Found {len(compliance_records)} compliance records within asset_compliance.")
    
    orphans = 0
    dpdp_found = False
    
    output_lines = []
    
    for r in compliance_records:
        aid = r.get("assetId")
        short_id = str(r.get("_id"))
        evidence_count = len(r.get("evidence", []))
        
        status = "OK"
        if aid not in asset_ids:
            status = "ORPHAN"
            orphans += 1
        
        if evidence_count > 0:
             dpdp_found = True
             line = f"Record {short_id}: AssetID={aid}, Evidence={evidence_count}, Status={status}"
             print(line)
             output_lines.append(line)
        elif status == "ORPHAN":
             # Print orphans even if no evidence, to see the mess
             line = f"Record {short_id}: AssetID={aid}, Evidence={evidence_count}, Status={status}"
            #  print(line) 

    print(f"Total Orphans: {orphans}")
    output_lines.append(f"Total Orphans: {orphans}")
    
    with open("backend/results.txt", "w") as f:
        f.write("\n".join(output_lines))
        
    if dpdp_found:
        print("FOUND records with evidence.")
    else:
        print("NO records with evidence found.")
        
    await close_mongo_connection()

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(verify_evidence())
