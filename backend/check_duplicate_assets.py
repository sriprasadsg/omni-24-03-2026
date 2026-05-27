from pymongo import MongoClient
import os

_mongo_url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
_mongo_db = os.environ.get("MONGODB_DB_NAME", "omni_platform")
client = MongoClient(_mongo_url)
db = client[_mongo_db]

# Get all assets
assets = list(db.assets.find({}))

print(f"Total assets in database: {len(assets)}")
print(f"Unique asset IDs: {len(set([a['id'] for a in assets]))}")

# Find duplicates
id_counts = {}
for asset in assets:
    asset_id = asset['id']
    if asset_id not in id_counts:
        id_counts[asset_id] = []
    id_counts[asset_id].append(asset)

duplicates = {id:entries for id, entries in id_counts.items() if len(entries) > 1}

if duplicates:
    print(f"\n❌ Found {len(duplicates)} duplicate asset ID(s):")
    for asset_id, entries in duplicates.items():
        print(f"\n  Asset ID: {asset_id}")
        print(f"  Count: {len(entries)}")
        for i, entry in enumerate(entries):
            print(f"    Entry {i+1}:")
            print(f"      _id: {entry['_id']}")
            print(f"      hostname: {entry.get('hostname', 'N/A')}")
            print(f"      lastScanned: {entry.get('lastScanned', 'N/A')}")
else:
    print("\n✅ No duplicates found!")

client.close()
