from auth_utils import hash_password, verify_password
from database import connect_to_mongo, close_mongo_connection, get_database
import asyncio

async def test_auth():
    print("--- Testing Auth Utils ---")
    pw = "password123"
    hashed = hash_password(pw)
    print(f"Password: {pw}")
    print(f"Hashed: {hashed}")
    
    verify_result = verify_password(pw, hashed)
    print(f"Verify (fresh hash): {verify_result}")
    
    if not verify_result:
        print("CRITICAL: Newly hashed password failed verification!")
        
    await connect_to_mongo()
    db = get_database()
    user = await db.users.find_one({"email": "super@omni.ai"})
    
    if user:
        print(f"Found user: {user['email']}")
        stored_hash = user.get('hashed_password') or user.get('password')
        print(f"Stored Hash in DB: {stored_hash}")
        
        db_verify = verify_password(pw, stored_hash)
        print(f"Verify against DB hash: {db_verify}")
        
        if not db_verify:
            print("Resetting password to known valid hash...")
            new_hash = hash_password(pw)
            await db.users.update_one(
                {"email": "super@omni.ai"},
                {"$set": {"hashed_password": new_hash}}
            )
            print("Password reset complete. Try logging in now.")
            
            # Double check
            user_refetch = await db.users.find_one({"email": "super@omni.ai"})
            verify_refetch = verify_password(pw, user_refetch['hashed_password'])
            print(f"Verify after reset: {verify_refetch}")
    else:
        print("User super@omni.ai NOT FOUND in DB.")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(test_auth())
