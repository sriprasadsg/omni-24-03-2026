import asyncio
import sys
import os
import json

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database, close_mongo_connection

async def dump_all_ids():
    await connect_to_mongo()
    db = get_database()
    
    frameworks = await db.compliance_frameworks.find({}).to_list(length=None)
    
    valid_ids = {}
    for fw in frameworks:
        fw_name = fw.get('id')
        controls = [c.get('id') for c in fw.get('controls', []) if c.get('id')]
        valid_ids[fw_name] = controls
        
    with open('all_valid_ids.json', 'w', encoding='utf-8') as f:
        json.dump(valid_ids, f, indent=2)
            
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(dump_all_ids())
