"""Create indexes for core collections to enforce uniqueness and speed queries."""
VERSION = "001"
DESCRIPTION = "Create core collection indexes"


async def up(db) -> None:
    # Users: unique email across tenants is NOT enforced (same email can exist in different tenants)
    # But email + tenantId must be unique
    await db.users.create_index([("email", 1), ("tenantId", 1)], unique=True, background=True)
    await db.users.create_index([("id", 1)], unique=True, background=True)

    # Agents: id unique, heartbeat queries filter by tenantId + status
    await db.agents.create_index([("id", 1)], unique=True, background=True)
    await db.agents.create_index([("tenantId", 1), ("status", 1)], background=True)

    # Assets: id unique
    await db.assets.create_index([("id", 1)], unique=True, background=True)
    await db.assets.create_index([("tenantId", 1)], background=True)

    # Revoked tokens: JTI lookup
    await db.revoked_tokens.create_index([("jti", 1)], unique=True, background=True)
    await db.revoked_tokens.create_index([("expiresAt", 1)], expireAfterSeconds=0, background=True)

    # Compliance evidence
    await db.compliance_evidence.create_index([("tenantId", 1), ("controlId", 1)], background=True)


async def down(db) -> None:
    # Drop indexes (leave collections intact)
    for col in ["users", "agents", "assets", "revoked_tokens", "compliance_evidence"]:
        await db[col].drop_indexes()
