"""ITAM-API-02 request-scoped webhook dispatch suite (Phase 73 Plan 02).

Covers the three remaining request-scoped D-05 events plan 73-01's tracer
didn't wire: `asset.checked_in` (Task 1), `consumable.low_stock` (Task 2),
and `asset.request_approved`/`asset.request_denied` (Task 3). Selectable via
`-k lifecycle`, `-k low_stock`, `-k asset_request` per the plan's own
validation contract.

Conventions (this repository, not reinvented here): backend modules are
imported by bare name (never a `backend.` prefix); FastAPI dependencies are
swapped via `app.dependency_overrides`, never module-level patching of a
`Depends`-captured callable. Task 1 reuses plan 73-01's shared lifecycle
test-app fixtures (`itam_api_integrations_test_support.py`) rather than
re-deriving them.
"""
import asyncio
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.itam_api_integrations_test_support import (
    mock_db,
    patch_lifecycle_database,
    lifecycle_app,
    _session_admin_token,
)
from api_key_auth import get_current_user_or_api_key

from itam_webhook_events import (
    EVENT_ASSET_CHECKED_IN,
    EVENT_CONSUMABLE_LOW_STOCK,
    EVENT_ASSET_REQUEST_APPROVED,
    EVENT_ASSET_REQUEST_DENIED,
)
from itam_reporting_prebuilt import DEFAULT_LOW_STOCK_QUANTITY
from errors import APIError
from itam_models import ConsumableCheckoutRequest, AssetRequestStatus
import itam_consumable_service as consumable_service_module
from itam_consumable_service import ConsumableService, _is_low_stock
from itam_asset_request_service import ItamAssetRequestService
from database import TenantIsolatedDatabase


def _authorized(app):
    """Session-authenticated admin, mirroring the shared support module's
    _session_admin_token shape — overrides get_current_user_or_api_key
    since _require_itam_admin now resolves through that dependency (73-01)."""
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _session_admin_token()
    return app


def _deployed_asset(**overrides):
    """Pre-image for checkin: an asset already checked out to a user."""
    doc = {
        "id": "asset-1",
        "tenantId": "tenant-a",
        "lifecycleStatus": "deployed",
        "name": "Laptop X1",
        "assignedToType": "user",
        "assignedToId": "user-7",
        "checkedOutAt": "2026-08-01T00:00:00.000+00:00",
        "checkedOutBy": "admin@example.com",
    }
    doc.update(overrides)
    return doc


# ─── Task 1: asset.checked_in dispatch ─────────────────────────────────────

class TestLifecycleCheckinWebhook:
    @pytest.mark.asyncio
    async def test_lifecycle_checkin_dispatches_checked_in_event(self, mock_db, lifecycle_app):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset())
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="hist-2"))

        _authorized(lifecycle_app)
        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            transport = ASGITransport(app=lifecycle_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
                r = await ac.post("/api/assets/asset-1/checkin", json={})
            for _ in range(5):
                await asyncio.sleep(0)

        assert r.status_code == 200, r.text
        recorder.assert_awaited_once()
        args, _kwargs = recorder.call_args
        assert args[0] == EVENT_ASSET_CHECKED_IN

    @pytest.mark.asyncio
    async def test_lifecycle_checkin_payload_has_before_after_asset_diff(self, mock_db, lifecycle_app):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset())
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="hist-2"))

        _authorized(lifecycle_app)
        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            transport = ASGITransport(app=lifecycle_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
                r = await ac.post("/api/assets/asset-1/checkin", json={})
            for _ in range(5):
                await asyncio.sleep(0)

        assert r.status_code == 200, r.text
        args, _kwargs = recorder.call_args
        payload = args[1]
        assert payload["assetId"] == "asset-1"
        assert "before" in payload and "after" in payload
        assert "asset" in payload
        assert payload["before"]["assignedToId"] != payload["after"]["assignedToId"]
        assert payload["before"]["assignedToId"] == "user-7"
        assert payload["after"]["assignedToId"] is None
        assert payload["after"]["lifecycleStatus"] == "deployable"

    @pytest.mark.asyncio
    async def test_lifecycle_checkin_not_found_dispatches_nothing(self, mock_db, lifecycle_app):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=None)
        mock_db.assets.find_one = AsyncMock(return_value=None)

        _authorized(lifecycle_app)
        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            transport = ASGITransport(app=lifecycle_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
                r = await ac.post("/api/assets/asset-1/checkin", json={})
            for _ in range(5):
                await asyncio.sleep(0)

        assert r.status_code == 404
        recorder.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_lifecycle_checkin_not_deployed_dispatches_nothing(self, mock_db, lifecycle_app):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=None)
        mock_db.assets.find_one = AsyncMock(return_value={"id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployable"})

        _authorized(lifecycle_app)
        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            transport = ASGITransport(app=lifecycle_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
                r = await ac.post("/api/assets/asset-1/checkin", json={})
            for _ in range(5):
                await asyncio.sleep(0)

        assert r.status_code == 409
        recorder.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_lifecycle_checkin_dispatch_is_not_awaited_inline(self, mock_db, lifecycle_app):
        """The HTTP response completes even though the dispatch coroutine is
        deliberately stalled forever (until the gate is released after the
        assertion) — proving asyncio.create_task never blocks the response."""
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset())
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="hist-2"))

        gate = asyncio.Event()

        async def _slow_trigger(event_type, payload):
            await gate.wait()

        _authorized(lifecycle_app)
        with patch("webhook_service.WebhookService.trigger_webhook", side_effect=_slow_trigger):
            transport = ASGITransport(app=lifecycle_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
                r = await asyncio.wait_for(ac.post("/api/assets/asset-1/checkin", json={}), timeout=2)
            assert r.status_code == 200, r.text
            gate.set()
            # let the now-unblocked dispatch task actually finish so the
            # event loop doesn't warn about a pending task at teardown.
            for _ in range(5):
                await asyncio.sleep(0)


# ─── Task 2: consumable.low_stock dispatch ─────────────────────────────────

@pytest.fixture
def consumable_service(monkeypatch):
    """ConsumableService with a fully mocked itam_consumables collection —
    ConsumableService.__init__ resolves its db via module-level
    get_database(), so that's what gets patched here."""
    monkeypatch.setattr(consumable_service_module, "get_database", lambda: MagicMock())
    svc = ConsumableService()
    svc.db = MagicMock()
    svc.db.itam_consumables = MagicMock()
    return svc


class TestIsLowStockHelper:
    """Pure-function coverage of the exact threshold rule
    itam_reporting_prebuilt.py's low_stock_consumables report applies."""

    def test_low_stock_above_configured_threshold_not_low(self):
        assert _is_low_stock(10, 5) is False

    def test_low_stock_equal_to_configured_threshold_is_low(self):
        assert _is_low_stock(5, 5) is True

    def test_low_stock_below_configured_threshold_is_low(self):
        assert _is_low_stock(3, 5) is True

    def test_low_stock_zero_configured_threshold_honoured(self):
        # An explicitly configured 0 must be honoured, not treated as unset.
        assert _is_low_stock(0, 0) is True
        assert _is_low_stock(1, 0) is False

    def test_low_stock_no_threshold_uses_shared_default(self):
        assert _is_low_stock(DEFAULT_LOW_STOCK_QUANTITY, None) is True
        assert _is_low_stock(DEFAULT_LOW_STOCK_QUANTITY + 1, None) is False


class TestConsumableCheckoutLowStockDispatch:
    @pytest.mark.asyncio
    async def test_low_stock_checkout_crossing_configured_threshold_dispatches_event(self, consumable_service):
        consumable_service.db.itam_consumables.find_one_and_update = AsyncMock(return_value={
            "_id": "con-1", "name": "Toner Cartridge", "availableQuantity": 2, "reorderThreshold": 5,
            "tenantId": "tenant-a", "unitType": "unit", "initialQuantity": 10, "checkoutRecords": [],
        })
        req = ConsumableCheckoutRequest(quantity=1, assignedTo="user-1", assignedToType="user")

        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            await consumable_service.checkout_consumable("con-1", req, current_user=None)
            for _ in range(5):
                await asyncio.sleep(0)

        recorder.assert_awaited_once()
        args, _kwargs = recorder.call_args
        assert args[0] == EVENT_CONSUMABLE_LOW_STOCK
        payload = args[1]
        assert payload["consumableId"] == "con-1"
        assert payload["name"] == "Toner Cartridge"
        assert payload["availableQuantity"] == 2
        assert payload["reorderThreshold"] == 5

    @pytest.mark.asyncio
    async def test_low_stock_checkout_not_crossing_threshold_dispatches_nothing(self, consumable_service):
        consumable_service.db.itam_consumables.find_one_and_update = AsyncMock(return_value={
            "_id": "con-1", "name": "Toner Cartridge", "availableQuantity": 8, "reorderThreshold": 5,
            "tenantId": "tenant-a", "unitType": "unit", "initialQuantity": 10, "checkoutRecords": [],
        })
        req = ConsumableCheckoutRequest(quantity=1, assignedTo="user-1", assignedToType="user")

        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            await consumable_service.checkout_consumable("con-1", req, current_user=None)
            for _ in range(5):
                await asyncio.sleep(0)

        recorder.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_low_stock_checkout_no_configured_threshold_uses_default_and_dispatches(self, consumable_service):
        consumable_service.db.itam_consumables.find_one_and_update = AsyncMock(return_value={
            "_id": "con-1", "name": "Toner Cartridge", "availableQuantity": DEFAULT_LOW_STOCK_QUANTITY,
            "tenantId": "tenant-a", "unitType": "unit", "initialQuantity": 10, "checkoutRecords": [],
        })
        req = ConsumableCheckoutRequest(quantity=1, assignedTo="user-1", assignedToType="user")

        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            await consumable_service.checkout_consumable("con-1", req, current_user=None)
            for _ in range(5):
                await asyncio.sleep(0)

        recorder.assert_awaited_once()
        args, _kwargs = recorder.call_args
        assert args[1]["reorderThreshold"] == DEFAULT_LOW_STOCK_QUANTITY

    @pytest.mark.asyncio
    async def test_low_stock_checkout_insufficient_quantity_dispatches_nothing(self, consumable_service):
        consumable_service.db.itam_consumables.find_one_and_update = AsyncMock(return_value=None)
        consumable_service.db.itam_consumables.find_one = AsyncMock(
            return_value={"_id": "con-1", "availableQuantity": 1}
        )
        req = ConsumableCheckoutRequest(quantity=5, assignedTo="user-1", assignedToType="user")

        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            with pytest.raises(APIError):
                await consumable_service.checkout_consumable("con-1", req, current_user=None)
            for _ in range(5):
                await asyncio.sleep(0)

        recorder.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_low_stock_checkout_consumable_not_found_dispatches_nothing(self, consumable_service):
        consumable_service.db.itam_consumables.find_one_and_update = AsyncMock(return_value=None)
        consumable_service.db.itam_consumables.find_one = AsyncMock(return_value=None)
        req = ConsumableCheckoutRequest(quantity=1, assignedTo="user-1", assignedToType="user")

        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            with pytest.raises(APIError):
                await consumable_service.checkout_consumable("con-1", req, current_user=None)
            for _ in range(5):
                await asyncio.sleep(0)

        recorder.assert_not_awaited()


# ─── Task 3: asset.request_approved / asset.request_denied dispatch ───────

MOCK_TENANT_ID = "tenant-a"
MOCK_REQUEST_ID = "ar-12345678"
MOCK_APPROVER_ID = "approver@example.com"


def _asset_request_doc(**overrides):
    doc = {
        "_id": MOCK_REQUEST_ID,
        "id": MOCK_REQUEST_ID,
        "tenant_id": MOCK_TENANT_ID,
        "requester_id": "requester@example.com",
        "item_description": "New Monitor",
        "quantity": 1,
        "reason": "Replacement for broken unit",
        "status": AssetRequestStatus.PENDING,
        "request_date": datetime.now(timezone.utc),
        "approval_date": None,
        "approver_id": None,
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def asset_request_service():
    db_instance = AsyncMock(spec=TenantIsolatedDatabase)
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock()
    mock_collection.find_one = AsyncMock()
    mock_collection.find_one_and_update = AsyncMock()
    mock_collection.find = MagicMock()
    db_instance.asset_requests = mock_collection

    with patch("itam_asset_request_service.ApprovalService") as MockApproval, \
         patch("itam_asset_request_service.ItamNotificationService") as MockNotify:
        MockApproval.return_value = AsyncMock()
        MockNotify.return_value = AsyncMock()
        yield ItamAssetRequestService(db_instance)


class TestAssetRequestWebhookDispatch:
    @pytest.mark.asyncio
    async def test_asset_request_approve_dispatches_approved_event(self, asset_request_service):
        asset_request_service.db.asset_requests.find_one.return_value = _asset_request_doc(
            status=AssetRequestStatus.PENDING
        )
        asset_request_service.db.asset_requests.find_one_and_update.return_value = _asset_request_doc(
            status=AssetRequestStatus.APPROVED, approver_id=MOCK_APPROVER_ID,
            approval_date=datetime.now(timezone.utc),
        )

        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            approved = await asset_request_service.approve_asset_request(
                MOCK_TENANT_ID, MOCK_REQUEST_ID, MOCK_APPROVER_ID
            )
            for _ in range(5):
                await asyncio.sleep(0)

        assert approved is not None
        recorder.assert_awaited_once()
        args, _kwargs = recorder.call_args
        assert args[0] == EVENT_ASSET_REQUEST_APPROVED
        payload = args[1]
        assert payload["requestId"] == MOCK_REQUEST_ID
        assert payload["status"] == AssetRequestStatus.APPROVED
        assert payload["approver_id"] == MOCK_APPROVER_ID
        asset_request_service.notification_service.send_asset_request_notification.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_asset_request_reject_dispatches_denied_event(self, asset_request_service):
        asset_request_service.db.asset_requests.find_one.return_value = _asset_request_doc(
            status=AssetRequestStatus.PENDING
        )
        asset_request_service.db.asset_requests.find_one_and_update.return_value = _asset_request_doc(
            status=AssetRequestStatus.REJECTED, approver_id=MOCK_APPROVER_ID,
            approval_date=datetime.now(timezone.utc),
        )

        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            rejected = await asset_request_service.reject_asset_request(
                MOCK_TENANT_ID, MOCK_REQUEST_ID, MOCK_APPROVER_ID
            )
            for _ in range(5):
                await asyncio.sleep(0)

        assert rejected is not None
        recorder.assert_awaited_once()
        args, _kwargs = recorder.call_args
        # Deliberate asymmetry: internal status is "rejected", the fixed
        # outward event name is "asset.request_denied" (D-05).
        assert args[0] == EVENT_ASSET_REQUEST_DENIED
        payload = args[1]
        assert payload["requestId"] == MOCK_REQUEST_ID
        assert payload["status"] == AssetRequestStatus.REJECTED
        asset_request_service.notification_service.send_asset_request_notification.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_asset_request_approve_non_pending_dispatches_nothing(self, asset_request_service):
        asset_request_service.db.asset_requests.find_one.return_value = _asset_request_doc(
            status=AssetRequestStatus.APPROVED
        )

        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            approved = await asset_request_service.approve_asset_request(
                MOCK_TENANT_ID, MOCK_REQUEST_ID, MOCK_APPROVER_ID
            )
            for _ in range(5):
                await asyncio.sleep(0)

        assert approved is None
        recorder.assert_not_awaited()
        asset_request_service.db.asset_requests.find_one_and_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_asset_request_reject_non_pending_dispatches_nothing(self, asset_request_service):
        asset_request_service.db.asset_requests.find_one.return_value = _asset_request_doc(
            status=AssetRequestStatus.REJECTED
        )

        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            rejected = await asset_request_service.reject_asset_request(
                MOCK_TENANT_ID, MOCK_REQUEST_ID, MOCK_APPROVER_ID
            )
            for _ in range(5):
                await asyncio.sleep(0)

        assert rejected is None
        recorder.assert_not_awaited()
        asset_request_service.db.asset_requests.find_one_and_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_asset_request_approve_dispatch_never_blocks_return(self, asset_request_service):
        """A stalled dispatch coroutine (gated forever until after the
        assertion) never prevents approve_asset_request from returning —
        proving asyncio.create_task, not an inline await, is used."""
        asset_request_service.db.asset_requests.find_one.return_value = _asset_request_doc(
            status=AssetRequestStatus.PENDING
        )
        asset_request_service.db.asset_requests.find_one_and_update.return_value = _asset_request_doc(
            status=AssetRequestStatus.APPROVED, approver_id=MOCK_APPROVER_ID,
        )

        gate = asyncio.Event()

        async def _slow_trigger(event_type, payload):
            await gate.wait()

        with patch("webhook_service.WebhookService.trigger_webhook", side_effect=_slow_trigger):
            approved = await asyncio.wait_for(
                asset_request_service.approve_asset_request(MOCK_TENANT_ID, MOCK_REQUEST_ID, MOCK_APPROVER_ID),
                timeout=2,
            )
        assert approved is not None
        gate.set()
        for _ in range(5):
            await asyncio.sleep(0)


# ─── Task 1 (Plan 73-03): asset.warranty_expiring background-sweep dispatch ─

import itam_finance_service as finance_service_module
from itam_webhook_events import EVENT_ASSET_WARRANTY_EXPIRING
from tenant_context import get_tenant_id
from tests.itam_finance_sweep_test_support import _RawSweepDb, _asset, _user


def _expiring_asset(**overrides):
    """Purchased 2026-01-01, 8-month warranty -> expires 2026-09-01. Against
    a mocked "now" of 2026-08-15 that is 17 days out: inside the default
    30-day alert window and not yet past expiry, so this is genuinely the
    EXPIRING branch, not EXPIRED."""
    return _asset(purchaseDate="2026-01-01T00:00:00Z", warrantyMonths=8, **overrides)


def _mock_now_2026_08_15():
    return patch("itam_finance_service.datetime", **{
        "now.return_value": datetime(2026, 8, 15, tzinfo=timezone.utc),
        "fromisoformat.side_effect": datetime.fromisoformat,
    })


class TestWarrantyExpiringWebhookDispatch:
    @pytest.mark.asyncio
    async def test_warranty_expiring_dispatches_event_once_for_expiring_asset(self):
        db = _RawSweepDb(assets=[_expiring_asset()], users=[_user()])
        recorder = AsyncMock()
        with _mock_now_2026_08_15(), \
             patch("webhook_service.WebhookService.trigger_webhook", recorder):
            count = await finance_service_module.run_warranty_alert_pass(db)

        assert count == 1
        recorder.assert_awaited_once()
        args, _kwargs = recorder.call_args
        assert args[0] == EVENT_ASSET_WARRANTY_EXPIRING

    @pytest.mark.asyncio
    async def test_warranty_expiring_dispatch_uses_asset_tenant_as_ambient_context(self):
        """The load-bearing regression: this fails if the tenant bracketing
        around the webhook dispatch is ever removed, since get_tenant_id()
        would then read None instead of the swept asset's own tenant id."""
        captured_tenant_ids = []

        async def _recording_trigger(event_type, payload):
            captured_tenant_ids.append(get_tenant_id())

        db = _RawSweepDb(
            assets=[_expiring_asset(tenantId="tenant-xyz")],
            users=[_user(tenantId="tenant-xyz")],
        )
        with _mock_now_2026_08_15(), \
             patch("webhook_service.WebhookService.trigger_webhook", side_effect=_recording_trigger):
            await finance_service_module.run_warranty_alert_pass(db)

        assert captured_tenant_ids == ["tenant-xyz"]

    @pytest.mark.asyncio
    async def test_warranty_expiring_tenant_context_restored_after_dispatch_raises(self):
        assert get_tenant_id() is None  # sanity: no ambient tenant before the sweep runs

        async def _raising_trigger(event_type, payload):
            raise RuntimeError("subscriber unreachable")

        db = _RawSweepDb(assets=[_expiring_asset()], users=[_user()])
        with _mock_now_2026_08_15(), \
             patch("webhook_service.WebhookService.trigger_webhook", side_effect=_raising_trigger):
            await finance_service_module.run_warranty_alert_pass(db)

        assert get_tenant_id() is None

    @pytest.mark.asyncio
    async def test_warranty_expiring_marker_and_existing_paths_still_occur_when_webhook_raises(self):
        async def _raising_trigger(event_type, payload):
            raise RuntimeError("subscriber unreachable")

        db = _RawSweepDb(assets=[_expiring_asset()], users=[_user()])
        with patch.object(finance_service_module, "get_notification_service") as mock_get_ns, \
             patch.object(finance_service_module, "send_notification") as mock_send, \
             _mock_now_2026_08_15():
            mock_ns = MagicMock()
            mock_ns.send_alert = AsyncMock()
            mock_get_ns.return_value = mock_ns
            mock_send.return_value = {"matched_rules": 0, "sent": 0}
            with patch("webhook_service.WebhookService.trigger_webhook", side_effect=_raising_trigger):
                count = await finance_service_module.run_warranty_alert_pass(db)

        assert count == 1
        assert mock_ns.send_alert.await_count >= 1
        mock_send.assert_awaited()
        assert db._docs["assets"]["asset-1"].get("warrantyAlertSentAt") is not None

    @pytest.mark.asyncio
    async def test_warranty_expiring_active_asset_dispatches_nothing(self):
        db = _RawSweepDb(
            assets=[_asset(purchaseDate="2026-01-01T00:00:00Z", warrantyMonths=36)],
            users=[_user()],
        )
        recorder = AsyncMock()
        with _mock_now_2026_08_15(), \
             patch("webhook_service.WebhookService.trigger_webhook", recorder):
            count = await finance_service_module.run_warranty_alert_pass(db)

        assert count == 0
        recorder.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_warranty_expiring_already_marked_asset_dispatches_nothing(self):
        db = _RawSweepDb(
            assets=[_expiring_asset(warrantyAlertSentAt="2026-08-01T00:00:00+00:00")],
            users=[_user()],
        )
        recorder = AsyncMock()
        with _mock_now_2026_08_15(), \
             patch("webhook_service.WebhookService.trigger_webhook", recorder):
            count = await finance_service_module.run_warranty_alert_pass(db)

        assert count == 0
        recorder.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_warranty_expiring_payload_shape(self):
        db = _RawSweepDb(assets=[_expiring_asset(assetTag="TAG-42")], users=[_user()])
        recorder = AsyncMock()
        with _mock_now_2026_08_15(), \
             patch("webhook_service.WebhookService.trigger_webhook", recorder):
            await finance_service_module.run_warranty_alert_pass(db)

        args, _kwargs = recorder.call_args
        payload = args[1]
        assert set(payload.keys()) == {"assetId", "assetTag", "warrantyStatus", "warrantyExpiresAt"}
        assert payload["assetId"] == "asset-1"
        assert payload["assetTag"] == "TAG-42"
