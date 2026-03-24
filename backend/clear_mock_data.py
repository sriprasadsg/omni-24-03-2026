import asyncio
import os
from database import connect_to_mongo, get_database, close_mongo_connection

async def clear_mock_data():
    print("Initializing core database connection...")
    await connect_to_mongo()
    
    # get_database() returns the raw motor client for operations
    db = get_database()
    
    # Define collections to purge (mock telemetry & generated data)
    collections_to_purge = [
        "telemetry",
        "vulnerabilities", 
        "ueba_events",
        "network_connections",
        "network_devices",
        "assets",
        "alerts",
        "metrics",
        "logs",
        "security_events",
        "audit_logs"
    ]
    
    print("\n--- Purging All Registered Agents and Assets ---")
    mock_agent_result = await db.agents.delete_many({})
    print(f"Deleted {mock_agent_result.deleted_count} strictly mock agents by prefix.")
    
    seeded_agent_result = await db.assets.delete_many({})
    print(f"Deleted {seeded_agent_result.deleted_count} associated assets.")

    print("\n--- Purging Generated Collections ---")
    for coll in collections_to_purge:
        try:
            result = await db[coll].delete_many({})
            print(f"Emptied collection '{coll}': Removed {result.deleted_count} mock records.")
        except Exception as e:
            print(f"Failed to clear {coll}: {e}")
            
    print("\nData purge complete! Core tenants and users were retained.")
    
if __name__ == "__main__":
    asyncio.run(clear_mock_data())
