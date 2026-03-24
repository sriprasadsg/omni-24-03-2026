import asyncio
import sys
import os
import datetime

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database, close_mongo_connection

# Framework Prefixes to Remove
PREFIXES = ["iso27001-", "pci-dss-", "nistcsf-", "dpdp-", "csa-", "fedramp-", "hipaa-", "ccpa-", "gdpr-", "cmmc-", "dora-", "cobit-"]

# Legacy to 2022 Mapping for Cleanup (Ensure these are already cleaned)
LEGACY_MAPPING = {
    "A.12.2.1": "A.8.7",   # Malware
    "A.9.4.3": "A.5.15",    # Passwords
    "A.13.1.1": "A.8.22",   # Network Segregation
    "A.12.6.1": "A.8.8",    # Vulnerabilities
}

async def cleanup_compliance():
    await connect_to_mongo()
    db = get_database()
    
    print("🧹 Starting Compliance Evidence Cleanup...")
    
    docs = await db.asset_compliance.find({}).to_list(length=None)
    print(f"📊 Processing {len(docs)} compliance records...")
    
    migrated_count = 0
    deduped_evidence_count = 0
    record_dedupe_count = 0
    deleted_count = 0
    
    # 1. Deduplicate records themselves (same assetId + controlId)
    seen_records = set()
    for doc in docs:
        key = (doc.get("assetId"), doc.get("controlId"))
        if key in seen_records:
            # Delete duplicate record
            await db.asset_compliance.delete_one({"_id": doc["_id"]})
            record_dedupe_count += 1
            continue
        seen_records.add(key)
        
        # 2. Remove Prefixes and Migrate IDs
        control_id = doc.get("controlId", "")
        original_id = control_id
        
        # Strip prefixes
        for prefix in PREFIXES:
            if control_id.startswith(prefix):
                control_id = control_id[len(prefix):]
                break
        
        # Apply legacy mapping on stripped ID
        if control_id in LEGACY_MAPPING:
            control_id = LEGACY_MAPPING[control_id]
            
        if control_id != original_id:
            print(f"🔄 Standardizing ID: {original_id} -> {control_id}")
            
            # Check if target already exists
            existing_target = await db.asset_compliance.find_one({"assetId": doc["assetId"], "controlId": control_id})
            
            if existing_target:
                # Merge evidence into existing target
                new_evidence = existing_target.get("evidence", [])
                existing_names = [e.get("name") for e in new_evidence]
                
                for e in doc.get("evidence", []):
                    if e.get("name") not in existing_names:
                        new_evidence.append(e)
                
                await db.asset_compliance.update_one(
                    {"_id": existing_target["_id"]},
                    {"$set": {"evidence": new_evidence, "lastUpdated": datetime.datetime.utcnow().isoformat()}}
                )
                await db.asset_compliance.delete_one({"_id": doc["_id"]})
                deleted_count += 1
            else:
                # Update this record to the new ID
                await db.asset_compliance.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"controlId": control_id, "lastUpdated": datetime.datetime.utcnow().isoformat()}}
                )
            migrated_count += 1
            # Explicitly fetch the updated document for internal dedupe or reload it
            doc = await db.asset_compliance.find_one({"_id": doc["_id"]})
            if not doc: continue # Deleted in merge

        # 3. Deduplicate evidence within the record
        evidence = doc.get("evidence", [])
        if evidence:
            unique_evidence = {}
            for e in evidence:
                name = e.get("name")
                # Keep latest evidence for each name
                if name not in unique_evidence or e.get("uploadedAt", "") > unique_evidence[name].get("uploadedAt", ""):
                    unique_evidence[name] = e
            
            if len(unique_evidence) < len(evidence):
                await db.asset_compliance.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"evidence": list(unique_evidence.values())}}
                )
                deduped_evidence_count += 1

    print("\n✅ Cleanup Complete!")
    print(f"  • Migrated legacy records: {migrated_count}")
    print(f"  • Consolidated duplicate records: {record_dedupe_count}")
    print(f"  • Merged/Deleted duplicate targets: {deleted_count}")
    print(f"  • Records with deduped internal evidence: {deduped_evidence_count}")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(cleanup_compliance())
