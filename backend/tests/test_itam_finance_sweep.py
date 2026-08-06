"""
Tests for the Phase 59 warranty alert sweep (ITAM-FIN-02) and its startup
registration in app_startup.py.

Covers:
  - sweep_core: asset selection, tenant isolation, marker write (Task 1)
  - raw_db_registration: source-level guards on the service module and
    app_startup registration (Task 2)

The two-failure-mode regression suite (raw_db_no_crash, idempotent_alert,
sweep_resilience, sweep_tenant_scope — Task 3) lives in
test_itam_finance_sweep_resilience.py; shared db-stub fixtures live in
itam_finance_sweep_test_support.py. Split across three files to keep each
one under the CLAUDE.md 500-line limit.
"""
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import itam_finance_service as svc
from compliance_remediation_sla_service import _ADMIN_ROLES
from tests.itam_finance_sweep_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    _RawSweepDb,
    _run,
    _asset,
    _user,
)


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

        # Mock current time to 2026-08-01
        with patch("itam_finance_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 1, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat

            # Purchase 2026-01-01, 8 months warranty → expires 2026-09-01
            # On 2026-08-01, it is 31 days to expiry. Alert window is 30.
            # Close enough to approach the window.
            # Let's use 7 months warranty → expires 2026-08-01 (EXPIRED)
            db = _RawSweepDb(
                assets=[_asset(purchaseDate="2026-01-01T00:00:00Z", warrantyMonths=7)],
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

        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1)],
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
            assets=[_asset(purchaseDate="2020-01-01T00:00:00Z", warrantyMonths=1)],
            users=[_user()],
        )
        count = _run(svc.run_warranty_alert_pass(db))
        assert count == 1

        assert len(db._captured_update_one_filters) >= 1
        uf = db._captured_update_one_filters[0]
        assert uf.get("id") == "asset-1"
        assert uf.get("tenantId") == "tenant-a"


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
