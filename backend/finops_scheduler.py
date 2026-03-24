"""
Background scheduler for periodic tasks.
Includes FinOps cost recalculation for all tenants.
"""
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime

scheduler = None

async def recalculate_all_finops_costs():
    """
    Background task to recalculate finOps costs for all tenants.
    Runs hourly to keep billing data up-to-date.
    """
    try:
        from database import get_database
        from finops_service import finops_service
        
        db = get_database()
        if not db:
            print("[Scheduler] Database not available, skipping finOps recalculation")
            return
        
        # Get all tenants (exclude platform-admin)
        tenants = await db.tenants.find(
            {"id": {"$ne": "platform-admin"}},
            {"id": 1, "name": 1}
        ).to_list(length=1000)
        
        print(f"[Scheduler] Starting finOps recalculation for {len(tenants)} tenants...")
        
        success_count = 0
        error_count = 0
        
        for tenant in tenants:
            try:
                await finops_service.calculate_tenant_costs(tenant["id"])
                success_count += 1
                print(f"[Scheduler] [OK] Updated finOps for tenant: {tenant.get('name', tenant['id'])}")
            except Exception as e:
                error_count += 1
                print(f"[Scheduler] [ERROR] Failed to update finOps for tenant {tenant['id']}: {e}")
        
        print(f"[Scheduler] FinOps recalculation complete: {success_count} success, {error_count} errors")
        
        # Create audit log
        try:
            await db.audit_logs.insert_one({
                "id": f"audit-{datetime.utcnow().timestamp()}",
                "timestamp": datetime.utcnow().isoformat(),
                "action": "finops_recalculation",
                "userName": "System Scheduler",
                "userId": "system",
                "tenantId": "platform-admin",
                "details": f"Recalculated finOps for {success_count}/{len(tenants)} tenants",
                "success": error_count == 0
            })
        except Exception as audit_error:
            print(f"[Scheduler] Failed to create audit log: {audit_error}")
            
    except Exception as e:
        print(f"[Scheduler] Critical error in finOps recalculation task: {e}")
        import traceback
        traceback.print_exc()

def start_scheduler():
    """Initialize and start the background scheduler"""
    global scheduler
    
    if scheduler is not None:
        print("[Scheduler] Already running, skipping start")
        return
    
    print("[Scheduler] Initializing background tasks...")
    
    scheduler = AsyncIOScheduler()
    
    # Schedule finOps recalculation every hour
    scheduler.add_job(
        recalculate_all_finops_costs,
        trigger=IntervalTrigger(hours=1),
        id="finops_recalculation",
        name="FinOps Cost Recalculation",
        replace_existing=True
    )
    
    scheduler.start()
    print("[Scheduler] [OK] Background scheduler started successfully")
    print("[Scheduler]   - FinOps recalculation: Every 1 hour")

def stop_scheduler():
    """Shutdown the background scheduler"""
    global scheduler
    
    if scheduler:
        scheduler.shutdown()
        scheduler = None
        print("[Scheduler] [OK] Background scheduler stopped")
    else:
        print("[Scheduler] No scheduler running")

# Export scheduler instance for debugging
def get_scheduler():
    return scheduler
