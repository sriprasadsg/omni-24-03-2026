import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__)))
from admin_evidence_service import collect_evidence_for_host, run_evidence_collection_for_asset

async def debug_evidence():
    import socket
    hostname = socket.gethostname()
    print(f"Testing direct Sync collection for {hostname}...")
    
    # 1. Test synchronous collection
    try:
        checks = collect_evidence_for_host(hostname)
        print(f"Successfully collected {len(checks)} checks synchronously.")
        if len(checks) > 0:
            print(f"First check: {checks[0]}")
    except Exception as e:
        print(f"Failed sync collection: {e}")
        return

    # 2. Test DB persistence
    print("\nTesting Async DB Persistence...")
    try:
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client.omni_platform
        await run_evidence_collection_for_asset(hostname, db)
        
        evidence_count = await db.compliance_evidence.count_documents({})
        asset_comp_count = await db.asset_compliance.count_documents({})
        
        print(f"New compliance_evidence records: {evidence_count}")
        print(f"New asset_compliance records: {asset_comp_count}")
        
    except Exception as e:
        print(f"Failed async DB persistence: {e}")

if __name__ == "__main__":
    asyncio.run(debug_evidence())
