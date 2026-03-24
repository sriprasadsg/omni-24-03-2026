import sys
import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def debug_frameworks():
    print("Connecting to database...")
    from database import connect_to_mongo, get_database
    await connect_to_mongo()
    db = get_database()
    
    print("\n--- Checking PCI DSS Framework ---")
    # Using regex to find PCI DSS framework since ID might vary
    fw = await db.compliance_frameworks.find_one({"id": {"$regex": "pci-dss"}})
    
    if not fw:
        # Try finding by name
        fw = await db.compliance_frameworks.find_one({"name": "PCI DSS"})
        
    if fw:
        print(f"Framework ID: {fw.get('id')}")
        controls = fw.get('controls', [])
        print(f"Total Controls: {len(controls)}")
        
        # Check a few controls
        target = "1.1.1" 
        found = False
        
        output_data = {"framework_id": fw.get('id'), "controls": []}
        
        for c in controls:
            if target in c.get('id') or "Firewall" in c.get('name'):
                print(f"Found Control: ID='{c.get('id')}', Name='{c.get('name')}'")
                output_data["controls"].append(c)
                found = True
        
        with open("framework_output.json", "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
            
        if not found:
            print("Did not find 1.1.1 or Firewall control in this framework.")
    else:
        print("PCI DSS Framework not found in DB.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(debug_frameworks())
