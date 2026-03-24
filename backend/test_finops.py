"""
Simple test script to verify finOps auto-calculation.
Run this to check if the finops_service is working correctly.
"""
import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection

async def test_finops_calculation():
    """Test the finOps calculation for an existing tenant"""
    print("=" * 60)
    print("FinOps Auto-Calculation Test")
    print("=" * 60)
    
    try:
        # Connect to database
        await connect_to_mongo()
        db = get_database()
        
        if not db:
            print("❌ Failed to connect to database")
            return
        
        print("[OK] Connected to database")
        
        # Find a tenant to test with (excluding platform-admin)
        tenant = await db.tenants.find_one({"id": {"$ne": "platform-admin"}})
        
        if not tenant:
            print("❌ No tenants found to test with")
            print("   Create a tenant first (signup) to test finOps calculation")
            return
        
        tenant_id = tenant["id"]
        tenant_name = tenant.get("name", "Unknown")
        
        print(f"[OK] Found tenant: {tenant_name} ({tenant_id})")
        
        # Get agent count
        agent_count = await db.agents.count_documents({"tenantId": tenant_id})
        print(f"  Agents: {agent_count}")
        
        # Run finOps calculation
        print(f"\nCalculating finOps data for tenant {tenant_id}...")
        from finops_service import finops_service
        
        result = await finops_service.calculate_tenant_costs(tenant_id)
        
        if result:
            print("\n[OK] FinOps calculation successful!")
            print(f"  Current Month Cost: ${result.get('currentMonthCost', 0):.2f}")
            print(f"  Forecasted Cost: ${result.get('forecastedCost', 0):.2f}")
            print(f"  Potential Savings: ${result.get('potentialSavings', 0):.2f}")
            print(f"  Cost Breakdown:")
            for item in result.get('costBreakdown', []):
                print(f"    - {item['service']}: ${item['cost']:.2f}")
        else:
            print("❌ FinOps calculation returned None")
        
        # Verify data was stored in database
        updated_tenant = await db.tenants.find_one({"id": tenant_id})
        finops_data = updated_tenant.get("finOpsData")
        
        if finops_data:
            print("\n[OK] FinOps data stored in database")
            print(f"  Last Updated: {finops_data.get('lastUpdated', 'Unknown')}")
        else:
            print("\n❌ FinOps data NOT found in database")
        
        print("\n" + "=" * 60)
        print("Test Complete!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(test_finops_calculation())
