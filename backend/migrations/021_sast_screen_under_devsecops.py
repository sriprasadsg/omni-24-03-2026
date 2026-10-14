"""Migration 021: SAST is a DevSecOps screen (spec C6).

The SAST sidebar item needed view:security while every SAST API route needs view:devsecops, so a
tenant with Security on and DevSecOps off saw SAST and got 403 on all of it. SAST now needs
view:devsecops and its switch sits under DevSecOps. A tenant with DevSecOps on gets the SAST screen
switched on (it may only have had it through Security); a tenant without DevSecOps loses a screen
whose data it could never load.
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Switch on the SAST screen for every tenant with DevSecOps"


async def up(db: AsyncIOMotorDatabase) -> None:
    await db.tenants.update_many({"enabledFeatures": "view:devsecops"},
                                 {"$addToSet": {"enabledFeatures": "screen:sast"}})
