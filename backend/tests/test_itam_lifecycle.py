"""ITAM Lifecycle tests — Phase 57 Plan 01, Task 1: check-out-to-user end-to-end.

Shared mock DB/fixtures live in itam_lifecycle_test_support.py (split out to keep
every file under the CLAUDE.md 500-line limit). Task 2's location/refusal/
concurrency coverage and Task 3's cache-invalidation coverage live in
test_itam_lifecycle_expansion.py.
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_token_data
from tests.itam_lifecycle_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    mock_db,
    patch_get_database_globally,
    lifecycle_app,
    deployed_asset_after_checkout,
)

from authentication_service import get_current_user as real_get_current_user


class TestCheckoutToUser:
    """Task 1 — end-to-end 'check an asset out to a user', one path only."""

    @pytest.mark.asyncio
    async def test_checkout_to_user_end_to_end(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=deployed_asset_after_checkout())
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7", "email": "u7@x.com", "name": "User Seven"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["lifecycleStatus"] == "deployed"
        assert data["assignedToType"] == "user"
        assert data["assignedToId"] == "user-7"
        assert "_id" not in data
        assert "history" in data
        assert data["history"]["action"] == "checkout"
        assert data["history"]["targetId"] == "user-7"

    @pytest.mark.asyncio
    async def test_checkout_writes_exactly_one_history_entry(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=deployed_asset_after_checkout())
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 200, r.text
        assert mock_db.assignment_history.insert_one.await_count == 1
        inserted_doc = mock_db.assignment_history.insert_one.call_args[0][0]
        assert inserted_doc["assetId"] == "asset-1"
        assert inserted_doc["action"] == "checkout"
        assert inserted_doc["targetType"] == "user"
        assert inserted_doc["targetId"] == "user-7"
        assert inserted_doc["actorUsername"] == "admin@example.com"
        assert "ts" in inserted_doc

    @pytest.mark.asyncio
    async def test_checkout_history_entry_stores_reference_not_personal_data(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=deployed_asset_after_checkout())
        mock_db.users.find_one = AsyncMock(return_value={
            "id": "user-7", "email": "secret@example.com", "name": "Secret Person",
        })
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 200, r.text
        inserted_doc = mock_db.assignment_history.insert_one.call_args[0][0]
        serialized = str(inserted_doc)
        assert "secret@example.com" not in serialized
        assert "Secret Person" not in serialized

    @pytest.mark.asyncio
    async def test_checkout_guard_is_in_the_update_filter(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=deployed_asset_after_checkout())
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 200, r.text
        filt = mock_db.assets.find_one_and_update.call_args[0][0]
        assert "$or" in filt
        assert any("lifecycleStatus" in clause for clause in filt["$or"])
        # No separate read-then-write pair on the success path.
        assert mock_db.assets.find_one.await_count == 0

    @pytest.mark.asyncio
    async def test_checkout_captures_note_and_expected_return_date(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(
            return_value=deployed_asset_after_checkout(expectedReturnDate="2026-09-01")
        )
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={
                "targetType": "user",
                "targetId": "user-7",
                "note": "Loaned for conference",
                "expectedReturnDate": "2026-09-01",
            })

        assert r.status_code == 200, r.text
        update = mock_db.assets.find_one_and_update.call_args[0][1]
        assert update["$set"]["expectedReturnDate"] == "2026-09-01"
        inserted_doc = mock_db.assignment_history.insert_one.call_args[0][0]
        assert inserted_doc["note"] == "Loaned for conference"
        assert inserted_doc["expectedReturnDate"] == "2026-09-01"

    @pytest.mark.asyncio
    async def test_checkout_rejects_unknown_field(self, mock_db, lifecycle_app, patch_get_database_globally):
        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={
                "targetType": "user",
                "targetId": "user-7",
                "bogusField": True,
            })

        assert r.status_code == 422, r.text


class TestCheckinAsset:
    """Plan 57-02, Task 1 — check an asset back in, returning it to stock and
    clearing its assignment (ITAM-LIFE-03)."""

    @pytest.mark.asyncio
    async def test_checkin_returns_asset_to_stock(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={
            "id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployable",
            "locationId": "loc-1", "_id": "mongo-oid-1",
        })
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkin", json={})

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["lifecycleStatus"] == "deployable"
        assert "_id" not in data
        assert "history" in data
        assert data["history"]["action"] == "checkin"

    @pytest.mark.asyncio
    async def test_checkin_clears_assignment_fields(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={
            "id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployable",
        })
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkin", json={})

        assert r.status_code == 200, r.text
        update = mock_db.assets.find_one_and_update.call_args[0][1]
        assert set(update["$unset"].keys()) == {
            "assignedToType", "assignedToId", "checkedOutAt", "checkedOutBy", "expectedReturnDate",
        }

    @pytest.mark.asyncio
    async def test_checkin_retains_location_id(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={
            "id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployable",
        })
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkin", json={})

        assert r.status_code == 200, r.text
        update = mock_db.assets.find_one_and_update.call_args[0][1]
        assert "locationId" not in update.get("$set", {})
        assert "locationId" not in update.get("$unset", {})

    @pytest.mark.asyncio
    async def test_checkin_of_asset_not_checked_out_returns_409(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=None)
        mock_db.assets.find_one = AsyncMock(return_value={
            "id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "retired",
        })
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkin", json={})

        assert r.status_code == 409, r.text
        mock_db.assignment_history.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_checkin_of_missing_asset_returns_404(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=None)
        mock_db.assets.find_one = AsyncMock(return_value=None)

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-missing/checkin", json={})

        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_checkin_writes_one_history_entry(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={
            "id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployable",
        })
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkin", json={})

        assert r.status_code == 200, r.text
        assert mock_db.assignment_history.insert_one.await_count == 1
        inserted_doc = mock_db.assignment_history.insert_one.call_args[0][0]
        assert inserted_doc["assetId"] == "asset-1"
        assert inserted_doc["action"] == "checkin"
        assert inserted_doc["actorUsername"] == "admin@example.com"
        assert "ts" in inserted_doc
        assert "targetType" not in inserted_doc
        assert "targetId" not in inserted_doc

    @pytest.mark.asyncio
    async def test_checkin_records_optional_note(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={
            "id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployable",
        })
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkin", json={"note": "Returned in good condition"})

        assert r.status_code == 200, r.text
        inserted_doc = mock_db.assignment_history.insert_one.call_args[0][0]
        assert inserted_doc["note"] == "Returned in good condition"

    @pytest.mark.asyncio
    async def test_concurrent_checkin_only_one_succeeds(self, mock_db, lifecycle_app, patch_get_database_globally):
        """Two asyncio.gather-issued check-ins against one checked-out asset, backed by
        a fake find_one_and_update honouring the guard against real in-memory state,
        yield exactly one 200 and one 409 — never two successes."""
        import asyncio as _asyncio

        state = {"asset": {
            "id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployed",
            "assignedToType": "user", "assignedToId": "user-7",
        }}

        async def _fake_find_one_and_update(f, u, *args, **kwargs):
            asset = state["asset"]
            if asset is None or asset.get("id") != f.get("id"):
                return None
            if asset.get("lifecycleStatus") != "deployed":
                return None
            updated = dict(asset)
            updated.update(u.get("$set", {}))
            for key in u.get("$unset", {}):
                updated.pop(key, None)
            state["asset"] = updated
            return dict(updated)

        async def _fake_find_one(f, *args, **kwargs):
            asset = state["asset"]
            return dict(asset) if asset and asset.get("id") == f.get("id") else None

        mock_db.assets.find_one_and_update = AsyncMock(side_effect=_fake_find_one_and_update)
        mock_db.assets.find_one = AsyncMock(side_effect=_fake_find_one)
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r1, r2 = await _asyncio.gather(
                ac.post("/api/assets/asset-1/checkin", json={}),
                ac.post("/api/assets/asset-1/checkin", json={}),
            )

        statuses = sorted([r1.status_code, r2.status_code])
        assert statuses == [200, 409], (r1.status_code, r2.status_code)
        assert mock_db.assignment_history.insert_one.await_count == 1

    @pytest.mark.asyncio
    async def test_checkin_requires_manage_assets_permission(self, mock_db, lifecycle_app, patch_get_database_globally, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))

        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkin", json={})

        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_checkin_does_not_write_agent_liveness_field(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={
            "id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployable",
        })
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkin", json={})

        assert r.status_code == 200, r.text
        update = mock_db.assets.find_one_and_update.call_args[0][1]
        set_doc = update["$set"]
        # Agent-liveness field owned exclusively by agent_registry_endpoints.py's
        # heartbeat upsert — never written by the lifecycle check-in path.
        assert "status" not in set_doc
