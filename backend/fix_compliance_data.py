import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import random
from datetime import datetime, timezone

load_dotenv()
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")

async def fix_data():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[MONGODB_DB_NAME]
    print(f"Connected to {MONGODB_DB_NAME}")

    # 1. Get Tenants
    tenants_from_users = await db.users.distinct("tenantId")
    tenants_from_tenants = await db.tenants.distinct("id")
    # Union list
    all_tenants = list(set(tenants_from_users + tenants_from_tenants))
    
    # Ensure platform-admin is there (it might not have assets but good to check)
    if "platform-admin" not in all_tenants:
        all_tenants.append("platform-admin")

    print(f"Found Tenants: {all_tenants}")
    
    # 2. Get Frameworks
    frameworks = await db.compliance_frameworks.find({}).to_list(length=100)
    print(f"Found {len(frameworks)} Frameworks")
    
    if not frameworks:
        print("CRITICAL: No frameworks found! Run seed_compliance.py first.")
        # We won't try to fix frameworks here to keep script focused
    
    # 3. For each tenant, ensure evidence
    for tenant_id in all_tenants:
        if not tenant_id: continue
        print(f"\nProcessing Tenant: {tenant_id}")
        
        # Get Assets for this tenant
        assets = await db.assets.find({"tenantId": tenant_id}).to_list(length=100)
        print(f"  Found {len(assets)} assets")
        
        if not assets:
            print(f"  WARNING: No assets for tenant {tenant_id}. Creating a dummy asset to enable testing.")
            dummy_asset = {
                "id": f"asset-dummy-{tenant_id}",
                "name": "Dummy Asset for Compliance",
                "type": "Server",
                "tenantId": tenant_id,
                "status": "Active"
            }
            await db.assets.insert_one(dummy_asset)
            assets = [dummy_asset]
            print(f"  Created dummy asset: {dummy_asset['id']}")

        # Seed Evidence
        evidence_count = 0
        for asset in assets:
            # Pick a few controls from each framework
            for fw in frameworks:
                controls = fw.get('controls', [])
                # Seed evidence for first 5 controls
                for control in controls[:5]:
                    control_id = control.get('id')
                    
                    # Check existence
                    exists = await db.asset_compliance.find_one({
                        "tenantId": tenant_id,
                        "assetId": asset['id'],
                        "controlId": control_id
                    })
                    
                    if not exists:
                        # Create evidence
                        status = random.choice(["Compliant", "Non-Compliant", "Pending"])
                        doc = {
                            "tenantId": tenant_id,
                            "assetId": asset['id'],
                            "controlId": control_id,
                            "frameworkId": fw['id'],
                            "status": status,
                            "evidence": [], # Can add dummy evidence if needed
                            "lastUpdated": datetime.now(timezone.utc).isoformat()
                        }
                        await db.asset_compliance.insert_one(doc)
                        evidence_count += 1
        
        print(f"  Seeded {evidence_count} evidence records for tenant {tenant_id}")

    client.close()

if __name__ == "__main__":
    asyncio.run(fix_data())
