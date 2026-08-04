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
    """Mock database carrying every collection the lifecycle router touches."""
    db = MagicMock()
    for name in ("assets", "users", "locations", "assignment_history"):
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
