import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def check_user():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.omni_platform
    
    user = await db.users.find_one({"email": "admin@exafleucne.com"})
    if user:
        # Remove _id for JSON serialization
        user.pop('_id', None)
        print(json.dumps(user, indent=2))
    else:
        print("User NOT found")
    
    client.close()

asyncio.run(check_user())
