
import asyncio
import os
import sys
import motor.motor_asyncio
import bcrypt

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

async def update_password():
    print("Connecting to DB...")
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    print(f"Hashing password for {USER_EMAIL}...")
    hashed = get_password_hash(NEW_PASSWORD)
    
    res = await db.users.update_one(
        {"email": USER_EMAIL},
        {"$set": {"password": hashed}}
    )
    
    if res.modified_count > 0:
        print("Password updated successfully.")
    else:
        print("User not found or password unchanged.")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(update_password())
