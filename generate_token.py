
import asyncio
import os
import sys
import motor.motor_asyncio
from datetime import timedelta

# Ensure backend modules are importable
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Import token creator
from backend.authentication_service import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = "omni_platform"

TENANT_ID = "tenant_82dda0f33bc4" # Found earlier
USER_EMAIL = "admin@exafluence.com"

async def generate_token():
    print("Connecting to DB...")
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    # 1. Check/Create User
    print(f"Checking for user {USER_EMAIL} in tenant {TENANT_ID}...")
    user = await db.users.find_one({"email": USER_EMAIL})
    
    if not user:
        print("User not found. Creating...")
        # Basic user struct
        new_user = {
            "email": USER_EMAIL,
            "username": "Exafluence Admin",
            "password": "hashed_password_placeholder", # Agent doesn't need login pass really, just token
            "role": "Tenant Admin",
            "tenantId": TENANT_ID,
            "createdAt": "2025-12-25T00:00:00Z"
        }
        await db.users.insert_one(new_user)
        user = new_user
        print("User created.")
    else:
        print("User found.")
        # Ensure tenant ID matches just in case
        if user.get("tenantId") != TENANT_ID:
            print(f"WARNING: User tenant {user.get('tenantId')} != {TENANT_ID}. Updating...")
            await db.users.update_one({"_id": user["_id"]}, {"$set": {"tenantId": TENANT_ID}})

    # 2. Generate Token
    print("Generating Token...")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES * 24 * 30) # 30 days for agent
    
    token = create_access_token(
        data={"sub": USER_EMAIL, "role": user["role"], "tenant_id": TENANT_ID},
        expires_delta=access_token_expires
    )
    
    print("\n--- TOKEN START ---")
    print(token)
    print("--- TOKEN END ---\n")
    
    with open("token.txt", "w") as f:
        f.write(token)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(generate_token())
