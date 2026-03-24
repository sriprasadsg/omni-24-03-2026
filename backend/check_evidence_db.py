import asyncio
from database import get_database, connect_to_mongo

async def check_evidence():
    await connect_to_mongo()
    db = get_database()
    count = await db.compliance_evidence.count_documents({})
    print(f"TOTAL_EVIDENCE_COUNT: {count}")

if __name__ == "__main__":
    asyncio.run(check_evidence())
