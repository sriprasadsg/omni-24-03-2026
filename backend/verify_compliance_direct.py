import pymongo
client = pymongo.MongoClient("mongodb://127.0.0.1:27017")
db = client["omni_platform"]

assets = db.asset_compliance.distinct("assetId")
print(f"Active Assets in Compliance: {assets}")

# Check PCI-DSS 8.1.1 (Password Policy)
pci_811 = db.asset_compliance.find_one({"controlId": "PCI-8.1.1"})
print(f"\nPassword Policy (PCI-8.1.1) Status: {pci_811.get('status') if pci_811 else 'Not Found'}")
if pci_811 and "evidence" in pci_811:
    print(f"Evidence items: {len(pci_811['evidence'])}")

# Check PCI-DSS 3.4 (BitLocker)
pci_34 = db.asset_compliance.find_one({"controlId": "PCI-3.4"})
print(f"BitLocker (PCI-3.4) Status: {pci_34.get('status') if pci_34 else 'Not Found'}")

# Check CC6.1 (General settings)
cc61 = db.asset_compliance.find_one({"controlId": "CC6.1"})
print(f"General Sec (CC6.1) Status: {cc61.get('status') if cc61 else 'Not Found'}")

elevated = db.asset_compliance.count_documents({"evidence.elevated": True})
print(f"\nTotal elevated checks correctly stored: {elevated}")
