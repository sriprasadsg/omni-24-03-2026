"""
Tests for compliance_remediation_sla_service.py / compliance_remediation_sla_endpoints.py
— Phase 44 (Remediation SLA & Escalation).

This is the Wave-0 test scaffold for the whole phase (44-VALIDATION.md Per-Task
Verification Map). All 5 groups below are scaffolded here; only `compute_sla` is
expected green at the end of 44-01. The other four exercise not-yet-existing
symbols on purpose and stay RED until 44-02 (run_sla_pass, raw_db_registration)
and 44-03 (escalation_history, tenant_scope) implement them.

Covers:
  - compute_sla: compute_remediation_sla() day-scale boundaries, resolved-task
    short-circuit, unparseable due_date, compute_escalation_level() tiers, and
    get_sla_at_risk_window()'s tenant-then-global-then-default lookup (44-01)
  - run_sla_pass: the background sweep creates a remediation_escalations entry
    and sends assignee+admin alerts for a breached task; skips tasks with no
    tenantId (44-02, RED here)
  - raw_db_registration: app_startup registers start_remediation_sla_scheduler
    with raw mongodb.db, never get_database (44-02, RED here — regression guard
    cloned from the tickets/ticketing_bridge precedent)
  - escalation_history: the escalations resource is GET-only — no PATCH/DELETE/
    PUT route targets the escalations path (44-03, RED here)
  - tenant_scope: a cross-tenant read of another tenant's escalations returns
    empty; the read query is AND'd with tenantId (44-03, RED here)
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# compliance_remediation_sla_service.py is created in 44-01 Task 2 — guard so
# collection succeeds even before that task lands (Task 1 runs first).
try:
    import compliance_remediation_sla_service as sla_svc
except ImportError:
    sla_svc = None

# compliance_remediation_sla_endpoints.py is a new file created in 44-02/44-03
# (44-PATTERNS.md) — does not exist yet during this plan.
try:
    import compliance_remediation_sla_endpoints as sla_endpoints_mod
except ImportError:
    sla_endpoints_mod = None

import compliance_remediation_endpoints as endpoints_mod


# ---------------------------------------------------------------------------
# Shared mock-DB factory (mirrors test_ticketing_bridge.py's _mock_db())
# ---------------------------------------------------------------------------
def _mock_db():
    db = MagicMock()

    tasks_col = MagicMock()
    tasks_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-inserted-id"))
    tasks_col.find = MagicMock()
    tasks_col.find_one = AsyncMock(return_value=None)
    tasks_col.update_one = AsyncMock()
    db.compliance_remediation_tasks = tasks_col

    settings_col = MagicMock()
    settings_col.find_one = AsyncMock(return_value=None)
    db.system_settings = settings_col

    escalations_col = MagicMock()
    escalations_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-esc-id"))
    escalations_col.find = MagicMock()
    db.remediation_escalations = escalations_col

    users_col = MagicMock()
    users_col.find = MagicMock()
    users_col.find_one = AsyncMock(return_value=None)
    db.users = users_col

    # get_sla_at_risk_window()'s `db._db if hasattr(db, "_db") else db` unwrap
    # guard must resolve back to this same configured mock, not an
    # auto-generated child MagicMock (mirrors test_evidence_lifecycle.py's
    # _make_mock_db() convention of wiring db._db explicitly).
    db._db = db

    return db


class _AsyncCursor:
    """Async-iterable cursor stub for db.<collection>.find(...)."""

    def __init__(self, docs=()):
        self._docs = list(docs)
        self._iter = iter(self._docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    def sort(self, *a, **kw):
        return self

    async def to_list(self, length=None):
        return list(self._docs)


def _run(coro):
    return asyncio.run(coro)


def _make_task(**overrides):
    task = {
        "id": "task-1",
        "tenantId": "tenant-a",
        "control_id": "CC-1.1",
        "framework_id": "SOC2",
        "priority": "high",
        "description": "MFA not enforced",
        "created_at": "2026-07-21T00:00:00Z",
        "asset_id": "asset-1",
        "assignee": "user@test.com",
        "assignee_type": "user",
        "status": "open",
        "due_date": None,
    }
    task.update(overrides)
    return task


# ===========================================================================
# compute_sla — 44-01, expected GREEN at end of this plan
# ===========================================================================
class Test_compute_sla:
    def test_compute_sla_at_risk_within_window(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        task = _make_task(due_date=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat())
        result = sla_svc.compute_remediation_sla(task, 3)
        assert result["sla_status"] == "at_risk"

    def test_compute_sla_breached_past_due(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        task = _make_task(due_date=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
        result = sla_svc.compute_remediation_sla(task, 3)
        assert result["sla_status"] == "breached"

    def test_compute_sla_ok_well_before_window(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        task = _make_task(due_date=(datetime.now(timezone.utc) + timedelta(days=10)).isoformat())
        result = sla_svc.compute_remediation_sla(task, 3)
        assert result["sla_status"] == "ok"

    def test_compute_sla_none_when_no_due_date(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        task = _make_task(due_date=None)
        result = sla_svc.compute_remediation_sla(task, 3)
        assert result["sla_status"] == "none"

    def test_compute_sla_unparseable_due_date_is_none(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        task = _make_task(due_date="not-a-date")
        result = sla_svc.compute_remediation_sla(task, 3)
        assert result["sla_status"] == "none"

    def test_compute_sla_resolved_task_is_ok_not_tracked(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        task = _make_task(
            status="resolved",
            due_date=(datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        )
        result = sla_svc.compute_remediation_sla(task, 3)
        assert result["sla_status"] == "ok"

    def test_compute_sla_escalation_level_tiers(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        assert sla_svc.compute_escalation_level(0.5) == 0
        assert sla_svc.compute_escalation_level(1) == 1
        assert sla_svc.compute_escalation_level(2.9) == 1
        assert sla_svc.compute_escalation_level(3) == 2
        assert sla_svc.compute_escalation_level(6.9) == 2
        assert sla_svc.compute_escalation_level(7) == 3
        assert sla_svc.compute_escalation_level(30) == 3

    def test_compute_sla_at_risk_window_tenant_doc_wins(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        db = _mock_db()
        db.system_settings.find_one = AsyncMock(
            return_value={"type": "remediation_sla_at_risk", "tenantId": "tenant-a", "windowDays": 5}
        )
        result = _run(sla_svc.get_sla_at_risk_window(db, "tenant-a"))
        assert result == 5

    def test_compute_sla_at_risk_window_global_fallback(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        db = _mock_db()

        async def _find_one(query):
            if query.get("tenantId") == "tenant-a":
                return None
            return {"type": "remediation_sla_at_risk", "windowDays": 4}

        db.system_settings.find_one = AsyncMock(side_effect=_find_one)
        result = _run(sla_svc.get_sla_at_risk_window(db, "tenant-a"))
        assert result == 4

    def test_compute_sla_at_risk_window_hardcoded_default(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        db = _mock_db()
        db.system_settings.find_one = AsyncMock(return_value=None)
        result = _run(sla_svc.get_sla_at_risk_window(db, "tenant-a"))
        assert result == 3

    def test_compute_sla_at_risk_window_clamps_to_minimum_one(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        db = _mock_db()
        db.system_settings.find_one = AsyncMock(
            return_value={"type": "remediation_sla_at_risk", "tenantId": "tenant-a", "windowDays": 0}
        )
        result = _run(sla_svc.get_sla_at_risk_window(db, "tenant-a"))
        assert result == 1


# ===========================================================================
# run_sla_pass — RED until 44-02
# ===========================================================================
class Test_run_sla_pass:
    def test_run_sla_pass_breached_task_creates_escalation_and_alerts(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        assert hasattr(sla_svc, "run_sla_pass"), "run_sla_pass not yet implemented (44-02)"

        db = _mock_db()
        task = _make_task(due_date=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat())
        db.compliance_remediation_tasks.find = MagicMock(return_value=_AsyncCursor([task]))
        db.users.find = MagicMock(
            return_value=_AsyncCursor(
                [{"id": "admin-1", "email": "admin@test.com", "role": "admin", "tenantId": "tenant-a"}]
            )
        )

        with patch.object(sla_svc, "get_notification_service") as mock_get_ns:
            mock_ns = MagicMock()
            mock_ns.send_alert = AsyncMock(return_value={"alert_id": "a1"})
            mock_get_ns.return_value = mock_ns
            _run(sla_svc.run_sla_pass(db))

        db.remediation_escalations.insert_one.assert_awaited()
        assert mock_ns.send_alert.await_count >= 1

    def test_run_sla_pass_skips_task_without_tenant_id(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        assert hasattr(sla_svc, "run_sla_pass"), "run_sla_pass not yet implemented (44-02)"

        db = _mock_db()
        task = _make_task(
            tenantId="", due_date=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        )
        db.compliance_remediation_tasks.find = MagicMock(return_value=_AsyncCursor([task]))

        _run(sla_svc.run_sla_pass(db))

        db.remediation_escalations.insert_one.assert_not_awaited()


# ===========================================================================
# raw_db_registration — RED until 44-02
# ===========================================================================
class Test_raw_db_registration:
    def test_raw_db_registration_scheduler_never_uses_get_database(self):
        assert sla_svc is not None, "compliance_remediation_sla_service not yet created (44-01 Task 2)"
        assert hasattr(sla_svc, "start_remediation_sla_scheduler"), (
            "start_remediation_sla_scheduler not yet implemented (44-02)"
        )
        import inspect

        src = inspect.getsource(sla_svc)
        assert "get_database" not in src
        assert inspect.iscoroutinefunction(sla_svc.run_sla_pass)
        assert inspect.iscoroutinefunction(sla_svc.start_remediation_sla_scheduler)

    def test_raw_db_registration_app_startup_uses_raw_mongodb_db(self):
        import inspect
        import app_startup

        src = inspect.getsource(app_startup)
        idx = src.find("start_remediation_sla_scheduler")
        assert idx != -1, "app_startup does not register start_remediation_sla_scheduler yet (44-02)"
        snippet = src[max(0, idx - 200) : idx + 400]
        assert "_mdb.db" in snippet
        assert "get_database()" not in snippet


# ===========================================================================
# escalation_history — RED until 44-03 (route-table introspection, not grep)
# ===========================================================================
class Test_escalation_history:
    def test_escalation_history_route_is_get_only_no_mutation_verbs(self):
        assert sla_endpoints_mod is not None, (
            "compliance_remediation_sla_endpoints not yet created (44-03)"
        )
        routes = sla_endpoints_mod.router.routes
        escalation_routes = [r for r in routes if getattr(r, "path", "").endswith("/escalations")]
        assert len(escalation_routes) >= 1, "no /escalations route registered yet"
        for route in escalation_routes:
            methods = getattr(route, "methods", set())
            assert "GET" in methods
            assert not ({"PATCH", "DELETE", "PUT"} & methods), (
                f"escalations route must never accept mutation verbs, found {methods}"
            )


# ===========================================================================
# tenant_scope — RED until 44-03
# ===========================================================================
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData

_ENDPOINT_USER = TokenData(
    username="v@test.com", role="user", tenant_id="tenant-a", mfa_verified=True,
)


def _sla_endpoint_app():
    app = FastAPI()
    app.include_router(sla_endpoints_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _ENDPOINT_USER
    return app


class Test_tenant_scope:
    def test_tenant_scope_cross_tenant_escalations_excluded(self):
        assert sla_endpoints_mod is not None, (
            "compliance_remediation_sla_endpoints not yet created (44-03)"
        )
        db = _mock_db()
        # Only another tenant's escalation exists — a tenant-a caller must see none.
        db.remediation_escalations.find = MagicMock(
            return_value=_AsyncCursor([{"task_id": "task-1", "tenantId": "tenant-b", "level": 1}])
        )

        with patch.object(sla_endpoints_mod, "get_database", return_value=db):
            with TestClient(_sla_endpoint_app()) as client:
                r = client.get("/api/compliance/remediation-tasks/task-1/escalations")

        assert r.status_code == 200
        assert r.json()["entries"] == []

    def test_tenant_scope_read_query_and_with_tenant_id(self):
        assert sla_endpoints_mod is not None, (
            "compliance_remediation_sla_endpoints not yet created (44-03)"
        )
        db = _mock_db()
        db.remediation_escalations.find = MagicMock(return_value=_AsyncCursor([]))

        with patch.object(sla_endpoints_mod, "get_database", return_value=db):
            with TestClient(_sla_endpoint_app()) as client:
                client.get("/api/compliance/remediation-tasks/task-1/escalations")

        db.remediation_escalations.find.assert_called_once()
        query = db.remediation_escalations.find.call_args[0][0]
        assert query.get("tenantId") == "tenant-a"
        assert query.get("task_id") == "task-1"
