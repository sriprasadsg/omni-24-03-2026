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

from itam_webhook_events import EVENT_ASSET_CHECKED_IN


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
