import asyncio
from unittest.mock import MagicMock, AsyncMock
from backend.retention_service import RetentionService
from datetime import datetime, timedelta, timezone

# Mock DB Wrapper to test logic without touching real DB if preferred, 
# OR we can use Real DB connection if we want integration test.
# Let's use Real DB connection for "System Verification" style.
from backend.database import connect_to_mongo, get_database

async def verify_retention():
    print("Verifying Data Retention Policy...")
    await connect_to_mongo()
    db = get_database()
    service = RetentionService(db)
    
    # 1. Seed Old Data (100 days old)
    old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    new_date = datetime.now(timezone.utc).isoformat()
    
    # Audit Logs
    await db.audit_logs.insert_many([
        {"action": "TEST_OLD_LOG", "timestamp": old_date},
        {"action": "TEST_NEW_LOG", "timestamp": new_date}
    ])
    
    # Metrics
    await db.metrics.insert_many([
        {"metric": "TEST_OLD_METRIC", "timestamp": old_date},
        {"metric": "TEST_NEW_METRIC", "timestamp": new_date}
    ])
    
    print("✅ Seeded Test Data (Old vs New)")
    
    # 2. Run Cleanup
    print("Running Cleanup...")
    report = await service.run_cleanup()
    print(f"Cleanup Report: {report}")
    
    # 3. Verify
    old_logs = await db.audit_logs.count_documents({"action": "TEST_OLD_LOG"})
    new_logs = await db.audit_logs.count_documents({"action": "TEST_NEW_LOG"})
    
    old_metrics = await db.metrics.count_documents({"metric": "TEST_OLD_METRIC"})
    new_metrics = await db.metrics.count_documents({"metric": "TEST_NEW_METRIC"})
    
    success = True
    if old_logs == 0 and new_logs >= 1:
        print("✅ Audit Logs Cleanup Verified")
    else:
        print(f"❌ Audit Logs Cleanup Failed (Old: {old_logs}, New: {new_logs})")
        success = False
        
    if old_metrics == 0 and new_metrics >= 1:
        print("✅ Metrics Cleanup Verified")
    else:
        print(f"❌ Metrics Cleanup Failed (Old: {old_metrics}, New: {new_metrics})")
        success = False

    # Cleanup Test Data
    await db.audit_logs.delete_many({"action": {"$in": ["TEST_OLD_LOG", "TEST_NEW_LOG"]}})
    await db.metrics.delete_many({"metric": {"$in": ["TEST_OLD_METRIC", "TEST_NEW_METRIC"]}})
    
    if success:
        print("🚀 Data Retention Verification PASSED")
    else:
        print("⚠️ Data Retention Verification FAILED")

if __name__ == "__main__":
    asyncio.run(verify_retention())
