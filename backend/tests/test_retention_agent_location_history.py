"""
Tests for RetentionService.cleanup_agent_location_history() and its wiring
into run_cleanup() — Phase 46 plan 46-03 (GAUD-01, D-01: 365-day retention
routed through the existing /api/retention/* module).

Hermetic: mongomock is not installed in this environment, so this uses a
small in-memory fake collection whose delete_many() genuinely evaluates the
{"timestamp": {"$lt": cutoff}} filter against native-datetime rows — the
365-day boundary behavior is actually exercised, not merely asserted on the
filter shape (per 46-RESEARCH.md's warning that TTL/expiry claims must be
verified against real row-deletion behavior).

RED at end of Task 1: cleanup_agent_location_history does not exist yet on
RetentionService, so every test below fails with AttributeError until
Task 2 implements it.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import retention_service as retention_service_mod


class _DeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


class _FakeLocationHistoryCollection:
    """Minimal in-memory stand-in for db.agent_location_history supporting
    the one delete_many shape cleanup_agent_location_history needs:
    {"timestamp": {"$lt": cutoff}} evaluated against native datetime rows."""

    def __init__(self, docs):
        self._docs = list(docs)
        self.last_filter = None

    async def delete_many(self, filt):
        self.last_filter = filt
        cutoff = filt["timestamp"]["$lt"]
        assert isinstance(cutoff, datetime), (
            "cutoff must be a real datetime object, not an .isoformat() string"
        )
        before = len(self._docs)
        self._docs = [d for d in self._docs if d["timestamp"] >= cutoff]
        return _DeleteResult(before - len(self._docs))


def _run(coro):
    return asyncio.run(coro)


def _make_db(location_history_docs):
    """Fake db with a real agent_location_history fake collection plus
    no-op AsyncMock stand-ins for the 3 other collections run_cleanup()
    also touches, so run_cleanup() can be exercised end-to-end."""
    db = MagicMock()
    db.agent_location_history = _FakeLocationHistoryCollection(location_history_docs)
    for name in ("audit_logs", "metrics", "notifications"):
        col = MagicMock()
        col.delete_many = AsyncMock(return_value=_DeleteResult(0))
        setattr(db, name, col)
    return db


class TestCleanupAgentLocationHistory:
    def test_366_day_old_row_deleted_1_day_old_row_retained(self):
        now = datetime.now(timezone.utc)
        old_row = {"timestamp": now - timedelta(days=366), "agent_id": "agent-1"}
        recent_row = {"timestamp": now - timedelta(days=1), "agent_id": "agent-2"}
        db = _make_db([old_row, recent_row])
        svc = retention_service_mod.RetentionService(db)

        deleted = _run(svc.cleanup_agent_location_history(retention_days=365))

        assert deleted == 1
        assert db.agent_location_history._docs == [recent_row]

    def test_cutoff_uses_native_datetime_not_isoformat_string(self):
        now = datetime.now(timezone.utc)
        db = _make_db([{"timestamp": now - timedelta(days=400), "agent_id": "agent-1"}])
        svc = retention_service_mod.RetentionService(db)

        _run(svc.cleanup_agent_location_history(retention_days=365))

        cutoff = db.agent_location_history.last_filter["timestamp"]["$lt"]
        assert isinstance(cutoff, datetime)


class TestRunCleanupWiring:
    def test_run_cleanup_report_includes_location_history_deletion_key(self):
        now = datetime.now(timezone.utc)
        old_row = {"timestamp": now - timedelta(days=366), "agent_id": "agent-1"}
        recent_row = {"timestamp": now - timedelta(days=1), "agent_id": "agent-2"}
        db = _make_db([old_row, recent_row])
        svc = retention_service_mod.RetentionService(db)

        report = _run(svc.run_cleanup(policies={"agent_location_history": 365}))

        assert "agent_location_history_deleted" in report
        assert report["agent_location_history_deleted"] == 1

    def test_run_cleanup_defaults_agent_location_history_to_365_when_no_policy_passed(self):
        now = datetime.now(timezone.utc)
        old_row = {"timestamp": now - timedelta(days=366), "agent_id": "agent-1"}
        recent_row = {"timestamp": now - timedelta(days=1), "agent_id": "agent-2"}
        db = _make_db([old_row, recent_row])
        svc = retention_service_mod.RetentionService(db)

        report = _run(svc.run_cleanup(policies={}))

        assert report["agent_location_history_deleted"] == 1
