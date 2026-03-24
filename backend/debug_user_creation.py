
import asyncio
from database import get_database, connect_to_mongo
from auth_utils import hash_password, verify_password

async def debug_user():
    print("Connecting to Mongo...")
    await connect_to_mongo()
    db = get_database()
    
    email = "super@omni.ai"
    password = "superpassword"
    
    print(f"Creating user {email}...")
    
    # 1. Hash password
    hashed = hash_password(password)
    print(f"Generated hash: {hashed}")
    
    # 2. Verify hash immediately locally
    is_valid = verify_password(password, hashed)
    print(f"Immediate verification check: {is_valid}")
    
    user = {
        "id": "u-super-admin",
        "email": email,
        "password": hashed,
        "name": "Super Admin",
        "role": "Super Admin",
        "tenantId": "platform-admin",
        "status": "Active",
        "avatar": "https://github.com/shadcn.png"
    }
    
    # 3. Insert/Update
    result = await db.users.update_one(
        {"email": email}, 
        {"$set": user}, 
        upsert=True
    )
    print(f"Update result: matched={result.matched_count}, modified={result.modified_count}, upserted={result.upserted_id}")
    
    # 4. Read back
    fetched_user = await db.users.find_one({"email": email})
    if fetched_user:
        print(f"User retrieved from DB: {fetched_user['email']}")
        print(f"Stored hash: {fetched_user['password']}")
        
        # 5. Verify retrieved hash
        is_valid_db = verify_password(password, fetched_user['password'])
        print(f"DB Hash verification check: {is_valid_db}")
        
    else:
        print("ERROR: User not found in DB after update!")

if __name__ == "__main__":
    asyncio.run(debug_user())
