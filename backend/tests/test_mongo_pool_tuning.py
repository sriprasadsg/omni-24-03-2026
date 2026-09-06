"""Regression tests for DB-F15 (2026-08-25 audit): the Mongo connection pool
had no explicit tuning — maxPoolSize/minPoolSize silently used pymongo's
defaults, and waitQueueTimeoutMS/connectTimeoutMS were unset (None = wait
indefinitely for a free pooled connection). connect_to_mongo() now passes
explicit, env-configurable values for all four.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, patch

import database


@pytest.mark.asyncio
async def test_connect_passes_default_pool_tuning_params(monkeypatch):
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017")
    for var in (
        "MONGODB_MAX_POOL_SIZE", "MONGODB_MIN_POOL_SIZE",
        "MONGODB_WAIT_QUEUE_TIMEOUT_MS", "MONGODB_CONNECT_TIMEOUT_MS",
    ):
        monkeypatch.delenv(var, raising=False)

    with patch("database.AsyncIOMotorClient") as mock_client_cls:
        mock_client_cls.return_value.server_info = AsyncMock(return_value={})
        await database.connect_to_mongo()

    _, kwargs = mock_client_cls.call_args
    assert kwargs["maxPoolSize"] == 100
    assert kwargs["minPoolSize"] == 0
    assert kwargs["waitQueueTimeoutMS"] == 10000
    assert kwargs["connectTimeoutMS"] == 10000
    assert kwargs["serverSelectionTimeoutMS"] == 3000
    # Deliberately unset — see the comment in database.py for why.
    assert "socketTimeoutMS" not in kwargs


@pytest.mark.asyncio
async def test_connect_honors_pool_tuning_env_overrides(monkeypatch):
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGODB_MAX_POOL_SIZE", "250")
    monkeypatch.setenv("MONGODB_MIN_POOL_SIZE", "5")
    monkeypatch.setenv("MONGODB_WAIT_QUEUE_TIMEOUT_MS", "5000")
    monkeypatch.setenv("MONGODB_CONNECT_TIMEOUT_MS", "8000")

    with patch("database.AsyncIOMotorClient") as mock_client_cls:
        mock_client_cls.return_value.server_info = AsyncMock(return_value={})
        await database.connect_to_mongo()

    _, kwargs = mock_client_cls.call_args
    assert kwargs["maxPoolSize"] == 250
    assert kwargs["minPoolSize"] == 5
    assert kwargs["waitQueueTimeoutMS"] == 5000
    assert kwargs["connectTimeoutMS"] == 8000
