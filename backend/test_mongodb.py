import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def test_mongodb():
    try:
        client = AsyncIOMotorClient('mongodb://localhost:27017')
        info = await client.server_info()
        print(f"✅ MongoDB Connected!")
        print(f"Version: {info.get('version', 'unknown')}")
        
        # Test database access
        db = client['omni_platform']
        collections = await db.list_collection_names()
        print(f"Collections: {collections}")
        
        # Check for super admin user
        user = await db.users.find_one({"email": "super@omni.ai"})
        if user:
            print(f"✅ Super admin user exists: {user.get('email')}")
        else:
            print("⚠️ Super admin user NOT found in database")
            
        client.close()
        return True
    except Exception as e:
        print(f"❌ MongoDB Connection Error: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_mongodb())
    exit(0 if result else 1)
