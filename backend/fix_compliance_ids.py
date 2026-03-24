
import asyncio
import os
from database import connect_to_mongo, get_database

async def fix_compliance_ids():
    await connect_to_mongo()
    db = get_database()
    
    print("🔧 Starting Compliance Evidence ID Fix...")
    
    # 1. Get all asset_compliance records
    cursor = db.asset_compliance.find({})
    records = await cursor.to_list(length=10000)
    
    updates = 0
    prefixes = ["nistcsf-", "pci-dss-", "iso27001-", "hipaa-", "gdpr-", "dpdp-"]
    
    for record in records:
        original_control_id = record.get("controlId")
        new_control_id = original_control_id
        
        # Check if it has a prefix
        for prefix in prefixes:
            if original_control_id.startswith(prefix):
                new_control_id = original_control_id[len(prefix):]
                break
                
        if new_control_id != original_control_id:
            print(f"  Repairing: {original_control_id} -> {new_control_id} (Asset: {record.get('assetId')})")
            
            # We need to update the document. 
            # Ideally we'd just update this doc, but if there's already a doc with the new_control_id, we might have a collision.
            # In compliace logic, we usually Upsert.
            
            # Check if target exists
            target_exists = await db.asset_compliance.find_one({
                "assetId": record.get("assetId"), 
                "controlId": new_control_id
            })
            
            if target_exists:
                print(f"    Target {new_control_id} already exists. Merging/Overwriting evidence...")
                # Merge evidence
                existing_evidence = record.get("evidence", [])
                if existing_evidence:
                     await db.asset_compliance.update_one(
                        {"_id": target_exists["_id"]},
                        {"$push": {"evidence": {"$each": existing_evidence}}}
                    )
                # Delete old
                await db.asset_compliance.delete_one({"_id": record["_id"]})
            else:
                # Just update the controlId
                await db.asset_compliance.update_one(
                    {"_id": record["_id"]},
                    {"$set": {"controlId": new_control_id}}
                )
            updates += 1
            
    print(f"✅ Fixed {updates} records.")
    
    # Also fix any evidence IDs inside the array if they have weirness, 
    # but primarily controlId is the linker.
    
    # Verify
    print("\n--- Verification: Checking for remaining prefixes ---")
    bad_records = await db.asset_compliance.find({
        "controlId": {"$regex": "^(nistcsf-|pci-dss-|iso27001-|hipaa-|gdpr-|dpdp-)"}
    }).to_list(length=100)
    
    if bad_records:
        print(f"❌ Warning: {len(bad_records)} records still have prefixes!")
    else:
        print("✅ No records with known prefixes found.")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fix_compliance_ids())
