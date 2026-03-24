import asyncio
import motor.motor_asyncio

async def clear_and_verify():
    try:
        client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')
        db = client['omni_agent']
        
        # Clear collection
        res = await db.asset_compliance.delete_many({})
        print(f"✅ Cleared {res.deleted_count} records from asset_compliance")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(clear_and_verify())
