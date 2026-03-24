import asyncio
from database import connect_to_mongo, get_database

async def clear_mock_patches():
    """Clear mock patch data from the database"""
    await connect_to_mongo()
    db = get_database()
    
    # Count current patches
    count = await db.patches.count_documents({})
    print(f"Found {count} patches in database")
    
    if count > 0:
        # List them first
        patches = await db.patches.find({}).to_list(100)
        print("\nPatches to be deleted:")
        for p in patches:
            print(f"  - {p.get('cveId', 'N/A')} ({p.get('severity', 'N/A')}, {p.get('status', 'N/A')}) - {len(p.get('affectedAssets', []))} assets")
        
        # Delete all
        result = await db.patches.delete_many({})
        print(f"\n✅ Deleted {result.deleted_count} patches")
        print("The Patch Management dashboard will now show empty states.")
    else:
        print("No patches to delete.")

if __name__ == "__main__":
    asyncio.run(clear_mock_patches())
