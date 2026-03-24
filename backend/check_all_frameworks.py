import asyncio
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database, close_mongo_connection

async def check_frameworks():
    await connect_to_mongo()
    db = get_database()
    
    frameworks = await db.compliance_frameworks.find({}).to_list(length=None)
    print(f"Total Frameworks: {len(frameworks)}\n")
    
    for f in frameworks:
        controls = f.get('controls', [])
        prefix = controls[0]['id'] if controls else 'None'
        print(f"Framework: {f.get('name')} (ID: {f.get('id')})")
        print(f"  Total Controls: {len(controls)}")
        print(f"  Example Control ID: {prefix}")
        if controls:
            print(f"  First 5 IDs: {[c['id'] for c in controls[:5]]}")
        print("-" * 40)
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check_frameworks())
