"""
Seed all compliance frameworks into the database.
Data lives in seed_compliance_controls_*.py and seed_compliance_frameworks_*.py.
"""

import asyncio
from database import connect_to_mongo, close_mongo_connection, get_database
from seed_compliance_frameworks_a import FRAMEWORKS_PART1
from seed_compliance_frameworks_b import FRAMEWORKS_PART2


async def seed_compliance():
    await connect_to_mongo()
    db = get_database()
    print("Seeding comprehensive compliance frameworks...")

    frameworks = FRAMEWORKS_PART1 + FRAMEWORKS_PART2

    # Normalise: all controls must be Implemented
    for fw in frameworks:
        for c in fw["controls"]:
            c["status"] = "Implemented"

    canonical_ids = {fw["id"] for fw in frameworks}

    # Remove any stale documents whose id is not in the canonical set
    stale = await db.compliance_frameworks.find(
        {"id": {"$nin": list(canonical_ids)}}, {"id": 1}
    ).to_list(length=200)
    if stale:
        stale_ids = [d["id"] for d in stale]
        await db.compliance_frameworks.delete_many({"id": {"$in": stale_ids}})
        print(f"  Removed {len(stale_ids)} stale entries: {stale_ids}")

    for fw in frameworks:
        await db.compliance_frameworks.update_one(
            {"id": fw["id"]},
            {"$set": fw},
            upsert=True,
        )
        print(f"  OK  {fw['name']}  ({len(fw['controls'])} controls)")

    print("\nDone. All compliance frameworks seeded.")
    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(seed_compliance())
