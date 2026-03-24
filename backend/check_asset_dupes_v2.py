
import asyncio

from database import mongodb, connect_to_mongo, close_mongo_connection
from tenant_context import get_tenant_id
from collections import Counter

async def check_duplicate_assets():
    print("Starting duplicate check...")
    try:
        await connect_to_mongo()
        

        # Bypass TenantIsolatedDatabase wrapper
        db = mongodb.db
        if db is None:
            print("ERROR: Database connection failed (db is None)", flush=True)
            return

        print(f"Current Tenant ID context: {get_tenant_id()}", flush=True)
        
        # List collections to verify connection
        cols = await db.list_collection_names()
        print(f"Collections: {cols}", flush=True)

        # Count total documents first
        print("Counting assets...", flush=True)
        total_docs = await db.assets.count_documents({})
        print(f"Total documents in 'assets' collection: {total_docs}", flush=True)
        
        if total_docs == 0:
            print("No assets found in database.")
            await close_mongo_connection()
            return

        unique_ids = set()
        all_ids = []
        
        print("Fetching assets...")
        cursor = db.assets.find({}, {"id": 1, "name": 1, "tenantId": 1})
        
        count = 0
        async for asset in cursor:
            count += 1
            if count % 100 == 0:
                print(f"Processed {count} assets...")
                
            asset_id = asset.get("id")
            if asset_id:
                all_ids.append(asset_id)
                if asset_id in unique_ids:
                    print(f"DUPLICATE FOUND: {asset_id} - {asset.get('name')} (Tenant: {asset.get('tenantId')})")
                else:
                    unique_ids.add(asset_id)
                    
        duplicate_count = len(all_ids) - len(unique_ids)
        print(f"\nFinal Report:")
        print(f"Total Assets Processed: {len(all_ids)}")
        print(f"Unique Assets: {len(unique_ids)}")
        print(f"Duplicate Count: {duplicate_count}")
        
        if duplicate_count > 0:
            print("\nDetailed Duplicate Analysis:")
            counts = Counter(all_ids)
            for aid, count in counts.items():
                if count > 1:
                    print(f"Asset ID {aid} appears {count} times")
                    dupes = await db.assets.find({"id": aid}).to_list(length=100)
                    for i, d in enumerate(dupes):
                        print(f"  Instance {i+1}: _id={d.get('_id')}, name={d.get('name')}, tenantId={d.get('tenantId')}")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check_duplicate_assets())
