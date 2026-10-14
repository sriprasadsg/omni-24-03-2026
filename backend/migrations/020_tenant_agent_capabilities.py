"""Migration 020: per-tenant agent capabilities.

Tenants now carry the list of capabilities their agents may use (tenants.agentCapabilities), and
a tenant without a list gets only the always-on ones. Every existing tenant starts with every
capability, so no agent loses one on deploy; the Super Admin then unticks per tenant.
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

import agent_capabilities

DESCRIPTION = "Give every existing tenant every agent capability"


async def up(db: AsyncIOMotorDatabase) -> None:
    await db.tenants.update_many({"agentCapabilities": {"$exists": False}},
                                 {"$set": {"agentCapabilities": agent_capabilities.every_capability()}})
