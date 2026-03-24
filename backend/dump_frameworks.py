import asyncio
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database, close_mongo_connection

async def dump_frameworks():
    await connect_to_mongo()
    db = get_database()
    
    frameworks = await db.compliance_frameworks.find({}).to_list(length=None)
    with open('frameworks_dump.txt', 'w', encoding='utf-8') as f:
        f.write(f"Total Frameworks: {len(frameworks)}\n\n")
        
        for fw in frameworks:
            controls = fw.get('controls', [])
            prefix = controls[0]['id'] if controls else 'None'
            f.write(f"Framework: {fw.get('name')} (ID: {fw.get('id')})\n")
            f.write(f"  Total Controls: {len(controls)}\n")
            f.write(f"  Example Control ID: {prefix}\n")
            if controls:
                f.write(f"  First 5 IDs: {[c['id'] for c in controls[:5]]}\n")
            f.write("-" * 40 + "\n")
            
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(dump_frameworks())
