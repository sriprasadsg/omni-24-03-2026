"""ITAM Lifecycle tests — Phase 57 Plan 01/02/03 (check-out, check-in, audit)."""
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_test_app, make_token_data, _make_col

from authentication_service import get_current_user as real_get_current_user


# ---------------------------------------------------------------------------
# Fixture set copied from test_itam_foundation.py (no equivalent lives in
# conftest.py) and adapted: assets/users/locations/assignment_history built
# with _make_col(); itam_lifecycle_endpoints.get_database / .invalidate_cache
# patched; itam_asset_endpoints.verify_permission patched (the RBAC dependency
# this router uses is imported from that module).
# ---------------------------------------------------------------------------
class MockTenantIsolatedCollection:
    def __init__(self, collection_name, tenant_id, raw_collection_mock):
        self._collection_name = collection_name
        self._tenant_id = tenant_id
        self._raw_collection = raw_collection_mock

        async def _find_one(f, *args, **kwargs):
            return await raw_collection_mock.find_one({**(f or {}), "tenantId": self._tenant_id}, *args, **kwargs)

        async def _insert_one(doc, *args, **kwargs):
            return await raw_collection_mock.insert_one({**doc, "tenantId": self._tenant_id}, *args, **kwargs)

        async def _count_documents(f, *args, **kwargs):
            return await raw_collection_mock.count_documents({**(f or {}), "tenantId": self._tenant_id}, *args, **kwargs)

        async def _find_one_and_update(f, u, *args, **kwargs):
            return await raw_collection_mock.find_one_and_update({**(f or {}), "tenantId": self._tenant_id}, u, *args, **kwargs)

        async def _delete_one(f, *args, **kwargs):
            return await raw_collection_mock.delete_one({**(f or {}), "tenantId": self._tenant_id}, *args, **kwargs)

        self.find_one = _find_one
        self.insert_one = _insert_one
        self.count_documents = _count_documents
        self.find_one_and_update = _find_one_and_update
        self.delete_one = _delete_one
        self.find = MagicMock(side_effect=lambda f=None, *args, **kwargs:
                              raw_collection_mock.find({**(f if f else {}), "tenantId": self._tenant_id}, *args, **kwargs))


class MockTenantIsolatedDatabase:
    def __init__(self, raw_db_mock, tenant_id):
        self._raw_db = raw_db_mock
        self._tenant_id = tenant_id

    def __getattr__(self, name):
        return MockTenantIsolatedCollection(name, self._tenant_id, getattr(self._raw_db, name))

    def __getitem__(self, name):
        return self.__getattr__(name)


@pytest.fixture
def mock_db():
    """Mock database carrying every collection the lifecycle router touches, plus the
    catalog collections Task 3's real-cache-invalidation test drives through
    itam_asset_endpoints.create_manual_asset (counters/manufacturers/asset_models)."""
    db = MagicMock()
    for name in (
        "assets", "users", "locations", "assignment_history",
        "counters", "manufacturers", "asset_models",
    ):
        setattr(db, name, _make_col())
    # find_one_and_update is not part of _make_col()'s default surface — the
    # lifecycle router's guarded transition needs it explicitly present.
    db.assets.find_one_and_update = AsyncMock(return_value=None)
    return db


@pytest.fixture(autouse=True)
def patch_get_database_globally(mock_db, monkeypatch):
    """Patch get_database at itam_lifecycle_endpoints' own bound name (name-binding
    import — patching database.get_database alone would not affect it)."""
    import itam_lifecycle_endpoints
    _current_tenant_id = "tenant-a"

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(itam_lifecycle_endpoints, "get_database", get_mock_tenant_db)

    _patch_all()

    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def lifecycle_app(mock_db, patch_get_database_globally, monkeypatch):
    """Test FastAPI app mounting only itam_lifecycle_endpoints.router."""
    import itam_lifecycle_endpoints
    import itam_asset_endpoints

    # The RBAC dependency this router uses (_require_itam_admin) is imported from
    # itam_asset_endpoints, so verify_permission must be patched at that module's
    # own bound name.
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))
    # invalidate_cache is a synchronous def in the real module — a plain MagicMock
    # (not AsyncMock) proves the lifecycle path never awaits it.
    monkeypatch.setattr(itam_lifecycle_endpoints, "invalidate_cache", MagicMock())

    app, _ = make_test_app(itam_lifecycle_endpoints.router)
    return app


def _deployable_asset(**overrides):
    doc = {
        "id": "asset-1",
        "tenantId": "tenant-a",
        "lifecycleStatus": "deployable",
        "name": "Laptop X1",
    }
    doc.update(overrides)
    return doc


def _deployed_asset_after_checkout(**overrides):
    doc = {
        "id": "asset-1",
        "tenantId": "tenant-a",
        "lifecycleStatus": "deployed",
        "assignedToType": "user",
        "assignedToId": "user-7",
        "checkedOutAt": "2026-08-04T00:00:00.000+00:00",
        "checkedOutBy": "admin@example.com",
        "updatedAt": "2026-08-04T00:00:00.000+00:00",
        "_id": "mongo-oid-1",
    }
    doc.update(overrides)
    return doc


# ---------------------------------------------------------------------------
# Task 1 — end-to-end "check an asset out to a user", one path only.
# ---------------------------------------------------------------------------
class TestCheckoutToUser:

    @pytest.mark.asyncio
    async def test_checkout_to_user_end_to_end(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset_after_checkout())
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
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset_after_checkout())
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
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset_after_checkout())
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
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset_after_checkout())
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
            return_value=_deployed_asset_after_checkout(expectedReturnDate="2026-09-01")
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


# ---------------------------------------------------------------------------
# Task 2 — location targets, every refusal path, and the concurrency guarantee.
# ---------------------------------------------------------------------------
class TestCheckoutExpansion:

    @pytest.mark.asyncio
    async def test_checkout_to_location_overwrites_location_id(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset_after_checkout(
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
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset_after_checkout())
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
        find_one_and_update_mock = AsyncMock(return_value=_deployed_asset_after_checkout())
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
        find_one_and_update_mock = AsyncMock(return_value=_deployed_asset_after_checkout())
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
        mock_db.assets.find_one = AsyncMock(return_value=_deployable_asset(lifecycleStatus="deployed"))
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

        state = {"asset": _deployable_asset()}

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
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset_after_checkout())
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
        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset_after_checkout())
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        mock_db.assignment_history.insert_one = AsyncMock(side_effect=RuntimeError("db down"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/checkout", json={"targetType": "user", "targetId": "user-7"})

        assert r.status_code == 500, r.text


# ---------------------------------------------------------------------------
# Task 3 — Phase-57 indexes and the cache-invalidation defect repair.
# ---------------------------------------------------------------------------
class TestCacheInvalidationRepair:

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

        mock_db.assets.find_one_and_update = AsyncMock(return_value=_deployed_asset_after_checkout())
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
