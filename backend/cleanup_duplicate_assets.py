"""
Remove duplicate assets from MongoDB.
Keep only the most recent entry based on lastSeen timestamp.
"""
from pymongo import MongoClient
from urllib.parse import quote_plus
from datetime import datetime

# Connect to MongoDB with URL-encoded credentials
username = quote_plus('omni_app')
password = quote_plus('SecureApp#2025!MongoDB')
client = MongoClient(f'mongodb://{username}:{password}@localhost:27017/omni_agent_db')
db = client['omni_agent_db']

print("🔍 Checking for duplicate assets...")

# Aggregate to find duplicate IDs
pipeline = [
    {"$group": {
        "_id": "$id",
        "count": {"$sum": 1},
        "entries": {"$push": "$$ROOT"}
    }},
    {"$match": {"count": {"$gt": 1}}}
]

duplicates =  list(db.assets.aggregate(pipeline))

if not duplicates:
    print("✅ No duplicate assets found!")
else:
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
            result = db.assets.delete_one({"_id": entry['_id']})
            if result.deleted_count > 0:
                total_removed += 1
    
    print(f"\n✅ Cleanup complete! Removed {total_removed} duplicate asset(s).")

# Verify
total_assets = db.assets.count_documents({})
unique_ids = len(db.assets.distinct("id"))

print(f"\n📊 Final Stats:")
print(f"  Total assets: {total_assets}")
print(f"  Unique IDs: {unique_ids}")

if total_assets == unique_ids:
    print(f"  ✅ All assets have unique IDs!")
else:
    print(f"  ⚠️  Warning: Still have {total_assets - unique_ids} duplicates")

client.close()
