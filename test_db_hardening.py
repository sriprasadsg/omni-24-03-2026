import asyncio
import os
import sys

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from database import connect_to_mongo, get_database, close_mongo_connection
from tenant_context import set_tenant_id

async def verify_hardening():
    await connect_to_mongo()
    db = get_database()
    
    print("\n--- TEST 1: UNAUTHORIZED ACCESS (Fail-Closed) ---")
    set_tenant_id(None)
    agents = await db.agents.find({}).to_list(length=100)
    print(f"Results with No Tenant Context: {len(agents)}")
    if len(agents) == 0:
        print("SUCCESS: Data leakage prevented.")
    else:
        print("FAILURE: Data leakage detected!")

    print("\n--- TEST 2: AUTHORIZED TENANT ACCESS ---")
    # Using a known tenant ID from previous steps
    test_tenant = "tenant_2af80af8f8bc"
    set_tenant_id(test_tenant)
    agents = await db.agents.find({}).to_list(length=100)
    print(f"Results for Tenant {test_tenant}: {len(agents)}")
    all_correct = all(a.get("tenantId") == test_tenant for a in agents)
    if all_correct and len(agents) > 0:
        print("SUCCESS: Data correctly isolated to tenant.")
    else:
        print(f"FAILURE: Data isolation failed or no data found (Count: {len(agents)}).")

    print("\n--- TEST 3: SUPER ADMIN ACCESS ---")
    set_tenant_id("platform-admin")
    agents = await db.agents.find({}).to_list(length=100)
    tenants = set(a.get("tenantId") for a in agents)
    print(f"Results for Super Admin: {len(agents)}")
    print(f"Unique Tenants seen: {tenants}")
    if len(tenants) > 1:
        print("SUCCESS: Super Admin can see cross-tenant data.")
    else:
        print("NOTE: Super Admin only saw one tenant, might be due to lack of diverse test data.")

    print("\n--- TEST 4: AGGREGATION ISOLATION ---")
    set_tenant_id(test_tenant)
    pipeline = [{"$count": "total"}]
    result = await db.agents.aggregate(pipeline).to_list(length=1)
    print(f"Aggregation count for tenant: {result}")
    
    set_tenant_id(None)
    result_fail = await db.agents.aggregate(pipeline).to_list(length=1)
    print(f"Aggregation count with no context: {result_fail}")
    if not result_fail:
        print("SUCCESS: Aggregation isolation verified.")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(verify_hardening())
