import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__)))
from admin_evidence_service import run_evidence_collection_for_asset

async def run_direct_evidence():
    print("Initiating direct evidence collection...")
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.omni_platform

    import socket
    hostname = socket.gethostname()

    print(f"Running evidence collection for host: {hostname}")
    await run_evidence_collection_for_asset(hostname, db)
    
    evidence_count = await db.compliance_evidence.count_documents({})
    asset_comp_count = await db.asset_compliance.count_documents({})
    
    print(f"New compliance_evidence records: {evidence_count}")
    print(f"New asset_compliance records: {asset_comp_count}")
    
    if evidence_count > 0 and asset_comp_count > 0:
        print("SUCCESS! Evidence was successfully recollected and processed.")
    else:
        print("FAILED! No evidence found in DB.")

if __name__ == "__main__":
    asyncio.run(run_direct_evidence())
