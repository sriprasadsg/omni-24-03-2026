"""
Recalculate billing costs for all tenants with new comprehensive service pricing.
This will update finOpsData for all tenants to use the new integrated billing logic.
"""
import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection
from finops_service import finops_service

async def recalculate_all_tenant_billing():
    """Recalculate billing for all tenants using new comprehensive pricing"""
    print("=" * 80)
    print("RECALCULATING TENANT BILLING WITH COMPREHENSIVE SERVICE PRICING")
    print("=" * 80)
    
    try:
        await connect_to_mongo()
        db = get_database()
        
        if not db:
            print("❌ Failed to connect to database")
            return
        
        print("[OK] Connected to database\n")
        
        # Get all tenants
        tenants = await db.tenants.find({}, {"id": 1, "name": 1}).to_list(length=100)
        total_tenants = len(tenants)
        
        print(f"Found {total_tenants} tenants\n")
        print("-" * 80)
        
        success_count = 0
        error_count = 0
        
        for idx, tenant in enumerate(tenants, 1):
            tenant_id = tenant["id"]
            tenant_name = tenant.get("name", "Unknown")
            
            try:
                print(f"[{idx}/{total_tenants}] Calculating: {tenant_name} ({tenant_id})...")
                
                # Calculate costs using new comprehensive logic
                fin_ops_data = await finops_service.calculate_tenant_costs(tenant_id)
                
                if fin_ops_data:
                    services_count = fin_ops_data.get("servicesCount", 0)
                    current_cost = fin_ops_data.get("currentMonthCost", 0)
                    total_agents = fin_ops_data.get("totalAgents", 0)
                    active_agents = fin_ops_data.get("activeAgents", 0)
                    
                    print(f"  ✅ SUCCESS:")
                    print(f"     Agents: {active_agents}/{total_agents} (active/total)")
                    print(f"     Services charged: {services_count}")
                    print(f"     Current month cost: ${current_cost:.2f}")
                    
                    success_count += 1
                else:
                    print(f"  ⚠️  WARNING: No finOps data returned")
                    error_count += 1
                    
            except Exception as e:
                print(f"  ❌ ERROR: {e}")
                error_count += 1
            
            print()
        
        print("-" * 80)
        print("\n" + "=" * 80)
        print("RECALCULATION COMPLETE")
        print("=" * 80)
        print(f"Total tenants: {total_tenants}")
        print(f"Successfully recalculated: {success_count}")
        print(f"Errors: {error_count}")
        print("=" * 80)
        
        # Show example breakdown from first tenant
        if tenants:
            first_tenant = tenants[0]
            tenant_data = await db.tenants.find_one({"id": first_tenant["id"]})
            if tenant_data and "finOpsData" in tenant_data:
                fin_ops = tenant_data["finOpsData"]
                breakdown = fin_ops.get("costBreakdown", [])
                
                print(f"\n📊 Example Cost Breakdown ({first_tenant.get('name', 'Unknown')}):")
                print("-" * 80)
                for item in breakdown[:10]:  # Show first 10 services
                    print(f"  {item['service']}: ${item['cost']:.2f}")
                if len(breakdown) > 10:
                    print(f"  ... and {len(breakdown) - 10} more services")
                print("-" * 80)
        
        await close_mongo_connection()
        print("\nClosed MongoDB connection")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(recalculate_all_tenant_billing())
