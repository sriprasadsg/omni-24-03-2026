import sys
import os
import asyncio
sys.path.append(os.path.abspath("backend"))

from backend.database import connect_to_mongo, get_database

async def verify_dpdp_data():
    await connect_to_mongo()
    db = get_database()
    
    print("\n--- Verifying DPDP Compliance Seeding ---\n")
    
    # 1. Check Asset Compliance
    dpdp_controls = await db.asset_compliance.find({"controlId": {"$regex": "^DPDP"}}).to_list(length=100)
    print(f"Found {len(dpdp_controls)} DPDP controls in 'asset_compliance'.")
    for c in dpdp_controls:
        print(f" - {c.get('controlId')}: {c.get('status')} (Tenant: {c.get('tenantId')})")
        
    # 2. Check Agent Meta
    agent = await db.agents.find_one({"id": "agent-EILT0197"})
    if agent:
        meta = agent.get("meta", {}).get("compliance_enforcement", {})
        print(f"\nAgent Meta Framework: {meta.get('framework')}")
        print(f"Total Rules: {meta.get('total_rules')}")
        
    print("\n-----------------------------------------\n")

if __name__ == "__main__":
    asyncio.run(verify_dpdp_data())
