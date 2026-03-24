import asyncio
import os
import sys

# Ensure backend directory is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, close_mongo_connection, get_database
from tenant_context import set_tenant_id

async def verify():
    print("Connecting to DB...")
    await connect_to_mongo()
    db = get_database()
    
    # Test Tenant ID (one that was seeded in the previous step)
    # Using one from the output: tenant_2a1354e1e71d
    test_tenant = "tenant_2a1354e1e71d"
    
    print(f"\n--- 1. Testing Framework Visibility (Tenant: {test_tenant}) ---")
    set_tenant_id(test_tenant)
    print(f"Context set to: {test_tenant}")
    
    # This should return frameworks despite tenant isolation because of the exemption we added
    try:
        frameworks = await db.compliance_frameworks.find({}).to_list(length=100)
        print(f"Frameworks found: {len(frameworks)}")
        if len(frameworks) > 0:
            print("✅ SUCCESS: compliance_frameworks are visible to tenant!")
        else:
            print("❌ FAILURE: compliance_frameworks are filtered out (0 found).")
    except Exception as e:
        print(f"❌ ERROR querying frameworks: {e}")

    print(f"\n--- 2. Testing Evidence Visibility (Tenant: {test_tenant}) ---")
    # This should return the evidence we seeded
    try:
        evidence = await db.asset_compliance.find({}).to_list(length=100)
        print(f"Evidence records found: {len(evidence)}")
        if len(evidence) > 0:
            print("✅ SUCCESS: asset_compliance records are visible!")
            print(f"Sample: {evidence[0].get('assetId')} - {evidence[0].get('status')}")
        else:
            print("❌ FAILURE: No evidence records found.")
    except Exception as e:
        print(f"❌ ERROR querying evidence: {e}")
    
    await close_mongo_connection()

if __name__ == "__main__":
    try:
        # Load env vars if needed, though database.py does it too
        from dotenv import load_dotenv
        load_dotenv("backend/.env")
        asyncio.run(verify())
    except KeyboardInterrupt:
        pass
