"""Migration 014: audit chain indexes (spec C5).

One chain head per tenant; seq unique per tenant among chained entries (legacy entries
without seq are left as they are and reported as unchained by verification).
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

DESCRIPTION = "Audit chain heads/checkpoints and (tenantId, seq) uniqueness"


async def up(db: AsyncIOMotorDatabase) -> None:
    await db.audit_chain_heads.create_index("tenantId", unique=True, name="tenant_unique")
    await db.audit_chain_checkpoints.create_index("tenantId", unique=True, name="tenant_unique")
    await db.audit_logs.create_index([("tenantId", 1), ("seq", 1)], unique=True, name="tenant_seq_unique",
                                     partialFilterExpression={"seq": {"$exists": True}})
