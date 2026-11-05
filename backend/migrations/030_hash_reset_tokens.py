"""Migration 030: reset and invite links stored as a hash only (partner UI QA 2026-11-04).

Rows written before this kept the link's raw ``token``, so anyone able to read
``password_reset_tokens`` held working password-set links. Each such row gets ``tokenHash``
(``reset_tokens.token_hash``, the form the routes now look up) and loses ``token``; an open link keeps
working. Rows that already carry only ``tokenHash`` are left alone, so a second run changes nothing.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from reset_tokens import token_hash

DESCRIPTION = "password_reset_tokens: replace raw link tokens with their SHA-256"

logger = logging.getLogger(__name__)


async def up(db: AsyncIOMotorDatabase) -> None:
    hashed = 0
    async for row in db.password_reset_tokens.find({"token": {"$type": "string"}}, {"token": 1}):
        await db.password_reset_tokens.update_one(
            {"_id": row["_id"]}, {"$set": {"tokenHash": token_hash(row["token"])}, "$unset": {"token": ""}})
        hashed += 1
    await db.password_reset_tokens.create_index([("tokenHash", 1)], name="tokenHash_1",
                                                partialFilterExpression={"tokenHash": {"$type": "string"}})
    logger.info("migration 030: %d stored link token(s) replaced by their hash", hashed)
