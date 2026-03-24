import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def clear_existing_evidence():
    print("Connecting to MongoDB...")
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.omni_platform

    print("Clearing compliance_evidence collection...")
    res1 = await db.compliance_evidence.delete_many({})
    print(f"Deleted {res1.deleted_count} documents from compliance_evidence.")

    print("Clearing asset_compliance collection...")
    res2 = await db.asset_compliance.delete_many({})
    print(f"Deleted {res2.deleted_count} documents from asset_compliance.")

    print("Done clearing evidence.")

if __name__ == "__main__":
    asyncio.run(clear_existing_evidence())
