import pymongo
client = pymongo.MongoClient("mongodb://127.0.0.1:27017")
db = client["omni_platform"]

print("Finding sample compliance records...")
doc = db.asset_compliance.find_one({})
if doc:
    print(f"Sample assetId format: {doc.get('assetId')}")
    print(f"Sample check_name format: {doc.get('check_name')}")
else:
    print("No records found in asset_compliance collection.")
    
# Check how many distinct assetIds exist
assets = db.asset_compliance.distinct("assetId")
print(f"Distinct Asset IDs in DB: {assets}")
