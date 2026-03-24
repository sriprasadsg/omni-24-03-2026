import asyncio
import motor.motor_asyncio

async def clear_and_verify():
    try:
        # Use the connection string found in update_mongodb_env.ps1
        url = "mongodb://omni_app:SecureApp%232025!MongoDB@localhost:27017/omni_platform?authSource=omni_platform"
        client = motor.motor_asyncio.AsyncIOMotorClient(url)
        db = client['omni_platform']
        
        # Clear collection
        res = await db.asset_compliance.delete_many({})
        print(f"✅ Cleared {res.deleted_count} records from asset_compliance")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")

if __name__ == "__main__":
    asyncio.run(clear_and_verify())
