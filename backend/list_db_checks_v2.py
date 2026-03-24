import pymongo
import json
client = pymongo.MongoClient("mongodb://127.0.0.1:27017")
db = client["omni_platform"]

asset = db.assets.find_one({"id": "asset-EILT0197"})
if not asset:
    print("Asset not found in db.assets")
    # Let's check available assets
    print("Available in db.assets:", db.assets.distinct("id"))
    exit(1)

# The compliance data acts directly as keys inside capabilities.compliance_enforcement
compliance = asset.get("capabilities", {}).get("compliance_enforcement", {})
if not compliance:
    print("No compliance data active on this asset.")
    exit(1)

print("\n--- Correct Compliance Keys Found in DB ---")
for key, data in compliance.items():
    if isinstance(data, dict) and "status" in data:
        print(f"Key: '{key}' | Status: {data.get('status')} | Current Evidence: {str(data.get('evidence'))[:50]}")
    elif isinstance(data, dict):
        print(f"Key: '{key}' | Status: {data.get('status')} | Current Evidence: {str(data.get('details'))[:50]}")
