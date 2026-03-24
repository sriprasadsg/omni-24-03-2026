import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

import asyncio
from database import connect_to_mongo, get_database
import datetime

async def seed_finops():
    await connect_to_mongo()
    db = get_database()
    
    # Fetch all tenants
    tenants = await db.tenants.find({}).to_list(length=None)
    
    from backend.finops_service import finops_service
    
    print(f"[INFO] Recalculating FinOps data for {len(tenants)} tenants...")
    
    for tenant in tenants:
        tid = tenant.get('id')
        print(f"   Processing tenant: {tenant.get('name')} ({tid})")
        
        try:
            updated_data = await finops_service.calculate_tenant_costs(tid)
            if updated_data:
                 print(f"   [OK] Successfully recalculated for {tid}")
            else:
                 print(f"   [ERR] Failed to recalculate for {tid} (Returned None)")
        except Exception as e:
            import traceback
            print(f"   [EXC] Exception for {tid}: {e}")
            traceback.print_exc()

    print("[DONE] Finished.")

if __name__ == "__main__":
    asyncio.run(seed_finops())
