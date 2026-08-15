"""
Regression suite for the two failure modes the Phase 59 warranty alert sweep
(ITAM-FIN-02) must survive. Split out from test_itam_finance_sweep.py to
keep both files under the CLAUDE.md 500-line limit; shared db-stub fixtures
live in itam_finance_sweep_test_support.py.

Covers (all Task 3):
  - raw_db_no_crash: the real notification functions against a stub without
    a _db attribute — regression guard for RESEARCH Pitfall 1
  - idempotent_alert: consecutive passes produce exactly one alert;
    clearing the marker re-enables alerting
  - sweep_resilience: delivery failure isolation
  - sweep_tenant_scope: cross-tenant delivery isolation
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import itam_finance_service as svc
from tests.itam_finance_sweep_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    _RawSweepDb,
    _run,
    _asset,
    _user,
)


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
        # The sweep's db is raw (no TenantIsolatedCollection to auto-inject
        # tenantId), so send_alert must set it explicitly — otherwise the
        # alert is invisible to every tenantId-filtered reader in
        # notification_endpoints.py (list/mark-read/delete).
        assert db._captured_notifications[0]["tenantId"] == "tenant-a"
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
            assets=[_asset(purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1)],
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
            assets=[_asset(purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1)],
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
            assets=[_asset(purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1)],
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
            assets=[_asset(purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1)],
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
            assets=[_asset(purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1)],
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
            assets=[_asset(purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 1
        # Marker still written despite both failures
        assert db._docs["assets"]["asset-1"].get("warrantyAlertSentAt") is not None

    @patch.object(svc, "get_notification_service")
    @patch.object(svc, "send_notification")
    def test_sweep_resilience_marker_write_raise_does_not_abort_pass(self, mock_send, mock_get_ns):
        """A marker-write failure (e.g. a transient DB error) must be isolated
        exactly like the two delivery attempts before it — not propagate past
        the async-for loop and silently drop every remaining asset in the
        pass. Two assets are seeded; only the first asset's update_one call
        raises, so the second asset must still be reached, alerted and
        counted."""
        mock_ns = MagicMock()
        mock_ns.send_alert = AsyncMock()
        mock_get_ns.return_value = mock_ns
        mock_send.return_value = {"matched_rules": 0, "sent": 0}

        db = _RawSweepDb(
            assets=[
                _asset(id="asset-a", tenantId="tenant-a",
                       purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1),
                _asset(id="asset-b", tenantId="tenant-a",
                       purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1),
            ],
            users=[_user()],
        )
        real_update_one = db.assets.update_one

        async def flaky_update_one(filter_spec, update):
            if filter_spec.get("id") == "asset-a":
                raise RuntimeError("transient db error")
            return await real_update_one(filter_spec, update)

        db.assets.update_one = flaky_update_one

        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 2, "both assets must be handled — the loop must not abort on the first asset's marker-write failure"
        assert mock_ns.send_alert.await_count == 2, "delivery must still be attempted for the second asset"
        # asset-a's own marker write raised, so it was never actually set —
        # it will be retried (and re-alerted) on the next pass, which is the
        # documented degrade-gracefully behavior, not a second crash.
        assert db._docs["assets"]["asset-a"].get("warrantyAlertSentAt") is None
        assert db._docs["assets"]["asset-b"].get("warrantyAlertSentAt") is not None

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
                       purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1),
                _asset(id="asset-b", tenantId="tenant-b", assetTag="TAG-B",
                       purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1),
            ],
            users=[
                _user(id="u1", email="admin-a@test.com", role="admin", tenantId="tenant-a"),
                _user(id="u2", email="admin-b@test.com", role="admin", tenantId="tenant-b"),
            ],
        )

        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 2
        assert mock_ns.send_alert.await_count == 2

        call1_kwargs = mock_ns.send_alert.call_args_list[0].kwargs
        call2_kwargs = mock_ns.send_alert.call_args_list[1].kwargs

        assert call1_kwargs["tenant_id"] == "tenant-a"
        assert call2_kwargs["tenant_id"] == "tenant-b"
        assert "admin-a@test.com" in call1_kwargs["recipients"]
        assert "admin-b@test.com" not in call1_kwargs["recipients"]
        assert "admin-b@test.com" in call2_kwargs["recipients"]
        assert "admin-a@test.com" not in call2_kwargs["recipients"]
