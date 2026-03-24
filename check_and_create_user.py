
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["omni_platform"]
    
    email = "super@omni.ai"
    password = "password123"
    
    user = await db.users.find_one({"email": email})
    
    if user:
        print(f"User {email} found.")
        # Verify password
        if verify_password(password, user["password"]):
            print("Password matches.")
        else:
            print("Password does NOT match. Updating password...")
            hashed = get_password_hash(password)
            await db.users.update_one({"email": email}, {"$set": {"password": hashed}})
            print("Password updated.")
    else:
        print(f"User {email} NOT found. Creating...")
        hashed = get_password_hash(password)
        new_user = {
            "email": email,
            "username": "superadmin",
            "password": hashed,
            "role": "super_admin",
            "tenantId": "default", # essential for token
            "is_active": True
        }
        await db.users.insert_one(new_user)
        print(f"User {email} created.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
