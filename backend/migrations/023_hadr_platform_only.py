"""Migration 023: HA/DR & Backups is a platform screen, not a tenant one.

Its routes back up and restore the platform database and always required view:backups /
manage:backups, which only the Super Admin holds, so a tenant with the screen switched on saw a
page that failed. The sidebar entry now needs view:backups and the switch is gone from Manage
Tenant; this drops the dead "screen:hadr" entry from every tenant's list.
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Remove the HA/DR screen switch from every tenant"


async def up(db: AsyncIOMotorDatabase) -> None:
    await db.tenants.update_many({"enabledFeatures": "screen:hadr"},
                                 {"$pull": {"enabledFeatures": "screen:hadr"}})
