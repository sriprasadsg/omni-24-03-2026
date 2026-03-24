import asyncio
from database import connect_to_mongo, get_database

async def check():
    await connect_to_mongo()
    db = get_database()
    
    print(f"\n=== SYSTEM PATCHING DEBUG ===")
    agents = await db.agents.find().to_list(None)
    
    if not agents:
        print("❌ No agents found.")
    else:
        for agent in agents:
            meta = agent.get('meta', {})
            cap_status = meta.get("capabilities_status", [])
            
            # Find status
            status_obj = next((c for c in cap_status if c['id'] == 'system_patching'), None)
            if status_obj:
                print(f"Status: {status_obj}")
            else:
                print("Status: Not found in capabilities_status")
                
            # Check data
            patching = meta.get('system_patching')
            if patching:
                import json
                print(f"RAW DATA: {json.dumps(patching, default=str)}")
            else:
                print("Data: MISSING")

if __name__ == "__main__":
    asyncio.run(check())
