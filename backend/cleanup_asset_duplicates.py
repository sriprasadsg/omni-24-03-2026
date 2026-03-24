"""
Quick cleanup script - run this directly in the backend directory
Uses the existing database connection configuration
"""
import asyncio
import sys
sys.path.insert(0, '.')

from database import connect_to_mongo, get_database, close_mongo_connection

async def cleanup_duplicates():
    print("🔍 Connecting to MongoDB...")
    await connect_to_mongo()
    db = get_database()
    
    print("Finding duplicate assets...")
    
    # Find all duplicates
    pipeline = [
        {"$group": {
            "_id": "$id",
            "count": {"$sum": 1},
            "entries": {"$push": "$$ROOT"}
        }},
        {"$match": {"count": {"$gt": 1}}}
    ]
    
    duplicates = await db.assets.aggregate(pipeline).to_list(length=None)
    
    if not duplicates:
        print("✅ No duplicate assets found!")
        await close_mongo_connection()
        return
    
    print(f"\n⚠️  Found {len(duplicates)} asset ID(s) with duplicates:")
    
    total_removed = 0
    
    for dup_group in duplicates:
        asset_id = dup_group['_id']
        entries = dup_group['entries']
        count = dup_group['count']
        
        print(f"\n  Asset ID: {asset_id}")
        print(f"  Count: {count} entries")
        
        # Sort by lastSeen (most recent first)
        sorted_entries = sorted(
            entries,
            key=lambda x: x.get('lastSeen', ''),
            reverse=True
        )
        
        # Keep the first (most recent), delete the rest
        keep = sorted_entries[0]
        to_delete = sorted_entries[1:]
        
        print(f"  Keeping: {keep['_id']} (lastSeen: {keep.get('lastSeen', 'N/A')})")
        
        for entry in to_delete:
            print(f"  Deleting: {entry['_id']} (lastSeen: {entry.get('lastSeen', 'N/A')})")
            result = await db.assets.delete_one({"_id": entry['_id']})
            if result.deleted_count > 0:
                total_removed += 1
    
    print(f"\n✅ Cleanup complete! Removed {total_removed} duplicate asset(s).")
    
    # Verify
    total_assets = await db.assets.count_documents({})
    unique_ids_cursor = await db.assets.distinct("id")
    unique_ids = len(unique_ids_cursor)
    
    print(f"\n📊 Final Stats:")
    print(f"  Total assets: {total_assets}")
    print(f"  Unique IDs: {unique_ids}")
    
    if total_assets == unique_ids:
        print(f"  ✅ All assets have unique IDs!")
    else:
        print(f"  ⚠️  Warning: Still have {total_assets - unique_ids} duplicates")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(cleanup_duplicates())
