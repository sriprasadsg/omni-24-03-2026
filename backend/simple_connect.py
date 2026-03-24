
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

async def main():
    print("Starting minimal check...", flush=True)
    uri = "mongodb://localhost:27017"
    db_name = "omni_platform"
    
    print(f"Connecting to {uri}...", flush=True)
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    

    print("Listing collections...", flush=True)
    try:
        # cols = await db.list_collection_names()
        # print(f"Collections: {cols}", flush=True)
        
        count = await db.assets.count_documents({})
        print(f"Assets count: {count}", flush=True)
        
        if count > 0:
            cursor = db.assets.find({}, {"id": 1, "tenantId": 1})
            all_ids = []
            async for doc in cursor:
                all_ids.append(doc.get("id"))
                
            from collections import Counter
            counts = Counter(all_ids)
            
            duplicates = {k: v for k, v in counts.items() if v > 1}
            
            if duplicates:
                print(f"FOUND DUPLICATES: {len(duplicates)}", flush=True)
                for dup_id, count in duplicates.items():
                    print(f"Duplicate ID: {dup_id} (Count: {count})", flush=True)
            else:
                print("NO DUPLICATES FOUND", flush=True)
                
    except Exception as e:
        print(f"Error: {e}", flush=True)
    finally:
        client.close()
        print("Closed.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
