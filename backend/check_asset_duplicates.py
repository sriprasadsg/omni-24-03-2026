"""
Check for duplicate agent references in assets collection
"""

import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection
from collections import defaultdict

async def check_asset_duplicates():
    """Check if assets have duplicate agent references"""
    
    await connect_to_mongo()
    db = get_database()
    
    print("🔍 Checking assets collection for duplicate agent references...")
    
    # Find all assets
    assets = await db.assets.find({}).to_list(length=None)
    print(f"📊 Total assets in database: {len(assets)}")
    
    # Check for duplicate agentId references
    agent_refs = defaultdict(int)
    for asset in assets:
        agent_id = asset.get('agentId')
        if agent_id:
            agent_refs[agent_id] += 1
    
    duplicates = {aid: count for aid, count in agent_refs.items() if count > 1}
    
    if duplicates:
        print(f"\n⚠️  Found agent IDs referenced multiple times in assets:")
        for agent_id, count in duplicates.items():
            print(f"  - {agent_id}: {count} assets")
            # Show which assets
            matching_assets = [a for a in assets if a.get('agentId') == agent_id]
            for asset in matching_assets:
                print(f"    • Asset: {asset.get('name', 'unnamed')} (id: {asset.get('id', 'no-id')})")
    else:
        print("✅ No duplicate agent references in assets!")
    
    await close_mongo_connection()

if __name__ == "__main__":
    print("=" * 60)
    print("🔍 Asset Duplicate Agent Reference Check")
    print("=" * 60)
    asyncio.run(check_asset_duplicates())
