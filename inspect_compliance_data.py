
import sys
import os
import json
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pprint import pprint

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def inspect_data():
    # Connect to Mongo
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.omni_platform
    
    hostname = "desktop-rust-agent"
    asset = await db.assets.find_one({"hostname": hostname})
    
    if not asset:
        print(f"Asset for {hostname} not found!")
        return

    print(f"Asset Found: {asset['id']}")
    print(f"Tenant ID: {asset.get('tenantId')}")
    
    # Check Compliance
    control_id = "pci-dss-PCI-1.1.1" # Mapped from Windows Firewall Profiles
    compliance_record = await db.asset_compliance.find_one({
        "assetId": asset['id'],
        "controlId": control_id
    })
    
    if not compliance_record:
        print(f"No compliance record found for Control {control_id}")
        
        # List all compliance records for this asset
        print("Listing all compliance records for this asset:")
        async for doc in db.asset_compliance.find({"assetId": asset['id']}):
            print(f"- {doc.get('controlId')}: {doc.get('status')} (Evidence count: {len(doc.get('evidence', []))})")
            
    else:
        print(f"Compliance Record Found for {control_id}:")
        print(f"Status: {compliance_record.get('status')}")
        evidence = compliance_record.get('evidence', [])
        print(f"Evidence Count: {len(evidence)}")
        if evidence:
            print("First Evidence Item:")
            pprint(evidence[0])
            
    client.close()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(inspect_data())
