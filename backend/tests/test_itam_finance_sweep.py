"""
Tests for the Phase 59 warranty alert sweep (ITAM-FIN-02) and its startup
registration in app_startup.py.

Covers:
  - sweep_core: asset selection, tenant isolation, marker write (Task 1)
  - raw_db_no_crash: the real notification functions against a stub without
    _db attribute — regression guard for RESEARCH Pitfall 1 (Task 3)
  - idempotent_alert: consecutive passes produce exactly one alert;
    clearing the marker re-enables alerting (Task 3)
  - sweep_resilience: delivery failure isolation (Task 3)
  - sweep_tenant_scope: cross-tenant delivery isolation (Task 3)
  - raw_db_registration: source-level guards on the service module and
    app_startup registration (Task 2)
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import itam_finance_service as svc
from compliance_remediation_sla_service import _ADMIN_ROLES


# ===========================================================================
# _RawSweepDb — plain-class stub designed to genuinely lack _db
# ===========================================================================
class _RawSweepDb:
    """Plain-class db stub, NOT a MagicMock and with NO __getattr__ fallback
    and NO _db attribute, so hasattr(stub, "_db") is genuinely False.

    A mock-based fixture auto-creates _db on attribute access and would make
    every Pitfall-1 assertion in this file pass vacuously while the real
    defect survived.

    Collection attributes are in-memory dicts seeded at construction time.
    Assets live as docs in a list; updates mutate them in place so a second
    pass sees the markers the first pass wrote.
    """

    def __init__(self, assets=None, users=None, rules=None, channels=None):
        self._docs = {  # in-memory document store keyed by (coll, id)
            "assets": {d["id"]: dict(d) for d in (assets or [])},
            "users": list(users or []),
        }
        self._rules = list(rules or [])
        self._channels = list(channels or [])

        self._captured_asset_filters = []
        self._captured_user_filters = []
        self._captured_update_one_filters = []
        self._captured_notifications = []
        self._settings_find_one_result = None
        self._settings_find_one_call_count = 0

        # Expose collection-shaped attributes for itam_finance_service code
        self.assets = _AssetsCollection(self)
        self.users = _UsersCollection(self)
        self.system_settings = _SystemSettings(self)
        self.notifications = _Notifications(self)
        self.notification_rules = _NotificationRules(self)
        self.notification_channels = _NotificationChannels(self)


class _AssetsCollection:
    def __init__(self, db):
        self._db = db

    def find(self, filter_spec, projection=None):
        self._db._captured_asset_filters.append(filter_spec)
        matched = [d for d in self._db._docs["assets"].values()
                   if all(d.get(k) == v if not isinstance(v, dict) else True
                          for k, v in filter_spec.items()
                          if not isinstance(v, dict))]
        # Apply $exists negation filter
        filtered = []
        for d in matched:
            skip = False
            for k, v in filter_spec.items():
                if isinstance(v, dict) and "$exists" in v:
                    if v["$exists"] and k in d:
                        continue
                    elif not v["$exists"] and k not in d:
                        continue
                    elif v["$exists"] and k not in d:
                        skip = True
                    elif not v["$exists"] and k in d:
                        skip = True
            if not skip:
                filtered.append(d)
        return _AsyncCursor(filtered)

    async def update_one(self, filter_spec, update):
        self._db._captured_update_one_filters.append(filter_spec)
        doc_id = filter_spec.get("id")
        tenant_id = filter_spec.get("tenantId")
        for d in self._db._docs["assets"].values():
            if d["id"] == doc_id and d.get("tenantId") == tenant_id:
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                break


class _UsersCollection:
    def __init__(self, db):
        self._db = db

    def find(self, filter_spec):
        self._db._captured_user_filters.append(filter_spec)
        matched = []
        for user in self._db._docs["users"]:
            match = True
            for k, v in filter_spec.items():
                if k == "role" and isinstance(v, dict) and "$in" in v:
                    if user.get("role") not in v["$in"]:
                        match = False
                elif user.get(k) != v:
                    match = False
            if match:
                matched.append(user)
        return _AsyncCursor(matched)


class _SystemSettings:
    def __init__(self, db):
        self._db = db

    async def find_one(self, query):
        # Return a default 30-day window for the warranty alert window setting
        if query.get("type") == "itam_warranty_alert_window":
            return {"windowDays": 30}
        return None


class _Notifications:
    def __init__(self, db):
        self._db = db

    async def insert_one(self, doc):
        self._db._captured_notifications.append(doc)


class _NotificationRules:
    def __init__(self, db):
        self._db = db

    def find(self, filter_spec):
        matched = []
        for rule in self._db._rules:
            match = True
            for k, v in filter_spec.items():
                if rule.get(k) != v:
                    match = False
            if match:
                matched.append(rule)
        return _AsyncCursor(matched)


class _NotificationChannels:
    def __init__(self, db):
        self._db = db

    def find(self, filter_spec):
        matched = []
        for ch in self._db._channels:
            match = True
            for k, v in filter_spec.items():
                if ch.get(k) != v:
                    match = False
            if match:
                matched.append(ch)
        return _AsyncCursor(matched)


class _AsyncCursor:
    """Async-iterable cursor stub."""

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

    async def to_list(self, length=None):
        return list(self._docs)


def _run(coro):
    return asyncio.run(coro)


def _asset(**overrides):
    asset = {
        "id": "asset-1",
        "tenantId": "tenant-a",
        "assetTag": "TAG-001",
        "purchaseDate": "2026-01-15T00:00:00Z",
        "warrantyMonths": 12,
    }
    asset.update(overrides)
    return asset


def _user(**overrides):
    user = {
        "id": "user-1",
        "email": "admin@tenant-a.com",
        "role": "admin",
        "tenantId": "tenant-a",
    }
    user.update(overrides)
    return user


# ===========================================================================
# TestWarrantySweepCore — Task 1: first six behavior rows
# ===========================================================================
class TestWarrantySweepCore:
    """Covers the first six behavior rows of the sweep: expiring asset alerted
    and marked; expired asset alerted; active (outside window) not alerted; no
    tenantId skipped; user filter carries tenantId + role set; update_one
    filter carries both id and tenantId."""

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_sweep_core_expiring_asset_alerted_and_marked(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns
        mock_send.return_value = {"matched_rules": 0, "sent": 0}

        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 1, "expiring asset must be alerted"
        assert mock_ns.send_alert.await_count >= 1
        # Marker written
        assert db._docs["assets"]["asset-1"].get("warrantyAlertSentAt") is not None

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_sweep_core_expired_asset_alerted(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns
        mock_send.return_value = {"matched_rules": 0, "sent": 0}

        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=3)],
            users=[_user()],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 1
        assert mock_ns.send_alert.await_count >= 1

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_sweep_core_outside_window_not_alerted(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns

        # Purchase 3 months ago with 36-month warranty → still active + well outside window
        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-05-01T00:00:00Z", warrantyMonths=36)],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 0
        mock_ns.send_alert.assert_not_awaited()
        assert db._docs["assets"]["asset-1"].get("warrantyAlertSentAt") is None

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_sweep_core_no_tenant_id_skipped(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns

        db = _RawSweepDb(
            assets=[_asset(tenantId="")],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 0
        mock_send.assert_not_called()
        mock_ns.send_alert.assert_not_awaited()

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_sweep_core_user_filter_carries_tenant_id_and_roles(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns

        admin_emails = ["admin1@a.com", "admin2@a.com"]
        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[
                _user(id="u1", email="admin1@a.com", role="admin", tenantId="tenant-a"),
                _user(id="u2", email="admin2@a.com", role="Super Admin", tenantId="tenant-a"),
            ],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 1

        # Verify users.find was called with tenantId and admin role set
        assert len(db._captured_user_filters) >= 1
        uf = db._captured_user_filters[0]
        assert uf.get("tenantId") == "tenant-a"
        assert "$in" in uf.get("role", {})
        assert set(uf["role"]["$in"]) == _ADMIN_ROLES

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_sweep_core_update_one_filter_carries_id_and_tenant_id(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns

        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 1

        assert len(db._captured_update_one_filters) >= 1
        uf = db._captured_update_one_filters[0]
        assert uf.get("id") == "asset-1"
        assert uf.get("tenantId") == "tenant-a"


# ===========================================================================
# TestSweepRawDbNoCrash — Task 3: regression guard for RESEARCH Pitfall 1
# ===========================================================================
class TestSweepRawDbNoCrash:
    """The single most important class in this phase.

    Runs run_warranty_alert_pass against the _RawSweepDb stub with
    get_notification_service and send_notification NOT patched, so the
    real functions execute against a handle that genuinely lacks _db.

    Regression guard for RESEARCH Pitfall 1: the bug this guards against is
    invisible in production because the sweep's outer handler only logs.
    Any future fixture change replacing the stub with a mock silently voids
    the whole class.
    """

    def test_raw_db_no_crash_completes_and_writes_notification(self):
        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
            rules=[],
            channels=[],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 1
        # Real send_alert inserted a notification
        assert len(db._captured_notifications) >= 1
        assert db._docs["assets"]["asset-1"].get("warrantyAlertSentAt") is not None

    def test_raw_db_no_crash_rule_routed_does_not_raise_for_tenant_with_no_rules(self):
        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
            rules=[],
            channels=[],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 1
        # Notifications still written by in-app path
        assert len(db._captured_notifications) >= 1

    def test_raw_db_no_crash_rule_routed_adapter_exposes_db(self):
        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
            rules=[],
            channels=[],
        )
        adapter = svc._RawDbForNotificationRules(db)
        assert hasattr(adapter, "_db")
        assert adapter._db is db


# ===========================================================================
# TestSweepIdempotency — Task 3: idempotency contract
# ===========================================================================
class TestSweepIdempotency:
    """Covers the idempotency contract: two consecutive passes produce exactly
    one alert, one rule-routed call, one marker write; clearing the marker
    makes the asset alertable again."""

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_idempotent_alert_two_passes_one_alert(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns
        mock_send.return_value = {"matched_rules": 0, "sent": 0}

        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
        )
        count1 = _run(svc.run_warranty_alert_pass(db))
        assert count1 == 1
        assert mock_ns.send_alert.await_count == 1
        assert mock_send.call_count == 1

        # Second pass — should be a no-op
        mock_ns.send_alert.reset_mock()
        mock_send.reset_mock()
        count2 = _run(svc.run_warranty_alert_pass(db))
        assert count2 == 0
        mock_ns.send_alert.assert_not_awaited()
        mock_send.assert_not_called()

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_idempotent_alert_clearing_marker_re_enables_alerting(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns
        mock_send.return_value = {"matched_rules": 0, "sent": 0}

        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
        )
        count1 = _run(svc.run_warranty_alert_pass(db))
        assert count1 == 1

        # Clear the marker — simulates PATCH /purchase
        db._docs["assets"]["asset-1"].pop("warrantyAlertSentAt", None)

        mock_ns.send_alert.reset_mock()
        mock_send.reset_mock()
        count2 = _run(svc.run_warranty_alert_pass(db))
        assert count2 == 1
        assert mock_ns.send_alert.await_count >= 1

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_idempotent_alert_cursor_filter_contains_marker_guard(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns
        mock_send.return_value = {"matched_rules": 0, "sent": 0}

        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
        )
        _run(svc.run_warranty_alert_pass(db))

        assert len(db._captured_asset_filters) >= 1
        cursor_filter = db._captured_asset_filters[0]
        assert "warrantyAlertSentAt" in cursor_filter
        assert cursor_filter["warrantyAlertSentAt"] == {"$exists": False}

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_idempotent_alert_second_pass_returns_zero(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns
        mock_send.return_value = {"matched_rules": 0, "sent": 0}

        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
        )
        count1 = _run(svc.run_warranty_alert_pass(db))
        assert count1 == 1
        count2 = _run(svc.run_warranty_alert_pass(db))
        assert count2 == 0


# ===========================================================================
# TestSweepResilienceAndTenantScope — Task 3: failure isolation + tenant scope
# ===========================================================================
class TestSweepResilienceAndTenantScope:
    """Failure isolation: when in-app delivery raises, rule-routed still
    happens, marker still written, count still returned. When both raise,
    pass still completes. Two-tenant isolation: each tenant gets only its
    own admins' emails."""

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_sweep_resilience_in_app_raise_rule_still_runs(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock(side_effect=RuntimeError("in-app down"))
        mock_get_ns.return_value = mock_ns
        mock_send.return_value = {"matched_rules": 0, "sent": 0}

        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 1
        assert mock_send.call_count == 1  # rule-routed still called
        assert db._docs["assets"]["asset-1"].get("warrantyAlertSentAt") is not None

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_sweep_resilience_both_paths_raise_pass_completes(self, mock_send, mock_get_ns):
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock(side_effect=RuntimeError("in-app down"))
        mock_get_ns.return_value = mock_ns
        mock_send.side_effect = RuntimeError("rule-routed down")

        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 1
        # Marker still written despite both failures
        assert db._docs["assets"]["asset-1"].get("warrantyAlertSentAt") is not None

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_sweep_tenant_scope_two_tenants_isolated(self, mock_send, mock_get_ns):
        """Two assets under two different tenants with distinct admin users:
        each send_alert call receives only its own tenant's recipients and
        its own tenant_id; neither recipient list contains the other tenant's
        admin email."""
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns
        mock_send.return_value = {"matched_rules": 0, "sent": 0}

        db = _RawSweepDb(
            assets=[
                _asset(id="asset-a", tenantId="tenant-a", assetTag="TAG-A",
                       purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1),
                _asset(id="asset-b", tenantId="tenant-b", assetTag="TAG-B",
                       purchaseDate="2026-07-01T00:00:00Z", warrantyMonths=1),
            ],
            users=[
                _user(id="u1", email="admin-a@test.com", role="admin", tenantId="tenant-a"),
                _user(id="u2", email="admin-b@test.com", role="admin", tenantId="tenant-b"),
            ],
        )

        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 2
        assert mock_ns.send_alert.await_count == 2

        # Check each send_alert call's recipient list
        call_args_list = mock_ns.send_alert.call_args_list
        # First call is tenant-a
        call1_kwargs = call_args_list[0].kwargs if hasattr(call_args_list[0], 'kwargs') else {}
        # Use keyword args
        call1_kwargs = call_args_list[0].kwargs
        call2_kwargs = call_args_list[1].kwargs

        assert call1_kwargs["tenant_id"] == "tenant-a"
        assert call2_kwargs["tenant_id"] == "tenant-b"
        assert "admin-a@test.com" in call1_kwargs["recipients"]
        assert "admin-b@test.com" not in call1_kwargs["recipients"]
        assert "admin-b@test.com" in call2_kwargs["recipients"]
        assert "admin-a@test.com" not in call2_kwargs["recipients"]


# ===========================================================================
# TestWarrantySchedulerRegistration — Task 2: source-level regression guards
# ===========================================================================
class TestWarrantySchedulerRegistration:
    """Source-level regression guards cloned from
    test_compliance_remediation_sla.py's Test_raw_db_registration."""

    def test_raw_db_registration_scheduler_never_uses_get_database(self):
        import inspect
        src = inspect.getsource(svc)
        assert "get_database" not in src
        assert inspect.iscoroutinefunction(svc.run_warranty_alert_pass)
        assert inspect.iscoroutinefunction(svc.start_warranty_alert_scheduler)

    def test_raw_db_registration_app_startup_uses_raw_mongodb_db(self):
        import inspect
        import app_startup

        src = inspect.getsource(app_startup)
        idx = src.find("start_warranty_alert_scheduler")
        assert idx != -1, "app_startup does not register start_warranty_alert_scheduler yet"
        snippet = src[max(0, idx - 200): idx + 400]
        assert "_mdb.db" in snippet
        assert "get_database()" not in snippet