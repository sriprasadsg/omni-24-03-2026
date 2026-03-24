import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

async def check():
    from database import mongodb, connect_to_mongo
    await connect_to_mongo()
    
    for db_name in ['omni_platform', 'omni_agent_db']:
        db = mongodb.client[db_name]
        print(f"--- Database: {db_name} ---")
        for col in ['compliance_frameworks', 'ai_models', 'ai_policies']:
            count = await db[col].count_documents({})
            print(f"Collection: {col} | Count: {count}")

if __name__ == "__main__":
    asyncio.run(check())
