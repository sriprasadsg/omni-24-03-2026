import sys
import os
import json
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Mock DB for standalone script if needed, but better to connect to real DB
try:
    from database import get_database
    from compliance_endpoints import process_automated_evidence
except ImportError as e:
    print(f"Error importing backend modules: {e}")
    print("Ensure you are running from the project root.")
    sys.exit(1)

async def seed_data():
    print("Connecting to database...")
    from database import connect_to_mongo, close_mongo_connection
    await connect_to_mongo()
    db = get_database()
    
    # Load Report
    report_path = "rust_agent/compliance_report.json"
    if not os.path.exists(report_path):
        print(f"Report not found at {report_path}")
        return

    with open(report_path, "r") as f:
        report = json.load(f)
        
    hostname = report.get("hostname", "desktop-rust-agent")
    print(f"Seeding evidence for host: {hostname}")
    
    # Create Dummy Agent & Asset to ensure they appear in UI
    agent_id = f"agent-{hostname}"
    asset_id = f"asset-{hostname}"
    import datetime
    timestamp = datetime.datetime.utcnow().isoformat()
    
    # 1. Asset
    await db.assets.update_one(
        {"id": asset_id},
        {"$set": {
            "id": asset_id,
            "hostname": hostname,
            "osName": "Windows",
            "osVersion": "10.0.22631", # Simulation
            "status": "Online",
            "lastSeen": timestamp,
            "tenantId": "platform-admin", # Default for super admin
            "agentId": agent_id
        }},
        upsert=True
    )
    print(f"Created/Updated Asset: {asset_id}")

    # 2. Agent
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {
            "id": agent_id,
            "hostname": hostname,
            "status": "Online",
            "version": "1.0.0",
            "platform": "Windows",
            "lastSeen": timestamp,
            "tenantId": "platform-admin",
            "assetId": asset_id
        }},
        upsert=True
    )
    print(f"Created/Updated Agent: {agent_id}")

    # Call the actual backend function
    # This will use the UPDATED MAPPINGS in compliance_endpoints.py
    await process_automated_evidence(hostname, report, db)
    
    print("✅ Seeding complete!")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(seed_data())
