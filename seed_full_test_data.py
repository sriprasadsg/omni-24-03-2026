
import asyncio
import sys
import os
import datetime
import uuid
import random

# Ensure backend directory is in path for imports
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, mongodb, get_database

async def seed_data():
    await connect_to_mongo()
    db = get_database()
    
    tenant_name = "Exafluence"
    tenant = await mongodb.db.tenants.find_one({"name": tenant_name})
    if not tenant:
        print(f"Creating tenant {tenant_name}...")
        tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
        await mongodb.db.tenants.insert_one({
            "id": tenant_id,
            "name": tenant_name,
            "subscriptionTier": "Enterprise",
            "createdAt": datetime.datetime.utcnow().isoformat()
        })
    else:
        tenant_id = tenant['id']
        print(f"Using tenant {tenant_name} ({tenant_id})")

    # --- Agents & Assets ---
    statuses = ["Online", "Offline", "Warning"]
    platforms = ["Windows", "Linux", "macOS"]
    
    print("Seeding Agents & Assets...")
    for i in range(5):
        agent_id = f"agent-test-{i}"
        hostname = f"host-test-{i}"
        platform = random.choice(platforms)
        
        # Asset
        asset_id = f"asset-test-{i}"
        await mongodb.db.assets.update_one(
            {"id": asset_id},
            {"$set": {
                "id": asset_id,
                "tenantId": tenant_id,
                "hostname": hostname,
                "ipAddress": f"192.168.1.{10+i}",
                "os": platform,
                "status": "Active",
                "lastSeen": datetime.datetime.utcnow().isoformat()
            }},
            upsert=True
        )
        
        # Agent
        await mongodb.db.agents.update_one(
            {"id": agent_id},
            {"$set": {
                "id": agent_id,
                "tenantId": tenant_id,
                "assetId": asset_id,
                "hostname": hostname,
                "status": random.choice(statuses),
                "version": "1.0.0",
                "lastSeen": datetime.datetime.utcnow().isoformat(),
                "capabilities": ["vulnerability_scanning", "compliance_enforcement"]
            }},
            upsert=True
        )

    # --- Vulnerabilities ---
    print("Seeding Vulnerabilities...")
    vulns = [
        {"cve": "CVE-2023-1234", "severity": "Critical", "title": "Remote Code Execution"},
        {"cve": "CVE-2023-5678", "severity": "High", "title": "Privilege Escalation"},
        {"cve": "CVE-2023-9012", "severity": "Medium", "title": "Information Disclosure"},
    ]
    
    for i in range(10):
        v = random.choice(vulns)
        asset_i = random.randint(0, 4)
        vuln_id = f"vuln-{i}"
        await mongodb.db.vulnerabilities.update_one(
            {"id": vuln_id},
            {"$set": {
                "id": vuln_id,
                "tenantId": tenant_id,
                "assetId": f"asset-test-{asset_i}",
                "cveId": v["cve"],
                "severity": v["severity"],
                "title": v["title"],
                "status": "Open",
                "detectedAt": datetime.datetime.utcnow().isoformat()
            }},
            upsert=True
        )

    # --- Compliance ---
    print("Seeding Compliance...")
    frameworks = ["NIST", "ISO27001", "GDPR"]
    for i in range(3):
        f_id = f"framework-{i}"
        await mongodb.db.compliance_frameworks.update_one(
            {"id": f_id},
            {"$set": {
                "id": f_id,
                "tenantId": tenant_id,
                "name": frameworks[i],
                "description": f"Compliance Standard {frameworks[i]}",
                "status": "Active"
            }},
            upsert=True
        )

    # --- Patches ---
    print("Seeding Patches...")
    for i in range(5):
        p_id = f"patch-{i}"
        await mongodb.db.patches.update_one(
            {"id": p_id},
            {"$set": {
                "id": p_id,
                "tenantId": tenant_id,
                "name": f"Security Update {100+i}",
                "severity": "Critical",
                "status": "Available",
                "releasedAt": datetime.datetime.utcnow().isoformat()
            }},
            upsert=True
        )

    print("Seeding complete.")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(seed_data())
