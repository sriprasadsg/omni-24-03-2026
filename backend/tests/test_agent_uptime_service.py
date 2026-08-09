"""
Tests for Phase 48 Plan 01 (Fleet Observability & Uptime Rollups, FOBS-02) —
`agent_uptime_service.compute_uptime` on-the-fly gap-detection math, plus the
`agent_uptime_endpoints` GET /api/agents/{id}/uptime wiring (hours-clamp +
tenant-gated 404).

Uptime source is the `agent_metrics` collection (per-heartbeat rows) at a
fixed, assumed 30s cadence (D-09) — NEVER `agent_metrics_history` (a capped
decoy, see 48-RESEARCH.md). Hermetic — no real Mongo, no network.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from agent_uptime_service import compute_uptime
from authentication_service import get_current_user
from auth_types import TokenData


def _rows(timestamps):
    return [{"timestamp": ts.isoformat()} for ts in timestamps]


class TestComputeUptimeGapDetection:
    """Behavior cases from 48-01-PLAN.md Task 1 <behavior>."""

    def test_full_coverage_evenly_spaced_is_100_percent(self):
        now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        hours = 1
        window_start = now - timedelta(hours=hours)
        # 120 heartbeats at exactly 30s cadence covers every expected bucket.
        timestamps = [window_start + timedelta(seconds=30 * i) for i in range(120)]

        result = compute_uptime(_rows(timestamps), hours, now=now)

        assert result["uptime_percent"] == 100.0
        assert result["received_buckets"] == result["expected_buckets"]
        assert result["expected_buckets"] == 120

    def test_half_the_buckets_present_is_50_percent(self):
        now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        hours = 1
        window_start = now - timedelta(hours=hours)
        # Only the even-indexed 30s buckets receive a heartbeat -> half coverage.
        timestamps = [window_start + timedelta(seconds=30 * i) for i in range(0, 120, 2)]

        result = compute_uptime(_rows(timestamps), hours, now=now)

        assert result["uptime_percent"] == 50.0
        assert result["received_buckets"] == 60
        assert result["expected_buckets"] == 120

    def test_empty_rows_never_heartbeat_agent_yields_zero_no_exception(self):
        now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)

        result = compute_uptime([], 24, now=now)

        assert result["uptime_percent"] == 0.0
        assert result["received_buckets"] == 0
        assert isinstance(result["timeline"], list)

    def test_more_rows_than_expected_buckets_clips_at_100(self):
        now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        hours = 1
        window_start = now - timedelta(hours=hours)
        # Heartbeat every 5s (agent faster than the assumed 30s cadence) ->
        # 720 raw rows against only 120 expected 30s buckets.
        timestamps = [window_start + timedelta(seconds=5 * i) for i in range(720)]

        result = compute_uptime(_rows(timestamps), hours, now=now)

        assert len(timestamps) > result["expected_buckets"]
        assert result["uptime_percent"] == 100.0
        assert result["uptime_percent"] <= 100.0
        assert result["received_buckets"] <= result["expected_buckets"]

    def test_timeline_is_list_of_bucket_dicts_with_start_and_up(self):
        now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        hours = 2
        window_start = now - timedelta(hours=hours)
        timestamps = [window_start + timedelta(seconds=30 * i) for i in range(0, 240, 3)]

        result = compute_uptime(_rows(timestamps), hours, now=now)

        assert isinstance(result["timeline"], list)
        assert len(result["timeline"]) > 0
        for block in result["timeline"]:
            assert "start" in block and "up" in block
            assert isinstance(block["up"], bool)
            # Must parse cleanly as an ISO-8601 string.
            datetime.fromisoformat(block["start"])


# ─── endpoint wiring (Task 2) ────────────────────────────────────────────────

def _user(role="security_analyst", tenant_id="tenant-a"):
    return TokenData(username="u@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _client(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class _AsyncCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def to_list(self, *a, **k):
        async def _inner():
            return self._docs
        return _inner()


class TestUptimeEndpoint:

    @patch("agent_uptime_endpoints.get_database")
    def test_hours_clamped_to_48_max(self, mock_get_db):
        import agent_uptime_endpoints as m

        agent_col = MagicMock(find_one=AsyncMock(return_value={"tenantId": "tenant-a"}))
        metrics_col = MagicMock(find=MagicMock(return_value=_AsyncCursor([])))
        db = MagicMock()
        db.agents = agent_col
        db.agent_metrics = metrics_col
        mock_get_db.return_value = db

        res = _client(m.router, _user()).get("/api/agents/agent-1/uptime?hours=9999")

        assert res.status_code == 200
        assert res.json()["hours"] == 48

    @patch("agent_uptime_endpoints.get_database")
    def test_hours_clamped_to_1_min(self, mock_get_db):
        import agent_uptime_endpoints as m

        agent_col = MagicMock(find_one=AsyncMock(return_value={"tenantId": "tenant-a"}))
        metrics_col = MagicMock(find=MagicMock(return_value=_AsyncCursor([])))
        db = MagicMock()
        db.agents = agent_col
        db.agent_metrics = metrics_col
        mock_get_db.return_value = db

        res = _client(m.router, _user()).get("/api/agents/agent-1/uptime?hours=0")

        assert res.status_code == 200
        assert res.json()["hours"] == 1

    @patch("agent_uptime_endpoints.get_database")
    def test_cross_tenant_agent_404s(self, mock_get_db):
        import agent_uptime_endpoints as m

        # Non-super-admin's agent lookup includes tenantId, so a cross-tenant
        # agent_id simply doesn't match -> find_one returns None -> 404.
        agent_col = MagicMock(find_one=AsyncMock(return_value=None))
        db = MagicMock()
        db.agents = agent_col
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="security_analyst", tenant_id="tenant-a")).get(
            "/api/agents/other-tenant-agent/uptime"
        )

        assert res.status_code == 404

    @patch("agent_uptime_endpoints.get_database")
    def test_response_includes_uptime_percent_and_timeline(self, mock_get_db):
        import agent_uptime_endpoints as m

        agent_col = MagicMock(find_one=AsyncMock(return_value={"tenantId": "tenant-a"}))
        metrics_col = MagicMock(find=MagicMock(return_value=_AsyncCursor([])))
        db = MagicMock()
        db.agents = agent_col
        db.agent_metrics = metrics_col
        mock_get_db.return_value = db

        res = _client(m.router, _user()).get("/api/agents/agent-1/uptime?hours=1")

        assert res.status_code == 200
        body = res.json()
        assert "uptime_percent" in body
        assert "timeline" in body
        assert body["uptime_percent"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
