import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
import random

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from motor.motor_asyncio import AsyncIOMotorClient

async def seed_telemetry():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    db = client.omni_platform
    
    print("Seeding dummy telemetry data for UEBA...")
    
    # Get primary tenant and test users
    tenant = await db.tenants.find_one({"id": "platform-admin"})
    if not tenant:
        print("Tenant 'platform-admin' not found.")
        return
    tenant_id = tenant['id']
    
    users = await db.users.find().to_list(None)
    if len(users) < 5:
        print("Need at least 5 users for Isolation Forest. Found", len(users))
        
        # Create dummy users if we don't have enough
        for i in range(5 - len(users)):
            new_user = {
                "id": f"dummy_user_{i}",
                "email": f"dummy{i}@example.com",
                "name": f"Dummy User {i}",
                "role": "user",
                "tenantId": tenant_id,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.users.insert_one(new_user)
            users.append(new_user)
            
    # Clear old telemetry
    await db.audit_logs.delete_many({"action": {"$in": ["user.login", "file.download"]}})
    await db.itdr_alerts.delete_many({})
    
    # Generate Normal Logs for everyone
    logs = []
    now = datetime.now(timezone.utc)
    
    for u in users:
        u_id = u.get('id') or str(u.get('_id'))
        # 1-3 logins from standard IPs
        for _ in range(random.randint(1, 3)):
            logs.append({
                "tenantId": tenant_id,
                "userId": u_id,
                "action": "user.login",
                "status": "success",
                "details": {"ipAddress": "192.168.1.100"},
                "timestamp": (now - timedelta(hours=random.randint(1, 23))).isoformat()
            })
            
        # Small file downloads
        for _ in range(random.randint(0, 5)):
             logs.append({
                "tenantId": tenant_id,
                "userId": u_id,
                "action": "file.download",
                "details": {"fileSize": random.randint(1024, 1024 * 1024 * 5)}, # Up to 5MB
                "timestamp": (now - timedelta(hours=random.randint(1, 23))).isoformat()
            })
             
    # Make the FIRST user the "Riskiest User" (Anomaly)
    risky_user = users[0]
    risky_u_id = risky_user.get('id') or str(risky_user.get('_id'))
    
    # Anomaly 1: Lots of failed logins
    for _ in range(15):
        logs.append({
            "tenantId": tenant_id,
            "userId": risky_u_id,
            "action": "user.login",
            "status": "failure",
            "details": {"ipAddress": f"10.0.0.{random.randint(1,255)}"},
            "timestamp": (now - timedelta(minutes=random.randint(1, 60))).isoformat()
        })
        
    # Anomaly 2: Massive Download
    logs.append({
        "tenantId": tenant_id,
        "userId": risky_u_id,
        "action": "file.download",
        "details": {"fileSize": 8 * 1024 * 1024 * 1024}, # 8 GB
        "timestamp": (now - timedelta(minutes=15)).isoformat()
    })
    
    # Anomaly 3: ITDR Alerts
    for i in range(2):
        await db.itdr_alerts.insert_one({
            "tenantId": tenant_id,
            "user_id": risky_u_id,
            "rule_name": f"Suspicious Activity {i}",
            "severity": "High",
            "timestamp": (now - timedelta(minutes=random.randint(1, 30))).isoformat()
        })
        
    # Insert Audit Logs
    await db.audit_logs.insert_many(logs)
    print("Telemetry seeded successfully.")
    print("Risky User ID:", risky_u_id)

if __name__ == "__main__":
    asyncio.run(seed_telemetry())
