import asyncio
import motor.motor_asyncio
import json

async def investigate():
    try:
        # Use authenticated connection
        url = "mongodb://omni_app:SecureApp%232025!MongoDB@localhost:27017/omni_platform?authSource=omni_platform"
        client = motor.motor_asyncio.AsyncIOMotorClient(url)
        db = client['omni_platform']
        
        # Check asset existence
        asset = await db.assets.find_one({"id": "asset-BLID197"}, {"_id": 0})
        if asset:
            print(f"✅ Found asset: {asset.get('hostname')} ({asset.get('id')})")
            print(f"   Has compliance data: {'compliance_enforcement' in asset.get('meta', {})}")
            if 'compliance_enforcement' in asset.get('meta', {}):
                checks = asset['meta']['compliance_enforcement'].get('compliance_checks', [])
                print(f"   Number of checks: {len(checks)}")
        else:
            print("❌ Asset asset-BLID197 not found")
            
        # Check compliance records for this asset
        cursor = db.asset_compliance.find({"assetId": "asset-BLID197"}, {"_id": 0})
        records = await cursor.to_list(length=100)
        print(f"\n✅ Found {len(records)} compliance records for BLID197")
        for r in records[:10]:
            print(f"   {r.get('controlId')}: {r.get('status')} (Evidence: {len(r.get('evidence', []))})")
            
        # Check specifically for CC1.1
        cc11 = await db.asset_compliance.find_one({"assetId": "asset-BLID197", "controlId": "CC1.1"}, {"_id": 0})
        print(f"\n CC1.1 record: {json.dumps(cc11, indent=2) if cc11 else 'NOT FOUND'}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(investigate())
