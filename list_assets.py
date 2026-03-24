import asyncio
import motor.motor_asyncio

async def list_assets():
    try:
        url = "mongodb://omni_app:SecureApp%232025!MongoDB@localhost:27017/omni_platform?authSource=omni_platform"
        client = motor.motor_asyncio.AsyncIOMotorClient(url)
        db = client['omni_platform']
        
        cursor = db.assets.find({}, {"_id": 0, "id": 1, "hostname": 1})
        assets = await cursor.to_list(length=100)
        
        print(f"✅ Found {len(assets)} assets:")
        for a in assets:
            print(f"   {a.get('id')} ({a.get('hostname')})")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(list_assets())
