"""
Check billing dashboard activation status for all tenants.
Shows which tenants have finOpsData and which need population.
"""
import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection

async def check_all_tenants_billing():
    """Check billing data status for all tenants"""
    print("=" * 70)
    print("BILLING DASHBOARD ACTIVATION CHECK")
    print("=" * 70)
    
    try:
        await connect_to_mongo()
        db = get_database()
        
        if not db:
            print("❌ Failed to connect to database")
            return
        
        print("[OK] Connected to database\n")
        
        # Get all tenants (excluding platform-admin)
        tenants = await db.tenants.find(
            {"id": {"$ne": "platform-admin"}},
            {"id": 1, "name": 1, "finOpsData": 1}
        ).to_list(length=1000)
        
        if not tenants:
            print("❌ No tenants found")
            return
        
        print(f"Found {len(tenants)} tenant(s)\n")
        print("-" * 70)
        
        activated_count = 0
        missing_count = 0
        tenants_to_populate = []
        
        for idx, tenant in enumerate(tenants, 1):
            tenant_id = tenant["id"]
            tenant_name = tenant.get("name", "Unknown")
            finops_data = tenant.get("finOpsData")
            
            # Get agent count for this tenant
            agent_count = await db.agents.count_documents({"tenantId": tenant_id})
            
            if finops_data:
                activated_count += 1
                last_updated = finops_data.get("lastUpdated", "Unknown")
                current_cost = finops_data.get("currentMonthCost", 0)
                
                print(f"{idx}. ✅ {tenant_name}")
                print(f"   ID: {tenant_id}")
                print(f"   Agents: {agent_count}")
                print(f"   Current Cost: ${current_cost:.2f}")
                print(f"   Last Updated: {last_updated}")
                print(f"   Status: ACTIVATED ✅")
            else:
                missing_count += 1
                tenants_to_populate.append({"id": tenant_id, "name": tenant_name})
                
                print(f"{idx}. ❌ {tenant_name}")
                print(f"   ID: {tenant_id}")
                print(f"   Agents: {agent_count}")
                print(f"   Status: NOT ACTIVATED ❌")
                print(f"   Issue: Missing finOpsData field")
            
            print("-" * 70)
        
        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Total Tenants: {len(tenants)}")
        print(f"Activated (with billing data): {activated_count} ✅")
        print(f"Not Activated (missing data): {missing_count} ❌")
        print("=" * 70)
        
        # Offer to populate missing tenants
        if tenants_to_populate:
            print("\n⚠️  TENANTS NEEDING BILLING DATA POPULATION:")
            for tenant in tenants_to_populate:
                print(f"   - {tenant['name']} ({tenant['id']})")
            
            print("\n" + "=" * 70)
            print("POPULATING BILLING DATA FOR ALL TENANTS...")
            print("=" * 70)
            
            from finops_service import finops_service
            
            success_count = 0
            error_count = 0
            
            for tenant in tenants_to_populate:
                try:
                    print(f"\nProcessing: {tenant['name']}...")
                    result = await finops_service.calculate_tenant_costs(tenant['id'])
                    
                    if result:
                        success_count += 1
                        print(f"✅ Success - Cost: ${result.get('currentMonthCost', 0):.2f}")
                    else:
                        error_count += 1
                        print(f"❌ Failed - No result returned")
                except Exception as e:
                    error_count += 1
                    print(f"❌ Error: {e}")
            
            print("\n" + "=" * 70)
            print("POPULATION RESULTS")
            print("=" * 70)
            print(f"Successfully populated: {success_count}")
            print(f"Failed: {error_count}")
            print("=" * 70)
        else:
            print("\n✅ All tenants have billing data activated!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check_all_tenants_billing())
