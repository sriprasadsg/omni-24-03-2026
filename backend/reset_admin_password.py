import asyncio
from database import get_database, connect_to_mongo
from auth_utils import hash_password

async def reset_super_admin_password():
    await connect_to_mongo()
    db = get_database()
    
    # First, check if user exists
    user = await db.users.find_one({'email': 'super@omni.ai'})
    
    if not user:
        print("❌ User super@omni.ai not found!")
        print("Creating new super admin user...")
        
        new_user = {
            "email": "super@omni.ai",
            "name": "Super Admin",
            "role": "Super Admin",
            "password": hash_password("admin123"),
            "tenantId": "platform",
            "createdAt": "2025-12-19T13:30:00Z"
        }
        
        result = await db.users.insert_one(new_user)
        print(f"✅ Created new super admin user with ID: {result.inserted_id}")
    else:
        print(f"✅ Found user: {user.get('email')}")
        print(f"   Role: {user.get('role')}")
        
        # Update password
        new_hash = hash_password("admin123")
        await db.users.update_one(
            {'email': 'super@omni.ai'},
            {'$set': {'password': new_hash}}
        )
        print("✅ Password updated to: admin123")
        print(f"   New hash starts with: {new_hash[:20]}...")

    # Verify the update worked
    updated_user = await db.users.find_one({'email': 'super@omni.ai'})
    print(f"\nVerification:")
    print(f"  Email: {updated_user.get('email')}")
    print(f"  Role: {updated_user.get('role')}")
    print(f"  Has password: {bool(updated_user.get('password'))}")
    print(f"  Password hash: {updated_user.get('password')[:30]}...")

asyncio.run(reset_super_admin_password())
