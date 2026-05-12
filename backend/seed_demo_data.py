import asyncio
import uuid
import os
from datetime import datetime, timedelta, timezone
from database import connect_to_mongo, close_mongo_connection, get_database
from auth_utils import hash_password

async def seed_demo_data():
    await connect_to_mongo()
    db = get_database()
    print("🌱 Starting Comprehensive Demo Data Seeding...")

    # 1. Tenants
    tenants = [
        {
            "id": "tenant_f15daa22a46a",
            "name": "Acme Corporation",
            "subscriptionTier": "Enterprise",
            "enabledFeatures": ["view:dashboard", "view:agents", "view:compliance", "view:security", "view:finops"],
            "createdAt": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": "tenant_c1344db58834",
            "name": "Exafluence Inc.",
            "subscriptionTier": "Enterprise",
            "enabledFeatures": ["view:dashboard", "view:agents", "view:compliance", "view:security", "view:llmops", "view:swarm"],
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
    ]
    for t in tenants:
        await db.tenants.update_one({"id": t["id"]}, {"$set": t}, upsert=True)
    print("✅ Tenants seeded.")

    # 2. Roles & Users
    admin_permissions = [
        "view:dashboard", "view:agents", "view:assets", "view:security", 
        "view:compliance", "view:finops", "manage:settings", "view:logs"
    ]
    
    users = [
        {
            "id": "user_admin_acme",
            "email": "admin@acme.com",
            "password": hash_password("Password123!"),
            "name": "Acme Admin",
            "role": "admin",
            "tenantId": "tenant_f15daa22a46a",
            "status": "Active",
            "permissions": admin_permissions,
            "createdAt": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": "user_admin_exafluence",
            "email": "admin@exafluence.com",
            "password": hash_password("Password123!"),
            "name": "Exafluence Admin",
            "role": "admin",
            "tenantId": "tenant_c1344db58834",
            "status": "Active",
            "permissions": admin_permissions + ["view:llmops", "view:swarm"],
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
    ]
    for u in users:
        await db.users.update_one({"email": u["email"]}, {"$set": u}, upsert=True)
    print("✅ Users seeded (Login: admin@acme.com / Password123!).")

    # 3. Agents
    agents = [
        {
            "id": "agent-1", "tenantId": "tenant_f15daa22a46a", "hostname": "db-prod-01", "platform": "Linux",
            "status": "Online", "version": "2.1.0", "ipAddress": "10.0.1.10", "lastSeen": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": "agent-2", "tenantId": "tenant_f15daa22a46a", "hostname": "web-server-01", "platform": "Windows",
            "status": "Online", "version": "2.1.0", "ipAddress": "10.0.2.5", "lastSeen": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": "agent-3", "tenantId": "tenant_c1344db58834", "hostname": "ai-worker-01", "platform": "Linux",
            "status": "Online", "version": "2.1.0", "ipAddress": "192.168.1.10", "lastSeen": datetime.now(timezone.utc).isoformat()
        }
    ]
    for a in agents:
        await db.agents.update_one({"id": a["id"]}, {"$set": a}, upsert=True)
    print("✅ Agents seeded.")

    # 4. Security Events
    events = [
        {
            "id": str(uuid.uuid4()), "tenantId": "tenant_f15daa22a46a", "type": "Brute Force", "severity": "High",
            "source": "192.168.1.100", "timestamp": datetime.now(timezone.utc).isoformat(), "status": "Open"
        },
        {
            "id": str(uuid.uuid4()), "tenantId": "tenant_f15daa22a46a", "type": "Malware Detected", "severity": "Critical",
            "source": "db-prod-01", "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(), "status": "Investigating"
        }
    ]
    await db.security_events.insert_many(events)
    print("✅ Security events seeded.")

    # 5. Goals (Innovation Horizon)
    goals = [
        {
            "id": "goal-1", "tenantId": "tenant_f15daa22a46a", "title": "Zero Trust Migration", "progress": 45,
            "status": "Active", "category": "Security", "deadline": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
        },
        {
            "id": "goal-2", "tenantId": "tenant_c1344db58834", "title": "LLM Governance Setup", "progress": 15,
            "status": "Active", "category": "Governance", "deadline": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        }
    ]
    for g in goals:
        await db.goals.update_one({"id": g["id"]}, {"$set": g}, upsert=True)
    print("✅ Goals seeded.")

    # 6. Predictive Health
    health_metrics = [
        {
            "id": "health-1", "tenantId": "tenant_f15daa22a46a", "assetId": "agent-1", "prediction": "High Risk of Failure",
            "probability": 0.85, "estimatedTime": "48h", "reason": "Consistent high memory usage and disk I/O"
        }
    ]
    for h in health_metrics:
        await db.predictive_health.update_one({"id": h["id"]}, {"$set": h}, upsert=True)
    # 7. SIEM Events
    siem_events = [
        {
            "id": "siem-1", "tenantId": "tenant_f15daa22a46a", "source": "Okta", "event_type": "Suspicious Login",
            "severity": "Medium", "timestamp": datetime.now(timezone.utc).isoformat(), "details": "Login from unrecognized IP in Bulgaria"
        },
        {
            "id": "siem-2", "tenantId": "tenant_f15daa22a46a", "source": "Azure Defender", "event_type": "Resource Deletion",
            "severity": "High", "timestamp": datetime.now(timezone.utc).isoformat(), "details": "Production SQL database deletion attempt"
        }
    ]
    await db.siem_events.insert_many(siem_events)
    print("✅ SIEM events seeded.")

    # 8. Risks
    risks = [
        {
            "id": "risk-1", "tenantId": "tenant_f15daa22a46a", "title": "Unpatched CVEs in Core Database",
            "impact": "Critical", "likelihood": "Medium", "status": "Open"
        }
    ]
    for r in risks:
        await db.risks.update_one({"id": r["id"]}, {"$set": r}, upsert=True)
    print("✅ Risks seeded.")

    print("🚀 Seeding Complete!")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_demo_data())
