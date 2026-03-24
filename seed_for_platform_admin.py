
import asyncio
import os
import sys
import uuid
import random
from datetime import datetime, timezone, timedelta

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from motor.motor_asyncio import AsyncIOMotorClient
import database
from ueba_engine import ueba_engine

async def seed_all():
    print("Connecting to database...")
    await database.connect_to_mongo()
    raw_db = database.mongodb.db # This is the raw motor database
    if not raw_db:
        print("Database connection failed.")
        return
    
    tenant_id = "platform-admin"
    print(f"Targeting Tenant ID: {tenant_id}")
    
    # 1. Ensure tenant exists
    tenant = await raw_db.tenants.find_one({"id": tenant_id})
    if not tenant:
        print(f"Tenant {tenant_id} not found. Creating it.")
        await raw_db.tenants.insert_one({
            "id": tenant_id,
            "name": "Platform Admin",
            "registrationKey": "PLATFORM-ADMIN-KEY",
            "createdAt": datetime.now(timezone.utc).isoformat()
        })
    
    # 2. SEED VULNERABILITIES
    print("Seeding Vulnerabilities...")
    asset_id = "asset-platform-01"
    await raw_db.assets.update_one(
        {"id": asset_id, "tenantId": tenant_id},
        {"$set": {
            "hostname": "win-admin-workspace",
            "os": "Windows 11 Enterprise",
            "ipAddress": "10.10.10.50",
            "status": "Online",
            "lastSeen": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    cve_data = [
        {"cveId": "CVE-2021-44228", "severity": "Critical", "description": "Log4Shell RCE"},
        {"cveId": "CVE-2023-38831", "severity": "Critical", "description": "WinRAR RCE"},
        {"cveId": "CVE-2024-21412", "severity": "High", "description": "Shortcut Bypass"},
    ]
    
    await raw_db.vulnerabilities.delete_many({"tenantId": tenant_id})
    vulns = []
    for cve in cve_data:
        vulns.append({
            "id": f"vuln-{str(uuid.uuid4())[:8]}",
            "tenantId": tenant_id,
            "cveId": cve["cveId"],
            "severity": cve["severity"],
            "status": "Open",
            "description": cve["description"],
            "affectedSoftware": "Various",
            "discoveredAt": datetime.now(timezone.utc).isoformat(),
            "assetId": asset_id,
            "updatedAt": datetime.now(timezone.utc).isoformat()
        })
    await raw_db.vulnerabilities.insert_many(vulns)
    print(f"Seeded {len(vulns)} vulnerabilities.")

    # 3. SEED UEBA TELEMETRY
    print("Seeding UEBA Telemetry...")
    user = await raw_db.users.find_one({"email": "super@omni.ai"})
    if not user:
        print("Super admin user not found. Can't seed UEBA.")
    else:
        user_id = user.get("id") or str(user.get("_id"))
        await raw_db.audit_logs.delete_many({"tenantId": tenant_id})
        
        # High volume downloads for user
        logs = []
        for _ in range(20):
             logs.append({
                "tenantId": tenant_id,
                "userId": user_id,
                "action": "file.download",
                "details": {"fileSize": 1024 * 1024 * 500}, # 500MB each
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        await raw_db.audit_logs.insert_many(logs)
        
        # Trigger calculation
        print(f"Calculating UEBA for user {user_id}...")
        await ueba_engine.calculate_risk_score(tenant_id, user_id)
        print("UEBA Calculation Complete.")

    print("Master Seed Complete.")
    await database.close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_all())
