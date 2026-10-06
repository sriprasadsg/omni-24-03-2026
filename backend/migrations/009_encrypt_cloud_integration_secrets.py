"""
Migration 009: encrypt cloud integration secrets stored in plaintext.

cloud_integrations_endpoints only sealed secret fields (client secrets,
service-account JSON, cloud API keys) when INTEGRATION_ENCRYPTION_KEY happened
to be set, and platform_secrets did not provision that key, so deployments
stored them in clear text. The key is now provisioned like the other platform
keys; this seals the secret fields of every existing document the same way
(idempotent: values already carrying the "enc:" prefix are left alone).
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

MIGRATION_ID = "009_encrypt_cloud_integration_secrets"
DESCRIPTION = "Encrypt plaintext secret fields in cloud_integrations"


async def up(db: AsyncIOMotorDatabase) -> None:
    from cloud_integrations_endpoints import _encrypt_secrets, _get_cipher

    if _get_cipher() is None:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY is unavailable; cannot seal cloud integration secrets")

    sealed = 0
    async for doc in db.cloud_integrations.find({}, {"_id": 1, "config": 1}):
        config = doc.get("config") or {}
        new_config = _encrypt_secrets(config)
        if new_config != config:
            await db.cloud_integrations.update_one({"_id": doc["_id"]}, {"$set": {"config": new_config}})
            sealed += 1
    logger.info("[Migration 009] Sealed secrets in %d cloud integrations.", sealed)
