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

from itam_webhook_events import EVENT_ASSET_CHECKED_IN, EVENT_CONSUMABLE_LOW_STOCK
from itam_reporting_prebuilt import DEFAULT_LOW_STOCK_QUANTITY
from errors import APIError
from itam_models import ConsumableCheckoutRequest
import itam_consumable_service as consumable_service_module
from itam_consumable_service import ConsumableService, _is_low_stock


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
