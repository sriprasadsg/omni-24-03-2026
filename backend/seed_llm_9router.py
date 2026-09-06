#!/usr/bin/env python3
"""Seed system_settings with 9router LLM config so backend boots with real provider."""

import asyncio
import sys
sys.path.insert(0, "/home/user/enterprise-omni-agent-ai-platform/backend")

from database import connect_to_mongo, get_database
from ai_service import ai_service


async def seed():
    await connect_to_mongo()
    db = get_database()
    raw = db._db if hasattr(db, "_db") else db

    settings = {
        "type": "llm",
        "provider": "OpenAI-Compatible",  # matches ai_service.initialize() branch
        "baseUrl": "http://192.168.10.70:20128/v1",
        "routerUrl": "http://192.168.10.70:20128/v1",
        "apiKey": "sk-e59d41ed97fcd8fc-40oke4-84bbac3d",
        "model": "cc/claude-haiku-4-5-20251001",  # verified working
    }

    # Global doc (no tenantId field)
    await raw.system_settings.update_one(
        {"type": "llm", "tenantId": {"$exists": False}},
        {"$set": settings},
        upsert=True,
    )
    print("Upserted global 9router LLM settings")

    # Invalidate cache so next request re-initializes from DB
    ai_service.invalidate_tenant_provider(None)
    ai_service.is_configured = False
    print("Invalidated provider cache")

    # Quick verify
    doc = await raw.system_settings.find_one({"type": "llm", "tenantId": {"$exists": False}}, {"_id": 0})
    if doc:
        print(f"Verified: provider={doc.get('provider')}, baseUrl={doc.get('baseUrl')}, model={doc.get('model')}")
    else:
        print("ERROR: doc not found after upsert")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(seed())