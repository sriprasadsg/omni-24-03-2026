"""A throwaway MongoDB database for tests that need real query semantics
($expr, atomic $inc, concurrent updates). Skips when no server is reachable.

MONGO_TEST_URL overrides the default mongodb://127.0.0.1:27017.
"""
import asyncio
import os
import uuid

import pytest
import pytest_asyncio

_URL = os.getenv("MONGO_TEST_URL", "mongodb://127.0.0.1:27017")


async def _let_background_writes_finish(before, timeout=2.0):
    """Wait for tasks the test started and never awaited (the audit-failure alert, a pending-agent
    notification). One still writing during the drop recreates the database on the server, which
    left 14 one-document omni_test_* databases behind (found 2026-11-05)."""
    started = [t for t in asyncio.all_tasks() if t not in before and t is not asyncio.current_task()]
    if started:
        await asyncio.wait(started, timeout=timeout)


@pytest_asyncio.fixture
async def mongo_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(_URL, serverSelectionTimeoutMS=1500)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip(f"MongoDB not reachable at {_URL}")
    name = f"omni_test_{uuid.uuid4().hex[:12]}"
    db = client[name]
    await db.agents.create_index([("tenantId", 1), ("hostname", 1)], unique=True)
    await db.agents.create_index([("id", 1)], unique=True)
    before = asyncio.all_tasks()
    try:
        yield db
    finally:
        await _let_background_writes_finish(before)
        await client.drop_database(name)
        client.close()
