import asyncio
import os
import sys
import uuid
import random
from datetime import datetime, timezone, timedelta

# Import paths for backend
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from motor.motor_asyncio import AsyncIOMotorClient
import database

async def seed_vulnerabilities():
    print("Connecting to database...")
    await database.connect_to_mongo()
    db = database.get_database()
    
    tenant = await db.tenants.find_one({"id": "platform-admin"})
    if not tenant:
        print("Tenant 'platform-admin' not found.")
        return
    tenant_id = tenant.get("id")
    print(f"Targeting Tenant ID: {tenant_id}")
    
    # Get some assets to attach vulns to
    assets = await db.assets.find({"tenantId": tenant_id}).to_list(10)
    asset_ids = [a.get("id") for a in assets]
    
    if not asset_ids:
        print("No assets found for tenant. Creating a dummy asset for vulnerabilities.")
        asset_id = str(uuid.uuid4())
        await db.assets.insert_one({
            "id": asset_id,
            "tenantId": tenant_id,
            "hostname": "win-server-prod-01",
            "os": "Windows Server 2022",
            "ipAddress": "10.0.50.12",
            "status": "Online",
            "lastSeen": datetime.now(timezone.utc).isoformat()
        })
        asset_ids.append(asset_id)

    # Sample CVEs
    cve_data = [
        {"cveId": "CVE-2021-44228", "severity": "Critical", "description": "Apache Log4j2 JNDI features do not protect against attacker controlled LDAP...", "affected": "Apache Log4j 2.14.1"},
        {"cveId": "CVE-2023-38831", "severity": "Critical", "description": "WinRAR before 6.23 allows attackers to execute arbitrary code...", "affected": "WinRAR 6.22"},
        {"cveId": "CVE-2024-21412", "severity": "High", "description": "Internet Shortcut Files Security Feature Bypass Vulnerability", "affected": "Windows 11 22H2"},
        {"cveId": "CVE-2023-4863", "severity": "High", "description": "Heap buffer overflow in libwebp allowed a remote attacker...", "affected": "Google Chrome < 116.0.5845.187"},
        {"cveId": "CVE-2021-34527", "severity": "Critical", "description": "Windows Print Spooler Remote Code Execution Vulnerability (PrintNightmare)", "affected": "Windows Server 2019"},
        {"cveId": "CVE-2023-23397", "severity": "Critical", "description": "Microsoft Outlook Elevation of Privilege Vulnerability", "affected": "Microsoft Office 365 Outlook"},
        {"cveId": "CVE-2022-22965", "severity": "High", "description": "Spring Framework RCE via Data Binding on JDK 9+ (Spring4Shell)", "affected": "Spring Framework 5.3.17"},
        {"cveId": "CVE-2023-36884", "severity": "High", "description": "Office and Windows HTML Remote Code Execution Vulnerability", "affected": "Microsoft Office 2019"},
        {"cveId": "CVE-2024-3094", "severity": "Critical", "description": "Malicious code discovered in the upstream tarballs of xz", "affected": "xz-utils 5.6.0"},
        {"cveId": "CVE-2017-0144", "severity": "Medium", "description": "SMBv1 Remote Code Execution (WannaCry related)", "affected": "Windows 7 (Legacy)"},
    ]

    print("Clearing old vulnerabilities...")
    await db.vulnerabilities.delete_many({"tenantId": tenant_id})
    
    vulns_to_insert = []
    
    for cve in cve_data:
        # Determine status
        rand_val = random.random()
        status = "Open"
        if rand_val > 0.8:
            status = "Patched"
        elif rand_val > 0.7:
            status = "Risk Accepted"
            
        now = datetime.now(timezone.utc)
        discovered_days_ago = random.randint(1, 90)
        discovered_at = now - timedelta(days=discovered_days_ago)
        
        assigned_asset = random.choice(asset_ids)
        
        vuln = {
            "id": f"vuln-{str(uuid.uuid4())[:8]}",
            "tenantId": tenant_id,
            "cveId": cve["cveId"],
            "severity": cve["severity"],
            "status": status,
            "description": cve["description"],
            "affectedSoftware": cve["affected"],
            "discoveredAt": discovered_at.isoformat(),
            "assetId": assigned_asset,
            "updatedAt": now.isoformat()
        }
        vulns_to_insert.append(vuln)
        
    if vulns_to_insert:
        await db.vulnerabilities.insert_many(vulns_to_insert)
        print(f"Successfully seeded {len(vulns_to_insert)} vulnerabilities into tenant '{tenant_id}'.")

if __name__ == "__main__":
    asyncio.run(seed_vulnerabilities())
