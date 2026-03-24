import asyncio
from database import get_database, connect_to_mongo
from auth_utils import verify_password, hash_password

async def test_password():
    await connect_to_mongo()
    db = get_database()
    user = await db.users.find_one({'email': 'super@omni.ai'})
    
    if user:
        stored_password = user.get('password')
        test_password = 'admin123'
        
        print(f"Testing password for: {user.get('email')}")
        print(f"Stored password hash: {stored_password[:50]}...")
        print(f"Test password: {test_password}")
        
        # Test verification
        is_valid = verify_password(test_password, stored_password)
        print(f"\n✅ Password match: {is_valid}")
        
        if not is_valid:
            print("\n⚠️  Password doesn't match. Let's try rehashing...")
            new_hash = hash_password(test_password)
            print(f"New hash: {new_hash[:50]}...")
            
            # Update the user with the correct hash
            await db.users.update_one(
                {'email': 'super@omni.ai'},
                {'$set': {'password': new_hash}}
            )
            print("✅ Password updated in database")

asyncio.run(test_password())
