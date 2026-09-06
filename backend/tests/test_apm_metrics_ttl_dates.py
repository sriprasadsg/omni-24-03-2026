"""Regression tests for DB-F02 (2026-08-25 audit): apm_metrics had no TTL
index and, worse, timestamp was stored as an ISO-8601 string — MongoDB's
TTL monitor only expires BSON Date-typed fields, so even a TTL index added
naively would have silently done nothing. apm_service.py's writers now
store a native datetime, and its time-window queries compare against a
native datetime threshold rather than threshold.isoformat() (comparing a
Date-typed field against a String literal via $gte does not compare
chronologically under BSON's type ordering).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock

from apm_service import APMService


def _mock_db():
    db = MagicMock()
    db.apm_metrics.insert_one = AsyncMock()
    cursor = MagicMock()
    cursor.__aiter__.return_value = iter([])
    db.apm_metrics.aggregate = MagicMock(return_value=cursor)
    return db


@pytest.mark.asyncio
async def test_record_request_stores_native_datetime():
    db = _mock_db()
    svc = APMService(db)
    await svc.record_request("/api/x", "GET", 42.0, 200)
    doc = db.apm_metrics.insert_one.call_args[0][0]
    assert isinstance(doc["timestamp"], datetime)


@pytest.mark.asyncio
async def test_record_database_query_stores_native_datetime():
    db = _mock_db()
    svc = APMService(db)
    await svc.record_database_query("find", "users", 5.0)
    doc = db.apm_metrics.insert_one.call_args[0][0]
    assert isinstance(doc["timestamp"], datetime)


@pytest.mark.asyncio
async def test_record_external_api_call_stores_native_datetime():
    db = _mock_db()
    svc = APMService(db)
    await svc.record_external_api_call("stripe", "/charges", 100.0, True)
    doc = db.apm_metrics.insert_one.call_args[0][0]
    assert isinstance(doc["timestamp"], datetime)


@pytest.mark.asyncio
async def test_record_background_job_stores_native_datetime():
    db = _mock_db()
    svc = APMService(db)
    await svc.record_background_job("cleanup", 10.0, True)
    doc = db.apm_metrics.insert_one.call_args[0][0]
    assert isinstance(doc["timestamp"], datetime)


@pytest.mark.asyncio
async def test_get_endpoint_metrics_queries_with_native_datetime_threshold():
    db = _mock_db()
    svc = APMService(db)
    await svc.get_endpoint_metrics(time_window_minutes=60)
    pipeline = db.apm_metrics.aggregate.call_args[0][0]
    match_stage = pipeline[0]["$match"]
    assert isinstance(match_stage["timestamp"]["$gte"], datetime)


@pytest.mark.asyncio
async def test_get_performance_trend_queries_with_native_datetime_threshold():
    db = _mock_db()
    svc = APMService(db)
    await svc.get_performance_trend("/api/x", hours=24)
    pipeline = db.apm_metrics.aggregate.call_args[0][0]
    match_stage = pipeline[0]["$match"]
    assert isinstance(match_stage["timestamp"]["$gte"], datetime)
