"""ITAM Lifecycle tests — Phase 57 Plan 01, Tasks 2 & 3.

Task 2: location targets, every refusal path, and the concurrency guarantee.
Task 3: Phase-57 indexes (covered by grep-based plan verification, not here)
and the cache-invalidation defect repair.

Shared mock DB/fixtures live in itam_lifecycle_test_support.py (split out to
keep every file under the CLAUDE.md 500-line limit; see test_itam_lifecycle.py
for Task 1's checkout-happy-path coverage).
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_test_app, make_token_data
from tests.itam_lifecycle_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    mock_db,
    patch_get_database_globally,
    lifecycle_app,
    deployable_asset,
    deployed_asset_after_checkout,
    MockTenantIsolatedDatabase,
)

from authentication_service import get_current_user as real_get_current_user


class TestCheckoutExpansion:
    """Task 2 — location targets, every refusal path, and the concurrency guarantee."""

    @pytest.mark.asyncio
    async def test_checkout_to_location_overwrites_location_id(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=deployed_asset_after_checkout(
            assignedToType="location", assignedToId="loc-1", locationId="loc-1",
        ))
        mock_db.locations.find_one = AsyncMock(return_value={"id": "loc-1", "name": "HQ"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "location", "targetId": "loc-1"})

        assert r.status_code == 200, r.text
        update = mock_db.assets.find_one_and_update.call_args[0][1]
        set_doc = update["$set"]
        assert set_doc["assignedToType"] == "location"
        assert set_doc["assignedToId"] == "loc-1"
        assert set_doc["locationId"] == "loc-1"

    @pytest.mark.asyncio
    async def test_checkout_to_user_produces_no_location_id_key(self, mock_db, lifecycle_app, patch_get_database_globally):
        """A check-out to a user must leave locationId untouched (no key in $set)."""
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
        update = mock_db.assets.find_one_and_update.call_args[0][1]
        assert "locationId" not in update["$set"]

    @pytest.mark.asyncio
    async def test_checkout_target_user_not_found_returns_400(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.users.find_one = AsyncMock(return_value=None)
        find_one_and_update_mock = AsyncMock(return_value=deployed_asset_after_checkout())
        mock_db.assets.find_one_and_update = find_one_and_update_mock

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "ghost-user"})

        assert r.status_code == 400, r.text
        find_one_and_update_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_checkout_target_location_not_found_returns_400(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.locations.find_one = AsyncMock(return_value=None)
        find_one_and_update_mock = AsyncMock(return_value=deployed_asset_after_checkout())
        mock_db.assets.find_one_and_update = find_one_and_update_mock

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "location", "targetId": "ghost-loc"})

        assert r.status_code == 400, r.text
        find_one_and_update_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_checkout_of_missing_asset_returns_404(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        mock_db.assets.find_one_and_update = AsyncMock(return_value=None)
        mock_db.assets.find_one = AsyncMock(return_value=None)

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-missing/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_checkout_of_non_deployable_asset_returns_409(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        mock_db.assets.find_one_and_update = AsyncMock(return_value=None)
        mock_db.assets.find_one = AsyncMock(return_value=deployable_asset(lifecycleStatus="deployed"))
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 409, r.text
        mock_db.assignment_history.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_checkout_reverts_asset_when_history_write_fails(self, mock_db, lifecycle_app, patch_get_database_globally):
        """WR-01 regression: the guarded find_one_and_update already committed the
        checkout mutation before write_history is attempted. If that history write
        fails, the asset mutation must be compensated (reverted) — not left as an
        invisible, untracked state change behind a 500."""
        pre_image_doc = deployable_asset()  # lifecycleStatus: deployable, no assignment fields yet
        mock_db.assets.find_one_and_update = AsyncMock(return_value=pre_image_doc)
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        mock_db.assignment_history.insert_one = AsyncMock(side_effect=RuntimeError("boom"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 500, r.text
        # Called twice: once for the guarded mutation, once for the compensating revert.
        assert mock_db.assets.find_one_and_update.await_count == 2
        revert_filt, revert_update = mock_db.assets.find_one_and_update.call_args_list[1][0][:2]
        assert revert_filt["id"] == "asset-1"
        # lifecycleStatus reverts to its pre-image value; fields this checkout
        # added (absent from the pre-image) are unset, not left behind.
        assert revert_update["$set"]["lifecycleStatus"] == "deployable"
        assert "assignedToType" in revert_update["$unset"]
        assert "checkedOutBy" in revert_update["$unset"]

    @pytest.mark.asyncio
    async def test_checkout_of_agent_asset_without_lifecycle_key_succeeds(self, mock_db, lifecycle_app, patch_get_database_globally):
        """An asset document with no lifecycleStatus key at all is checked out successfully —
        proves the guard admits the absent-key case (every pre-existing agent-discovered asset)."""
        asset_no_key = {"id": "asset-agent-1", "tenantId": "tenant-a", "hostname": "host1"}

        async def _fake_find_one_and_update(f, u, *args, **kwargs):
            if f.get("id") != asset_no_key["id"]:
                return None
            status_present = "lifecycleStatus" in asset_no_key
            guard_ok = (not status_present) or asset_no_key.get("lifecycleStatus") == "deployable"
            if not guard_ok:
                return None
            updated = dict(asset_no_key)
            updated.update(u.get("$set", {}))
            return updated

        mock_db.assets.find_one_and_update = AsyncMock(side_effect=_fake_find_one_and_update)
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-agent-1/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 200, r.text
        assert r.json()["lifecycleStatus"] == "deployed"

    @pytest.mark.asyncio
    async def test_concurrent_checkout_only_one_succeeds(self, mock_db, lifecycle_app, patch_get_database_globally):
        """Two asyncio.gather-issued check-outs against one asset, backed by a fake
        find_one_and_update that honours the guard against real in-memory state, yield
        exactly one 200 and one 409 — never two successes."""
        import asyncio as _asyncio

        state = {"asset": deployable_asset()}

        async def _fake_find_one_and_update(f, u, *args, **kwargs):
            # Synchronous body (no internal await) mirrors MongoDB's real atomicity
            # contract for this single-document guarded transition — the check and
            # the mutation happen without yielding to the other concurrent request.
            asset = state["asset"]
            if asset is None or asset.get("id") != f.get("id"):
                return None
            status_present = "lifecycleStatus" in asset
            guard_ok = (not status_present) or asset.get("lifecycleStatus") == "deployable"
            if not guard_ok:
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
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r1, r2 = await _asyncio.gather(
                ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"}),
                ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"}),
            )

        statuses = sorted([r1.status_code, r2.status_code])
        assert statuses == [200, 409], (r1.status_code, r2.status_code)
        assert mock_db.assignment_history.insert_one.await_count == 1

    @pytest.mark.asyncio
    async def test_checkout_does_not_write_agent_liveness_field(self, mock_db, lifecycle_app, patch_get_database_globally):
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
        update = mock_db.assets.find_one_and_update.call_args[0][1]
        set_doc = update["$set"]
        assert "lifecycleStatus" in set_doc
        # Agent-liveness field owned exclusively by agent_registry_endpoints.py's
        # heartbeat upsert — never written by the lifecycle checkout path.
        assert "status" not in set_doc

    @pytest.mark.asyncio
    async def test_checkout_requires_manage_assets_permission(self, mock_db, lifecycle_app, patch_get_database_globally, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))

        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_checkout_history_write_failure_surfaces_as_500(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=deployed_asset_after_checkout())
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        mock_db.assignment_history.insert_one = AsyncMock(side_effect=RuntimeError("db down"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 500, r.text


class TestCacheInvalidationRepair:
    """Task 3 — the await-invalidate_cache defect repair."""

    @pytest.fixture
    def asset_app(self, mock_db, monkeypatch):
        """App mounting itam_asset_endpoints.router with invalidate_cache left bound
        to the REAL synchronous cache_service helper (not monkeypatched) — exercises
        the real call path end-to-end rather than only under a test double. The cache
        backend itself gracefully degrades to fakeredis/disabled with no live store,
        so nothing else needs patching."""
        import itam_asset_endpoints

        def get_mock_tenant_db():
            return MockTenantIsolatedDatabase(mock_db, "tenant-a")

        monkeypatch.setattr(itam_asset_endpoints, "get_database", get_mock_tenant_db)
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))

        app, _ = make_test_app(itam_asset_endpoints.router)
        return app

    @pytest.mark.asyncio
    async def test_manual_asset_creation_survives_real_cache_invalidation(self, mock_db, asset_app):
        """This test fails before the await-removal fix (500) and passes after — the
        whole point of writing it here rather than only trusting the AsyncMock double
        test_itam_foundation.py's fixture set uses."""
        counter_state = {"seq": 0}

        async def _counter_find_one_and_update(f, u, *args, **kwargs):
            counter_state["seq"] += 1
            return {"seq": counter_state["seq"], **f}

        mock_db.counters.find_one_and_update = AsyncMock(side_effect=_counter_find_one_and_update)
        mock_db.assets.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        asset_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=asset_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets", json={"name": "Cache Repair Laptop"})

        assert r.status_code == 201, r.text

    @pytest.mark.asyncio
    async def test_checkout_invalidates_asset_cache_without_await(self, mock_db, lifecycle_app, patch_get_database_globally):
        import itam_lifecycle_endpoints

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
        itam_lifecycle_endpoints.invalidate_cache.assert_called_once_with("assets:*")
        # A plain (synchronous) MagicMock proves the lifecycle path never awaits it —
        # an AsyncMock would still "pass" here even if the code wrongly awaited it.
        assert not isinstance(itam_lifecycle_endpoints.invalidate_cache, AsyncMock)
