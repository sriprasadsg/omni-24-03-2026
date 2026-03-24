from pymongo import MongoClient
from urllib.parse import quote_plus

# Connect to MongoDB with URL-encoded credentials
username = quote_plus('omni_app')
password = quote_plus('SecureApp#2025!MongoDB')
client = MongoClient(f'mongodb://{username}:{password}@localhost:27017/omni_agent_db')
db = client['omni_agent_db']

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
