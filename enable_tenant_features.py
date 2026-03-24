import sys
import os
import asyncio
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from backend.database import connect_to_mongo, get_database

FEATURES_TO_ENABLE = [
    "view:dashboard",
    "view:agents",
    "view:compliance",
    "view:insights", # Predictive Health
    "view:security",
    "view:network",
    "view:assets",
    "manage:settings"
]

async def enable():
    await connect_to_mongo()
    db = get_database()
    
    # Update ALL tenants
    result = await db.tenants.update_many(
        {},
        {"$addToSet": {"enabledFeatures": {"$each": FEATURES_TO_ENABLE}}}
    )
    
    print(f"✅ Updated {result.matched_count} tenants (Modified: {result.modified_count})")
    print(f"Enabled features: {FEATURES_TO_ENABLE}")

if __name__ == "__main__":
    asyncio.run(enable())
