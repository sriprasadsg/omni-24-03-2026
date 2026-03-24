import asyncio
import os
import json
from database import connect_to_mongo, get_database

async def check():
    await connect_to_mongo()
    db = get_database()
    agent = await db.agents.find_one()
    if agent:
        # Convert ObjectId to string for printing
        agent['_id'] = str(agent['_id'])
        print(json.dumps(agent, indent=2))
    else:
        print("No agents found")
    
asyncio.run(check())
