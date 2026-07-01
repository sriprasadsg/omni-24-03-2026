import asyncio
from database import connect_to_mongo, get_database

async def clear_mock_vulnerabilities():
    """Clear mock vulnerability data from the database"""
    await connect_to_mongo()
    db = get_database()
    
    # Count current vulnerabilities
    count = await db.vulnerabilities.count_documents({})
    print(f"Found {count} vulnerabilities in database")
    
    if count > 0:
        # List them first
        vulns = await db.vulnerabilities.find({}).to_list(100)
        print("\nVulnerabilities to be deleted:")
        for v in vulns:
            print(f"  - {v.get('cveId', 'N/A')} ({v.get('severity', 'N/A')}) for {v.get('assetId', 'N/A')}")
        
        # Delete all
        result = await db.vulnerabilities.delete_many({})
        print(f"\n✅ Deleted {result.deleted_count} vulnerabilities")
        print("The Vulnerability Management dashboard will now show empty states.")
    else:
        print("No vulnerabilities to delete.")

if __name__ == "__main__":
    asyncio.run(clear_mock_vulnerabilities())
