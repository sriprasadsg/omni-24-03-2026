from database import get_database, connect_to_mongo
from auth_utils import hash_password
import asyncio

async def reset_password():
    await connect_to_mongo()
    db = get_database()
    email = "super@omni.ai"
    new_password = "admin"
    hashed_password = hash_password(new_password)
    print(f"Hashed password: {hashed_password}")
    
    result = await db.users.update_one(
        {"email": email},
        {"$set": {"password": hashed_password}}
    )
    
    if result.modified_count > 0:
        print(f"Password for {email} reset successfully.")
    else:
        print(f"User {email} not found or password unchanged.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(reset_password())
