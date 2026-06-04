import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

# Check env vars
print(f"MONGODB_URL from env: {os.getenv('MONGODB_URL')}")
print(f"MONGODB_DB_NAME from env: {os.getenv('MONGODB_DB_NAME')}")

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017")
DATABASE_NAME = os.getenv("MONGODB_DB_NAME", "ai_platform")

async def analyze_db():
    print(f"Connecting to {MONGODB_URL}...")
    client = AsyncIOMotorClient(MONGODB_URL)
    
    # List Databases
    try:
        dbs = await client.list_database_names()
        print(f"Databases found: {dbs}")
    except Exception as e:
        print(f"Error listing databases: {e}")
        return

    if DATABASE_NAME not in dbs:
        print(f"WARNING: Database '{DATABASE_NAME}' not found in {dbs}")
    
    db = client[DATABASE_NAME]
    
    params = {}
    auth_source = os.getenv("MONGODB_AUTH_SOURCE")
    if auth_source:
         params['authSource'] = auth_source

    print(f"Inspecting database: {DATABASE_NAME}")
    
    collections = await db.list_collection_names()
    print(f"Collections: {collections}")
    
    if "compliance_frameworks" in collections:
        count = await db.compliance_frameworks.count_documents({})
        print(f"compliance_frameworks count: {count}")
        if count > 0:
            sample = await db.compliance_frameworks.find_one({})
            print(f"Sample framework: {sample.get('id', 'N/A')} - Tenant: {sample.get('tenantId', 'N/A')}")
    else:
        print("compliance_frameworks collection NOT FOUND")

    if "asset_compliance" in collections:
        count = await db.asset_compliance.count_documents({})
        print(f"asset_compliance count: {count}")
        if count > 0:
            sample = await db.asset_compliance.find_one({})
            print(f"Sample compliance record: {sample.get('id', 'N/A')} - Tenant: {sample.get('tenantId', 'N/A')}")
    else:
         print("asset_compliance collection NOT FOUND")
         
    # Check for evidence related collections
    for col in collections:
        if "evidence" in col.lower():
            count = await db[col].count_documents({})
            print(f"Found evidence collection '{col}': {count} docs")

if __name__ == "__main__":
    asyncio.run(analyze_db())
