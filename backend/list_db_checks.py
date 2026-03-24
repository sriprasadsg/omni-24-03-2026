import pymongo
client = pymongo.MongoClient("mongodb://127.0.0.1:27017")
db = client["omni_platform"]

assets = db.asset_compliance.distinct("assetId")
if not assets:
    print("NO ASSETS FOUND IN asset_compliance")
    exit()

target_asset = assets[0]
print(f"Targeting: {target_asset}")

checks = db.asset_compliance.find({"assetId": target_asset})
print("\n--- Available Check Names in DB ---")
for c in checks:
    print(f"Name: '{c.get('check_name')}' | Status: {c.get('status')}")
