import asyncio
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database

async def check():
    await connect_to_mongo()
    db = get_database()
    vulns = await db.vulnerabilities.find().to_list(length=10)
    print(f"Found {len(vulns)} vulnerabilities")
    for v in vulns:
        print(v)

if __name__ == "__main__":
    asyncio.run(check())
