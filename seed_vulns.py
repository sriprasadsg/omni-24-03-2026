import asyncio
import os
import sys
from datetime import datetime, timezone
import uuid

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database

async def seed_vulnerabilities():
    await connect_to_mongo()
    db = get_database()
    
    print("Seeding vulnerabilities for platform-admin...")
    
    # Get some assets to link to
    assets = await db.assets.find().to_list(length=5)
    if not assets:
        print("No assets found. Using dummy asset IDs.")
        asset_ids = [f"asset-{uuid.uuid4()}" for _ in range(2)]
    else:
        asset_ids = [a["id"] for a in assets]

    vulns = [
        {
            "id": f"vuln-{uuid.uuid4()}",
            "tenantId": "platform-admin",
            "assetId": asset_ids[0],
            "cveId": "CVE-2024-1234",
            "severity": "Critical",
            "status": "Open",
            "affectedSoftware": "OpenSSL 3.0.1",
            "discoveredAt": datetime.now(timezone.utc).isoformat(),
            "description": "Buffer overflow in OpenSSL allows remote code execution."
        },
        {
            "id": f"vuln-{uuid.uuid4()}",
            "tenantId": "platform-admin",
            "assetId": asset_ids[0],
            "cveId": "CVE-2023-5678",
            "severity": "High",
            "status": "Open",
            "affectedSoftware": "Apache HTTP Server 2.4.54",
            "discoveredAt": datetime.now(timezone.utc).isoformat(),
            "description": "Path traversal vulnerability in Apache HTTP Server."
        },
        {
            "id": f"vuln-{uuid.uuid4()}",
            "tenantId": "platform-admin",
            "assetId": asset_ids[1] if len(asset_ids) > 1 else asset_ids[0],
            "cveId": "CVE-2024-9999",
            "severity": "Medium",
            "status": "Patched",
            "affectedSoftware": "Windows Kernel",
            "discoveredAt": datetime.now(timezone.utc).isoformat(),
            "description": "Privilege escalation in Windows Kernel."
        }
    ]
    
    await db.vulnerabilities.insert_many(vulns)
    print(f"Successfully seeded {len(vulns)} vulnerabilities.")

if __name__ == "__main__":
    asyncio.run(seed_vulnerabilities())
