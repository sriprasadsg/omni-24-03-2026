"""
Regression test for ARCH-017: ALLOW_MOCK_DB must never be honored outside
development — previously it was honored identically in production, so an
unreachable MongoDB plus a truthy ALLOW_MOCK_DB could make a production
container boot "successfully" against an in-memory database with total
data loss on restart, with no signal beyond one log line.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, patch

import database


@pytest.mark.asyncio
async def test_allow_mock_db_ignored_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_MOCK_DB", "true")
    monkeypatch.setenv("MONGODB_URL", "mongodb://nonexistent-host:27017")

    with patch("database.AsyncIOMotorClient") as mock_client_cls:
        mock_client_cls.return_value.server_info = AsyncMock(
            side_effect=Exception("connection refused")
        )
        with pytest.raises(Exception, match="connection refused"):
            await database.connect_to_mongo()


@pytest.mark.asyncio
async def test_allow_mock_db_still_works_in_development(monkeypatch):
    # mongomock_motor is an optional dependency not installed in every
    # environment (this one included) — patch AsyncMongoMockClient directly
    # so this test exercises the guard logic itself, not the optional lib.
    from unittest.mock import MagicMock

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_MOCK_DB", "true")
    monkeypatch.setenv("MONGODB_URL", "mongodb://nonexistent-host:27017")
    monkeypatch.setattr(database, "AsyncMongoMockClient", MagicMock())

    with patch("database.AsyncIOMotorClient") as mock_client_cls:
        mock_client_cls.return_value.server_info = AsyncMock(
            side_effect=Exception("connection refused")
        )
        await database.connect_to_mongo()

    assert database.is_demo_mode() is True


@pytest.mark.asyncio
async def test_no_allow_mock_db_raises_in_development_too(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("ALLOW_MOCK_DB", raising=False)
    monkeypatch.setenv("MONGODB_URL", "mongodb://nonexistent-host:27017")

    with patch("database.AsyncIOMotorClient") as mock_client_cls:
        mock_client_cls.return_value.server_info = AsyncMock(
            side_effect=Exception("connection refused")
        )
        with pytest.raises(Exception, match="connection refused"):
            await database.connect_to_mongo()
