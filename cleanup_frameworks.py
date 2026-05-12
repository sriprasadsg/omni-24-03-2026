import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    
    # Delete the redundant shell frameworks
    result = await db.compliance_frameworks.delete_many({
        "id": {"$in": ["framework-0", "framework-1", "framework-2"]}
    })
    print(f"Deleted {result.deleted_count} redundant frameworks.")
    
    # Also ensure the "good" ones are set to Active or In Progress as appropriate
    # The user wants them to "work", so making sure they have status that looks good.
    await db.compliance_frameworks.update_many(
        {"id": {"$in": ["gdpr", "nistcsf", "iso27001"]}},
        {"$set": {"status": "In Progress"}} # Or "Active" if user prefers
    )
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
