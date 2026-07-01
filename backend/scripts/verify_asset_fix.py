"""
Verify asset details are now populated
"""
import asyncio
import sys
sys.path.insert(0, '.')

from database import connect_to_mongo, get_database, close_mongo_connection

async def verify_asset():
    await connect_to_mongo()
    db = get_database()
    
    asset = await db.assets.find_one({"id": "agent-EILT0197"})
    
    if not asset:
        print("❌ Asset not found!")
        await close_mongo_connection()
        return
    
    print("✅ Asset found!\n")
    
    # Check each field
    fields_to_check = [
        ("hostname", asset.get("hostname")),
        ("ipAddress", asset.get("ipAddress")),
        ("osName", asset.get("osName")),
        ("osVersion", asset.get("osVersion")),
        ("kernel", asset.get("kernel")),
        ("cpuModel", asset.get("cpuModel")),
        ("ram", asset.get("ram")),
        ("macAddress", asset.get("macAddress")),
        ("serialNumber", asset.get("serialNumber")),
        ("lastScanned", asset.get("lastScanned")),
    ]
    
    all_populated = True
    for field_name, field_value in fields_to_check:
        status = "✅" if field_value and field_value not in ["Unknown", "Unknown CPU"] else "❌"
        print(f"{status} {field_name}: {field_value}")
        if not field_value or field_value in ["Unknown", "Unknown CPU"]:
            all_populated = False
    
    print(f"\n📊 Disks: {len(asset.get('disks', []))} found")
    print(f"📦 Installed Software: {len(asset.get('installedSoftware', []))} packages")
    
    if all_populated:
        print("\n🎉 All asset details are populated!")
    else:
        print("\n⚠️  Some fields are still missing - agent may need to send updated metadata")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(verify_asset())
