import asyncio
from database import connect_to_mongo, get_database

async def check_patches():
    """Check and list all patches in the database"""
    await connect_to_mongo()
    db = get_database()
    
    patches = await db.patches.find({}).to_list(100)
    
    with open("patch_check_output.txt", "w") as f:
        f.write(f"Found {len(patches)} patches in database:\n\n")
        
        for p in patches:
            f.write(f"CVE ID: {p.get('cveId', 'N/A')}\n")
            f.write(f"Severity: {p.get('severity', 'N/A')}\n")
            f.write(f"Status: {p.get('status', 'N/A')}\n")
            f.write(f"Description: {p.get('description', 'N/A')}\n")
            f.write(f"Affected Assets: {len(p.get('affectedAssets', []))}\n")
            f.write(f"Assets: {p.get('affectedAssets', [])}\n")
            f.write(f"Published Date: {p.get('publishedDate', 'N/A')}\n")
            f.write("-" * 80 + "\n\n")
    
    print(f"Found {len(patches)} patches - written to patch_check_output.txt")
    return len(patches)

if __name__ == "__main__":
    count = asyncio.run(check_patches())
    print(f"Total patches in database: {count}")
