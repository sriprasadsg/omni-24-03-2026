"""
Migration 010: encrypt SIEM/ticketing/chat integration secrets stored in plaintext.

integration_configs (SIEM, ticketing, EDR, ChatOps) and integrations (the
integrations catalog: Jira, ServiceNow, Slack, PagerDuty, ...) kept API
tokens, passwords and webhook URLs in clear text. They are now sealed on save
with INTEGRATION_ENCRYPTION_KEY (integration_service.seal_config), the same
way migration 009 sealed cloud integrations; this seals every existing
document (idempotent: values already carrying the "enc:" prefix are left alone).
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

MIGRATION_ID = "010_encrypt_integration_config_secrets"
DESCRIPTION = "Encrypt plaintext secret fields in integration_configs and integrations"


async def up(db: AsyncIOMotorDatabase) -> None:
    from cloud_integrations_endpoints import _get_cipher
    from integration_service import seal_config

    if _get_cipher() is None:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY is unavailable; cannot seal integration secrets")

    for name in ("integration_configs", "integrations"):
        sealed = 0
        async for doc in db[name].find({}):
            new_doc = seal_config(doc)
            if new_doc != doc:
                changes = {k: v for k, v in new_doc.items() if v != doc.get(k)}
                await db[name].update_one({"_id": doc["_id"]}, {"$set": changes})
                sealed += 1
        logger.info("[Migration 010] Sealed secrets in %d %s documents.", sealed, name)
