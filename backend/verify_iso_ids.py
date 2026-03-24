import asyncio
import sys
import os

# Add parent directory to sys.path to import backend modules
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, get_database, close_mongo_connection

async def verify_ids():
    await connect_to_mongo()
    db = get_database()
    
    # Get all distinct control IDs with status in asset_compliance
    control_ids = await db.asset_compliance.distinct("controlId")
    
    # Filter for ISO 2022 IDs (e.g., A.5.1, A.8.7)
    iso_2022_ids = sorted([i for i in control_ids if i.startswith("A.") and len(i.split('.')) >= 2])
    
    # Legacy ISO IDs (usually A.12.x etc from 2013)
    legacy_iso = sorted([i for i in control_ids if i.startswith("A.") and len(i.split('.')) > 3])
    
    print("\n🔍 Verification Results:")
    print(f"Total Unique Controls with Evidence: {len(control_ids)}")
    print(f"ISO 27001:2022 IDs Found: {len(iso_2022_ids)}")
    for i in iso_2022_ids:
        print(f"  • {i}")
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(verify_ids())
