import asyncio
import os
import sys
import json
from datetime import datetime, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from motor.motor_asyncio import AsyncIOMotorClient

async def verify_uebi_data():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    db = client.omni_platform
    
    print("Verifying UEBA Data in MongoDB...")
    
    tenant = await db.tenants.find_one()
    if not tenant:
        print("Error: No tenant found.")
        return
    tenant_id = tenant['id']
    
    scores_count = await db.ueba_risk_scores.count_documents({"tenantId": tenant_id})
    print(f"Risk Scores Count: {scores_count}")
    
    if scores_count > 0:
        top_risky = await db.ueba_risk_scores.find({"tenantId": tenant_id}).sort("score", -1).to_list(1)
        print(f"Top Risky User Score: {top_risky[0].get('score')}")
        print(f"Reasons: {top_risky[0].get('reasons')}")
    else:
        print("Warning: No risk scores calculated yet. Seed script might have run but calculation not triggered.")

    alerts_count = await db.ueba_alerts.count_documents({"tenantId": tenant_id})
    print(f"UEBA Alerts Count: {alerts_count}")

if __name__ == "__main__":
    asyncio.run(verify_uebi_data())
