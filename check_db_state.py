import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import get_database, connect_to_mongo, close_mongo_connection

async def check():
    await connect_to_mongo()
    db = get_database()
    if not db:
        print("DATABASE_NOT_FOUND")
        return
    agent = await db["agents"].find_one()
    invoice = await db["invoices"].find_one()
    print(f"AGENT_FOUND: {agent['hostname'] if agent else 'NONE'}")
    print(f"INVOICE_FOUND: {invoice['invoice_number'] if invoice else 'NONE'}")
    await close_mongo_connection()

if __name__ == '__main__':
    asyncio.run(check())
