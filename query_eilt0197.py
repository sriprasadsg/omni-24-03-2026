import pymongo, json, re

client = pymongo.MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)

print("=== Searching all collections for EILT0197 ===\n")

for db_name in ["omni_platform", "omni_agent_db", "omni", "agentic_ai_enterprise", "autonomous_guardians", "hybrid_siem", "omni-agent-queue"]:
    db = client[db_name]
    for col in db.list_collection_names():
        try:
            doc = None
            for field in ["hostname", "assetId", "name", "asset_id", "id"]:
                doc = db[col].find_one({field: re.compile("EILT0197", re.I)})
                if doc:
                    break
            if doc:
                doc.pop("_id", None)
                skip = {"software", "installedSoftware", "installed_software",
                        "software_inventory", "os_patches", "compliance_checks"}
                print(f"=== FOUND: {db_name}.{col} ===")
                for k, v in doc.items():
                    if k not in skip:
                        print(f"  {k}: {str(v)[:250]}")
                print()
        except Exception as e:
            pass

# Also run detect_device_type-equivalent directly on stored data
print("\n=== Software clues for EILT0197 (top 20) ===")
db = client["agentic_ai_enterprise"]
doc = db["agents"].find_one({"hostname": "EILT0197"})
if doc:
    sw = doc.get("software", [])
    server_hints = ["iis", "sql server", "oracle", "apache", "nginx", "active directory",
                    "exchange", "hyper-v", "windows server", "vcenter", "esxi", "tomcat",
                    "postgresql", "mysql", "redis", "kafka", "zabbix"]
    laptop_hints = ["epson", "easy photo", "hp support", "hp notifications", "battery",
                    "intel graphics", "realtek audio", "lenovo", "thinkpad", "dell inspiron",
                    "acer", "asus", "anyconnect", "zoom", "teams", "onedrive", "skype"]
    server_found = []
    laptop_found = []
    for s in sw:
        name = s.get("name", "").lower()
        for h in server_hints:
            if h in name:
                server_found.append(s["name"])
        for h in laptop_hints:
            if h in name:
                laptop_found.append(s["name"])
    print(f"Server-type software: {server_found}")
    print(f"Laptop/user-type software: {laptop_found}")
    print(f"\nTotal installed packages: {len(sw)}")

print("\nDone.")
