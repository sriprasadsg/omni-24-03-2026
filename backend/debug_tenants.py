import asyncio
import json
from database import connect_to_mongo, mongodb

async def list_tenants():
    try:
        await connect_to_mongo()
        if mongodb.db is None:
            print("Failed to connect to DB")
            return

        cursor = mongodb.db.tenants.find()
        tenants = await cursor.to_list(length=None)
        
        output = []
        for t in tenants:
            output.append({
                'name': t.get('name'),
                'id': t.get('id')
            })
            
        with open('tenants.json', 'w') as f:
            json.dump(output, f, indent=2)
            
        print("Done writing tenants.json")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(list_tenants())
