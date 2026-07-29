"""
Tests for agent_location_history_endpoints.py — Phase 46 (GAUD-02).

Covers the GET-only /api/agents/{agent_id}/location-history read surface
(tenant isolation, ascending sort, read-time dwell computation) and the
admin-gated GET/PATCH /api/settings/agent-location-tracking toggle, plus
the immutability guarantee (no PATCH/PUT/DELETE route anywhere on the
location-history path — D-10) verified via route-table introspection
rather than source grepping alone.

Mirrors test_compliance_remediation_sla.py's Test_tenant_scope /
Test_escalation_history conventions (mock-db factory, _AsyncCursor,
FastAPI TestClient + dependency-override on get_current_user).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# agent_location_history_endpoints.py is created/repaired in 46-04 — guard so
# collection succeeds even if it is ever briefly absent.
try:
    import agent_location_history_endpoints as endpoints_mod
except ImportError:
    endpoints_mod = None

from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData


# ---------------------------------------------------------------------------
# Shared mock-DB factory (mirrors test_compliance_remediation_sla.py's
# _mock_db())
# ---------------------------------------------------------------------------
def _mock_db():
    db = MagicMock()

    history_col = MagicMock()
    history_col.find = MagicMock()
    db.agent_location_history = history_col

    settings_col = MagicMock()
    settings_col.find_one = AsyncMock(return_value=None)
    settings_col.update_one = AsyncMock()
    db.system_settings = settings_col

    # get_database()/get_track_agent_location's `db._db if hasattr(db, "_db")
    # else db` unwrap guard must resolve back to this same configured mock.
    db._db = db

    return db


class _AsyncCursor:
    """Async-iterable cursor stub for db.<collection>.find(...)."""

    def __init__(self, docs=()):
        self._docs = list(docs)

    def __aiter__(self):
        return iter(self._docs)

    def sort(self, *a, **kw):
        return self

    async def to_list(self, length=None):
        return list(self._docs)


def _row(agent_id: str, tenant_id: str, ts: datetime, **overrides) -> dict:
    row = {
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "publicIp": "203.0.113.10",
        "geo": {"city": "Testville", "country": "US"},
        "asn": "AS64500",
        "vpn_heuristic": False,
        "timestamp": ts,
    }
    row.update(overrides)
    return row


_TENANT_A_USER = TokenData(
    username="a@test.com", role="user", tenant_id="tenant-a", mfa_verified=True,
)
_TENANT_A_ADMIN = TokenData(
    username="admin@test.com", role="admin", tenant_id="tenant-a", mfa_verified=True,
)


def _app_for(user):
    app = FastAPI()
    app.include_router(endpoints_mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


# ===========================================================================
# tenant_scope
# ===========================================================================
class TestTenantScope:
    def test_tenant_scope_cross_tenant_rows_excluded(self):
        assert endpoints_mod is not None, "agent_location_history_endpoints not yet created (46-04)"
        db = _mock_db()
        now = datetime.now(timezone.utc)
        rows = [
            _row("agent-1", "tenant-a", now - timedelta(hours=2)),
            _row("agent-1", "tenant-b", now - timedelta(hours=1)),
        ]
        db.agent_location_history.find = MagicMock(return_value=_AsyncCursor(rows))

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_USER)) as client:
                r = client.get("/api/agents/agent-1/location-history")

        assert r.status_code == 200
        entries = r.json()["entries"]
        assert len(entries) == 1
        assert entries[0]["tenantId"] == "tenant-a"

    def test_tenant_scope_query_anded_with_tenant_id(self):
        assert endpoints_mod is not None, "agent_location_history_endpoints not yet created (46-04)"
        db = _mock_db()
        db.agent_location_history.find = MagicMock(return_value=_AsyncCursor([]))

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_USER)) as client:
                client.get("/api/agents/agent-1/location-history")

        db.agent_location_history.find.assert_called_once()
        query = db.agent_location_history.find.call_args[0][0]
        assert query.get("agent_id") == "agent-1"
        assert query.get("tenantId") == "tenant-a"


# ===========================================================================
# sort
# ===========================================================================
class TestSort:
    def test_sort_ascending_by_timestamp(self):
        assert endpoints_mod is not None, "agent_location_history_endpoints not yet created (46-04)"
        db = _mock_db()
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t1 = t0 + timedelta(hours=1)
        rows = [_row("agent-1", "tenant-a", t0), _row("agent-1", "tenant-a", t1)]
        cursor = _AsyncCursor(rows)
        cursor.sort = MagicMock(wraps=cursor.sort)
        db.agent_location_history.find = MagicMock(return_value=cursor)

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_USER)) as client:
                r = client.get("/api/agents/agent-1/location-history")

        entries = r.json()["entries"]
        assert len(entries) == 2
        assert entries[0]["timestamp"] < entries[1]["timestamp"]
        cursor.sort.assert_called_once_with("timestamp", 1)


# ===========================================================================
# dwell — computed at read time (Pitfall 2), never a stored field
# ===========================================================================
class TestDwell:
    def test_dwell_intermediate_row_is_gap_to_next(self):
        assert endpoints_mod is not None, "agent_location_history_endpoints not yet created (46-04)"
        db = _mock_db()
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t1 = t0 + timedelta(minutes=30)
        rows = [_row("agent-1", "tenant-a", t0), _row("agent-1", "tenant-a", t1)]
        db.agent_location_history.find = MagicMock(return_value=_AsyncCursor(rows))

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_USER)) as client:
                r = client.get("/api/agents/agent-1/location-history")

        entries = r.json()["entries"]
        assert entries[0]["dwell_seconds"] == 1800.0

    def test_dwell_last_row_is_now_minus_timestamp_not_stored(self):
        assert endpoints_mod is not None, "agent_location_history_endpoints not yet created (46-04)"
        db = _mock_db()
        t0 = datetime.now(timezone.utc) - timedelta(hours=1)
        rows = [_row("agent-1", "tenant-a", t0)]
        db.agent_location_history.find = MagicMock(return_value=_AsyncCursor(rows))

        before = datetime.now(timezone.utc)
        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_USER)) as client:
                r = client.get("/api/agents/agent-1/location-history")
        after = datetime.now(timezone.utc)

        entries = r.json()["entries"]
        last_dwell = entries[0]["dwell_seconds"]
        # Never a stored/persisted field — must land in the live now()-t0 window.
        assert (before - t0).total_seconds() <= last_dwell <= (after - t0).total_seconds()
        # The seeded row itself carries no dwell_seconds — it is derived, not read back.
        assert "dwell_seconds" not in rows[0]


# ===========================================================================
# toggle GET (default true)
# ===========================================================================
class TestToggleGet:
    def test_toggle_get_defaults_to_enabled_true(self):
        assert endpoints_mod is not None, "agent_location_history_endpoints not yet created (46-04)"
        db = _mock_db()

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_USER)) as client:
                r = client.get("/api/settings/agent-location-tracking")

        assert r.status_code == 200
        assert r.json()["enabled"] is True


# ===========================================================================
# toggle PATCH — admin-gated
# ===========================================================================
class TestTogglePatch:
    def test_toggle_patch_admin_disables_and_get_reflects_it(self):
        assert endpoints_mod is not None, "agent_location_history_endpoints not yet created (46-04)"
        db = _mock_db()
        state: dict = {}

        async def _update_one(filter_, update, upsert=False):
            state.update(update["$set"])
            return MagicMock()

        async def _find_one(filter_):
            return dict(state) if state else None

        db.system_settings.update_one = AsyncMock(side_effect=_update_one)
        db.system_settings.find_one = AsyncMock(side_effect=_find_one)

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_ADMIN)) as client:
                patch_r = client.patch(
                    "/api/settings/agent-location-tracking", json={"enabled": False}
                )
                assert patch_r.status_code == 200
                assert patch_r.json()["enabled"] is False

                get_r = client.get("/api/settings/agent-location-tracking")

        assert get_r.status_code == 200
        assert get_r.json()["enabled"] is False
        db.system_settings.update_one.assert_awaited_once()

    def test_toggle_patch_forbidden_for_non_admin(self):
        assert endpoints_mod is not None, "agent_location_history_endpoints not yet created (46-04)"
        db = _mock_db()

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_USER)) as client:
                r = client.patch(
                    "/api/settings/agent-location-tracking", json={"enabled": False}
                )

        assert r.status_code == 403
        db.system_settings.update_one.assert_not_awaited()


# ===========================================================================
# immutability — no PATCH/PUT/DELETE anywhere on the location-history path
# (D-10). Enumerates the actual route table, not source inspection.
# ===========================================================================
class TestImmutability:
    def test_no_mutation_route_targets_location_history(self):
        assert endpoints_mod is not None, "agent_location_history_endpoints not yet created (46-04)"
        mutation_routes = [
            route
            for route in endpoints_mod.router.routes
            if "location-history" in getattr(route, "path", "")
            and ({"PATCH", "PUT", "DELETE"} & getattr(route, "methods", set()))
        ]
        assert mutation_routes == [], (
            f"found mutation route(s) on location-history path: {mutation_routes}"
        )
