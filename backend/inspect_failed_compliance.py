
import asyncio
from database import get_database, connect_to_mongo

async def main():
    await connect_to_mongo()
    db = get_database()
    
    # Find a failed compliance record
    failed_record = await db.asset_compliance.find_one({"status": "Non-Compliant"})
    
    if failed_record:
        print("Found failed record:")
        print(f"Control ID: {failed_record.get('controlId')}")
        print(f"Title: {failed_record.get('title')}") # Checking if title exists directly
        print(f"Evidence: {failed_record.get('evidence')}")
        print(f"Keys: {list(failed_record.keys())}")
    else:
        print("No failed records found.")

if __name__ == "__main__":
    asyncio.run(main())
