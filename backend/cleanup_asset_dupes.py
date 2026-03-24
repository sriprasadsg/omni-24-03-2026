
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from collections import Counter

async def cleanup_duplicates():
    print("Starting cleanup...", flush=True)
    uri = "mongodb://localhost:27017"
    db_name = "omni_platform"
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    
    try:
        # 1. Find all duplicates
        cursor = db.assets.find({}, {"id": 1})
        all_ids = []
        async for doc in cursor:
            if doc.get("id"):
                all_ids.append(doc.get("id"))
        
        counts = Counter(all_ids)
        duplicates = [aid for aid, count in counts.items() if count > 1]
        
        print(f"Found {len(duplicates)} duplicate IDs: {duplicates}", flush=True)
        
        for aid in duplicates:
            print(f"Processing duplicate: {aid}", flush=True)
            # Find all instances
            instances = await db.assets.find({"id": aid}).to_list(length=100)
            
            # Keep the first one (or arguably the one with most info? For now just first)
            # Actually, let's keep the one with _id that is latest? Or does it matter?
            # Let's just keep the first one found and delete others.
            
            if len(instances) > 1:
                keep_id = instances[0]["_id"]
                remove_ids = [doc["_id"] for doc in instances[1:]]
                
                print(f"  Keeping _id: {keep_id}", flush=True)
                print(f"  Removing {len(remove_ids)} instances...", flush=True)
                
                result = await db.assets.delete_many({"_id": {"$in": remove_ids}})
                print(f"  Deleted {result.deleted_count} documents.", flush=True)
                
        print("Cleanup complete.", flush=True)
        
    except Exception as e:
        print(f"Error: {e}", flush=True)
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(cleanup_duplicates())
