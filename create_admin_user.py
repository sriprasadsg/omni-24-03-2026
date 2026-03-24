
import sys
import os

# Add backend to sys.path primarily
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, mongodb
import asyncio
import bcrypt

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


async def create_admin():
    await connect_to_mongo()
    
    # Check if user exists
    existing = await mongodb.db.users.find_one({"email": "admin@example.com"})
    if existing:
        print("User admin@example.com already exists. Updating password to 'admin123'...")
        hashed = get_password_hash("admin123")
        await mongodb.db.users.update_one(
            {"email": "admin@example.com"},
            {"$set": {"password": hashed, "role": "Super Admin", "name": "Super Admin"}}
        )
    else:
        print("Creating admin@example.com...")
        hashed = get_password_hash("admin123")
        user = {
            "id": "user_admin_001",
            "email": "admin@example.com",
            "password": hashed,
            "name": "Super Admin",
            "role": "Super Admin",
            "tenantId": "platform-admin",
            "status": "Active"
        }
        await mongodb.db.users.insert_one(user)
    
    print("User ready: admin@example.com / admin123")
    
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(create_admin())
