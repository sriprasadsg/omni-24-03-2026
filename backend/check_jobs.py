import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json
import os

async def check():
    mongodb_url = "mongodb://localhost:27017"
    mongodb_db_name = "omni_platform"
    client = AsyncIOMotorClient(mongodb_url)
    db = client[mongodb_db_name]
    
    jobs = await db.patch_deployment_jobs.find({}, {"_id": 0}).sort("createdAt", -1).limit(5).to_list(length=5)
    print(json.dumps(jobs, indent=2))
    client.close()

if __name__ == "__main__":
    asyncio.run(check())
