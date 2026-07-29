"""
Tests for Phase 48 Plan 02 (Fleet Observability & Uptime Rollups, FOBS-02,
D-01b) — the daily `agent_uptime_rollup_loop()` background sweep (Task 1)
and `retention_service.cleanup_agent_uptime_rollups()` wiring (Task 2).

Hermetic: no real Mongo, no network. Drives the factored single-pass helper
`_run_agent_uptime_rollup_once(db)` directly rather than the infinite
`while True: await asyncio.sleep(86400)` loop.

`db` is a bare object exposing ONLY `_db` (no autovivifying MagicMock at the
top level) so that any accidental use of the ambient wrapped handle (e.g.
`db.tenants` instead of `db._db.tenants`) raises AttributeError immediately —
proving the sweep reads/writes exclusively through raw `db._db` (Pattern 1).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import app_background_tasks
import retention_service as retention_service_mod


def _run(coro):
    return asyncio.run(coro)


def _matches(doc, filt):
    """Minimal equality-only filter matcher; operator filters (dict values,
    e.g. {"$gte": ...}) are ignored — the fake fixtures already only contain
    rows within the relevant window, so this test doesn't need real range
    semantics to exercise the sweep's write shape."""
    for k, v in (filt or {}).items():
        if isinstance(v, dict):
            continue
        if doc.get(k) != v:
            return False
    return True


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, length=None):
        return list(self._docs)


class _FakeReadCollection:
    """Stand-in for db._db.tenants / db._db.agents / db._db.agent_metrics."""

    def __init__(self, docs):
        self._docs = docs
        self.find_calls = []

    def find(self, filt=None, proj=None):
        self.find_calls.append(filt)
        matched = [d for d in self._docs if _matches(d, filt)]
        return _FakeCursor(matched)


class _FakeRollupsCollection:
    """Stand-in for db._db.agent_uptime_rollups — records every upsert."""

    def __init__(self):
        self.upserts = []

    async def update_one(self, filt, update, upsert=False):
        self.upserts.append({"filter": filt, "update": update, "upsert": upsert})
        result = MagicMock()
        result.matched_count = 0
        result.modified_count = 0
        result.upserted_id = "fake-id"
        return result


class _RawDB:
    """The raw Motor-ish db that lives at `wrapped_db._db`."""

    def __init__(self, tenants, agents, metrics_rows):
        self.tenants = _FakeReadCollection(tenants)
        self.agents = _FakeReadCollection(agents)
        self.agent_metrics = _FakeReadCollection(metrics_rows)
        self.agent_uptime_rollups = _FakeRollupsCollection()


class _WrappedDBHandle:
    """Exposes ONLY `_db` — accessing any other attribute (e.g. `.tenants`)
    raises AttributeError, so a code path that mistakenly used the wrapped
    handle instead of raw `db._db` fails loudly rather than silently."""

    def __init__(self, raw_db):
        self._db = raw_db


def _iso(dt):
    return dt.isoformat()


def _make_db(now):
    """2 tenants, 3 agents total: tenant-a has agent-1 (with recent
    heartbeats) and agent-2 (zero heartbeats -> 0% uptime); tenant-b has
    agent-3 (with recent heartbeats)."""
    tenants = [{"id": "tenant-a"}, {"id": "tenant-b"}]
    agents = [
        {"id": "agent-1", "tenantId": "tenant-a"},
        {"id": "agent-2", "tenantId": "tenant-a"},
        {"id": "agent-3", "tenantId": "tenant-b"},
    ]
    metrics_rows = [
        {"agent_id": "agent-1", "timestamp": _iso(now - timedelta(minutes=5))},
        {"agent_id": "agent-1", "timestamp": _iso(now - timedelta(minutes=10))},
        {"agent_id": "agent-3", "timestamp": _iso(now - timedelta(minutes=1))},
    ]
    raw_db = _RawDB(tenants, agents, metrics_rows)
    return _WrappedDBHandle(raw_db)


class TestAgentUptimeRollupSweep:
    def test_one_upsert_per_agent_across_all_tenants(self):
        now = datetime.now(timezone.utc)
        db = _make_db(now)

        written = _run(app_background_tasks._run_agent_uptime_rollup_once(db))

        assert written == 3
        assert len(db._db.agent_uptime_rollups.upserts) == 3

    def test_upsert_keyed_on_agent_id_and_date_with_tenant_id_set(self):
        now = datetime.now(timezone.utc)
        db = _make_db(now)

        _run(app_background_tasks._run_agent_uptime_rollup_once(db))

        upserts_by_agent = {
            u["filter"]["agent_id"]: u for u in db._db.agent_uptime_rollups.upserts
        }
        assert set(upserts_by_agent.keys()) == {"agent-1", "agent-2", "agent-3"}

        date_key = now.strftime("%Y-%m-%d")
        for aid, expected_tenant in (
            ("agent-1", "tenant-a"),
            ("agent-2", "tenant-a"),
            ("agent-3", "tenant-b"),
        ):
            u = upserts_by_agent[aid]
            assert u["filter"]["date"] == date_key
            assert u["upsert"] is True
            assert u["update"]["$set"]["tenant_id"] == expected_tenant

    def test_upsert_timestamp_is_native_datetime_not_isoformat_string(self):
        now = datetime.now(timezone.utc)
        db = _make_db(now)

        _run(app_background_tasks._run_agent_uptime_rollup_once(db))

        for u in db._db.agent_uptime_rollups.upserts:
            ts = u["update"]["$set"]["timestamp"]
            assert isinstance(ts, datetime), (
                "rollup timestamp must be a native BSON Date (datetime), "
                "never .isoformat()'d — retention compares it with $lt"
            )

    def test_agent_with_no_heartbeats_gets_zero_percent_uptime(self):
        now = datetime.now(timezone.utc)
        db = _make_db(now)

        _run(app_background_tasks._run_agent_uptime_rollup_once(db))

        agent_2_upsert = next(
            u for u in db._db.agent_uptime_rollups.upserts
            if u["filter"]["agent_id"] == "agent-2"
        )
        assert agent_2_upsert["update"]["$set"]["uptime_percent"] == 0.0

    def test_reads_go_through_raw_db_underscore_db(self):
        """If the sweep mistakenly used the ambient wrapped `db` handle
        instead of raw `db._db`, `_WrappedDBHandle` would raise
        AttributeError on the very first `db.tenants` access — so simply
        completing without error already proves raw-db usage. This test
        also positively asserts the raw collections were actually queried."""
        now = datetime.now(timezone.utc)
        db = _make_db(now)

        _run(app_background_tasks._run_agent_uptime_rollup_once(db))

        assert len(db._db.tenants.find_calls) == 1
        assert len(db._db.agents.find_calls) == 2  # once per tenant
        assert len(db._db.agent_metrics.find_calls) == 3  # once per agent

    def test_loop_function_exists_and_is_registered_by_name(self):
        assert hasattr(app_background_tasks, "agent_uptime_rollup_loop")
        assert asyncio.iscoroutinefunction(app_background_tasks.agent_uptime_rollup_loop)


class _DeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


class _FakeRollupsRetentionCollection:
    """Minimal in-memory stand-in for db.agent_uptime_rollups supporting the
    one delete_many shape cleanup_agent_uptime_rollups needs:
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


def _make_retention_db(rollup_docs):
    db = MagicMock()
    db.agent_uptime_rollups = _FakeRollupsRetentionCollection(rollup_docs)
    for name in ("audit_logs", "metrics", "notifications", "agent_location_history"):
        col = MagicMock()
        col.delete_many = AsyncMock(return_value=_DeleteResult(0))
        setattr(db, name, col)
    return db


class TestCleanupAgentUptimeRollups:
    def test_90_day_old_row_deleted_1_day_old_row_retained(self):
        now = datetime.now(timezone.utc)
        old_row = {"timestamp": now - timedelta(days=91), "agent_id": "agent-1"}
        recent_row = {"timestamp": now - timedelta(days=1), "agent_id": "agent-2"}
        db = _make_retention_db([old_row, recent_row])
        svc = retention_service_mod.RetentionService(db)

        deleted = _run(svc.cleanup_agent_uptime_rollups(retention_days=90))

        assert deleted == 1
        assert db.agent_uptime_rollups._docs == [recent_row]

    def test_cutoff_uses_native_datetime_not_isoformat_string(self):
        now = datetime.now(timezone.utc)
        db = _make_retention_db([{"timestamp": now - timedelta(days=120), "agent_id": "a1"}])
        svc = retention_service_mod.RetentionService(db)

        _run(svc.cleanup_agent_uptime_rollups(retention_days=90))

        cutoff = db.agent_uptime_rollups.last_filter["timestamp"]["$lt"]
        assert isinstance(cutoff, datetime)


class TestRunCleanupWiringForUptimeRollups:
    def test_run_cleanup_report_includes_agent_uptime_rollups_deleted_key(self):
        now = datetime.now(timezone.utc)
        old_row = {"timestamp": now - timedelta(days=91), "agent_id": "agent-1"}
        recent_row = {"timestamp": now - timedelta(days=1), "agent_id": "agent-2"}
        db = _make_retention_db([old_row, recent_row])
        svc = retention_service_mod.RetentionService(db)

        report = _run(svc.run_cleanup(policies={"agent_uptime_rollups": 90}))

        assert "agent_uptime_rollups_deleted" in report
        assert report["agent_uptime_rollups_deleted"] == 1

    def test_run_cleanup_defaults_agent_uptime_rollups_to_90_when_no_policy_passed(self):
        now = datetime.now(timezone.utc)
        old_row = {"timestamp": now - timedelta(days=91), "agent_id": "agent-1"}
        recent_row = {"timestamp": now - timedelta(days=1), "agent_id": "agent-2"}
        db = _make_retention_db([old_row, recent_row])
        svc = retention_service_mod.RetentionService(db)

        report = _run(svc.run_cleanup(policies={}))

        assert report["agent_uptime_rollups_deleted"] == 1

    def test_run_cleanup_does_not_add_agent_metrics_retention(self):
        """Pitfall 4 / D-02 out-of-scope guard: agent_metrics retention must
        NOT be added by this plan."""
        now = datetime.now(timezone.utc)
        db = _make_retention_db([{"timestamp": now - timedelta(days=91), "agent_id": "a1"}])
        svc = retention_service_mod.RetentionService(db)

        report = _run(svc.run_cleanup(policies={}))

        assert "agent_metrics_deleted" not in report
        assert not hasattr(svc, "cleanup_agent_metrics")
