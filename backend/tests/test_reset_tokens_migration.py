"""Migration 030: open reset and invite links keep working, but the database stops holding their tokens.

Value: protects=a reader of ``password_reset_tokens`` gets no working link after the upgrade;
fails_when=a row keeps its raw ``token``, an already hashed row changes, a second run alters
anything, or an upgraded link no longer matches the lookup the routes use.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reset_tokens import by_token, token_hash
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

migration = importlib.import_module("migrations.030_hash_reset_tokens")

pytestmark = pytest.mark.asyncio


async def _seed(db):
    await db.password_reset_tokens.insert_many([
        {"token": "reset-secret", "email": "a@x.test", "expires_at": "2026-11-05T00:00:00+00:00"},
        {"token": "invite-secret", "email": "b@x.test", "expires_at": "2026-11-11T00:00:00+00:00", "invite": True},
        {"tokenHash": token_hash("already"), "email": "c@x.test", "expires_at": "2026-11-11T00:00:00+00:00"},
    ])


async def test_up_replaces_every_raw_token_with_its_hash(mongo_db):
    await _seed(mongo_db)
    await migration.up(mongo_db)
    rows = await mongo_db.password_reset_tokens.find({}, {"_id": 0}).sort("email", 1).to_list(None)
    assert all("token" not in row for row in rows)
    assert [row["tokenHash"] for row in rows] == [token_hash("reset-secret"), token_hash("invite-secret"),
                                                  token_hash("already")]
    assert rows[1]["invite"] is True and rows[0]["expires_at"] == "2026-11-05T00:00:00+00:00"
    for secret in ("reset-secret", "invite-secret", "already"):
        assert await mongo_db.password_reset_tokens.find_one(by_token(secret)) is not None


async def test_up_twice_changes_nothing_more(mongo_db):
    await _seed(mongo_db)
    await migration.up(mongo_db)
    first = await mongo_db.password_reset_tokens.find({}).sort("email", 1).to_list(None)
    await migration.up(mongo_db)
    assert await mongo_db.password_reset_tokens.find({}).sort("email", 1).to_list(None) == first
