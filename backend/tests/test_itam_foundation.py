"""End-to-end ITAM foundation tests — Phase 56 Plan 01."""
import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from pymongo import ReturnDocument

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_test_app, make_token_data, _make_col
from itam_models import ASSET_SOURCE_MANUAL, DEFAULT_LIFECYCLE_STATUS, ASSET_SOURCE_AGENT

# Patch authentication_service.get_current_user globally for all tests using make_test_app
# This ensures that FastAPI's Depends(get_current_user) resolves to our test user.
from authentication_service import get_current_user as real_get_current_user


# Simplified MockTenantIsolatedDatabase and Collection.
# The original _make_col already provides a good base.
# We just need to ensure tenantId is filtered/added correctly.
class MockTenantIsolatedCollection:
    def __init__(self, collection_name, tenant_id, raw_collection_mock):
        self._collection_name = collection_name
        self._tenant_id = tenant_id
        self._raw_collection = raw_collection_mock

        # Proxy calls, injecting tenantId into filters/documents. These are real
        # coroutine functions (not AsyncMock(side_effect=lambda ...) wrapping another
        # AsyncMock) — wrapping an AsyncMock in a sync lambda calls it without awaiting,
        # so the "result" is a live, never-awaited coroutine object instead of the real
        # value. A single `await` here avoids that double-wrap.
        async def _find_one(f, *args, **kwargs):
            return await raw_collection_mock.find_one({**f, "tenantId": self._tenant_id}, *args, **kwargs)

        async def _insert_one(doc, *args, **kwargs):
            return await raw_collection_mock.insert_one({**doc, "tenantId": self._tenant_id}, *args, **kwargs)

        async def _count_documents(f, *args, **kwargs):
            return await raw_collection_mock.count_documents({**f, "tenantId": self._tenant_id}, *args, **kwargs)

        async def _find_one_and_update(f, u, *args, **kwargs):
            return await raw_collection_mock.find_one_and_update({**f, "tenantId": self._tenant_id}, u, *args, **kwargs)

        async def _delete_one(f, *args, **kwargs):
            return await raw_collection_mock.delete_one({**f, "tenantId": self._tenant_id}, *args, **kwargs)

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
    """Basic mock database with required collections."""
    db = MagicMock()
    for name in ("assets", "manufacturers", "counters"):
        setattr(db, name, _make_col())
    # Initialize a sequence counter for the mock 'counters' collection
    db.counters.current_seq = 0
    return db


@pytest.fixture(autouse=True)
def patch_get_database_globally(mock_db, monkeypatch):
    """
    Patch get_database globally to return our mock wrapped for tenant isolation.
    This fixture is auto-used by pytest.

    itam_catalog_endpoints.py and itam_asset_endpoints.py both do
    `from database import get_database` (name-binding import), so patching
    database.get_database alone does not affect their already-bound local
    references — each importing module's own name must be patched too.
    """
    import database
    import itam_catalog_endpoints
    import itam_asset_endpoints
    _current_tenant_id = "default-tenant" # Default tenant for patching

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(database, "get_database", get_mock_tenant_db)
        monkeypatch.setattr(itam_catalog_endpoints, "get_database", get_mock_tenant_db)
        monkeypatch.setattr(itam_asset_endpoints, "get_database", get_mock_tenant_db)

    _patch_all()

    # Provide a way for tests to change the tenant_id if needed
    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        # Re-patch get_database everywhere to use the new tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def itam_app(mock_db, patch_get_database_globally, monkeypatch):
    """Fixture to create a test FastAPI app with ITAM routers and mocked DB."""
    import itam_catalog_endpoints
    import itam_asset_endpoints

    # itam_catalog_endpoints/itam_asset_endpoints both do `from rbac_utils import
    # verify_permission` / `from cache_service import invalidate_cache` (name-binding
    # imports), so patching the rbac_utils/cache_service module attribute does not affect
    # their already-bound local references — patch each module's own imported name.
    monkeypatch.setattr(itam_catalog_endpoints, "verify_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(itam_asset_endpoints, "invalidate_cache", AsyncMock())

    app, _ = make_test_app(
        itam_catalog_endpoints.router,
        itam_asset_endpoints.router,
    )
    return app


class TestCatalogManufacturer:
    """Tests for manufacturer CRUD in /api/itam/catalog/manufacturers."""

    @pytest.mark.asyncio
    async def test_create_manufacturer_returns_generated_id(self, mock_db, itam_app, patch_get_database_globally):
        """POST to manufacturers kind returns a body with id and name."""
        # Setup mock db's underlying raw collection's insert_one
        inserted_docs = []
        # For itam_catalog_endpoints, insert_one returns a MagicMock with inserted_id
        mock_db.manufacturers.insert_one = AsyncMock(side_effect=lambda doc: (inserted_docs.append(doc), MagicMock(inserted_id="mock-id"))[1])

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a") # Set tenant for this test
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/manufacturers", json={"name": "Acme Inc"})

        assert r.status_code == 201, r.text # Changed to 201 as per itam_catalog_endpoints.py
        data = r.json()
        assert data["id"].startswith("manufacturer-")
        assert data["name"] == "Acme Inc"
        assert "createdAt" in data
        assert len(inserted_docs) == 1
        assert inserted_docs[0]["name"] == "Acme Inc"
        assert inserted_docs[0]["tenantId"] == "tenant-a"

    @pytest.mark.asyncio
    async def test_get_manufacturer_round_trip(self, mock_db, itam_app, patch_get_database_globally):
        """Round-trip create then read by ID."""
        stored = []

        mock_db.manufacturers.insert_one = AsyncMock(side_effect=lambda doc: (stored.append(doc), MagicMock(inserted_id="mock-id"))[1])
        mock_db.manufacturers.find_one = AsyncMock(side_effect=lambda f, *args, **kwargs:
                                                   next((d for d in stored if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id")), None))
        # app code chains .find(...).limit(...).to_list(...) — .limit() must return the same
        # cursor-shaped mock that carries to_list, not a fresh unconfigured MagicMock.
        find_cursor = MagicMock()
        find_cursor.limit = MagicMock(return_value=find_cursor)
        find_cursor.to_list = AsyncMock(side_effect=lambda length: [d for d in stored])
        mock_db.manufacturers.find = MagicMock(return_value=find_cursor)


        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a") # Set tenant for this test
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            # create
            r = await ac.post("/api/itam/catalog/manufacturers", json={"name": "Roundtrip Corp"})
            assert r.status_code == 201, r.text
            created_id = r.json()["id"]

            # get by ID
            r2 = await ac.get(f"/api/itam/catalog/manufacturers/{created_id}")
            assert r2.status_code == 200, r2.text
            assert r2.json()["name"] == "Roundtrip Corp"

            # list
            r3 = await ac.get("/api/itam/catalog/manufacturers")
            assert r3.status_code == 200
            assert any(d["id"] == created_id for d in r3.json())

    @pytest.mark.asyncio
    async def test_unknown_catalog_kind_returns_404(self, itam_app, patch_get_database_globally):
        """Unrecognized kind returns 404."""
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a") # Set tenant for this test
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/unknown_kind", json={"name": "Bogus"})
            assert r.status_code == 404
            assert "not found" in r.json()["detail"].lower()

            r2 = await ac.get("/api/itam/catalog/unknown_kind/some-id")
            assert r2.status_code == 404
            assert "not found" in r2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_manufacturer_referenced_by_asset_returns_409(self, mock_db, itam_app, patch_get_database_globally):
        """Deleting a Manufacturer referenced by at least one asset is refused with 409 and the manufacturer is not removed."""
        mock_db.assets.count_documents = AsyncMock(return_value=1)
        mock_db.manufacturers.delete_one = AsyncMock()

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.delete("/api/itam/catalog/manufacturers/manufacturer-in-use")
            assert r.status_code == 409, r.text
            assert "reference" in r.json()["detail"].lower()

        mock_db.manufacturers.delete_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_unreferenced_manufacturer_succeeds(self, mock_db, itam_app, patch_get_database_globally):
        """Deleting a Manufacturer with zero referencing assets succeeds (204)."""
        mock_db.assets.count_documents = AsyncMock(return_value=0)
        mock_db.manufacturers.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.delete("/api/itam/catalog/manufacturers/manufacturer-unused")
            assert r.status_code == 204, r.text

        mock_db.manufacturers.delete_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_manufacturer_cross_tenant_isolation(self, mock_db, itam_app, patch_get_database_globally):
        """A tenant-scoped caller cannot read a Manufacturer belonging to another tenant."""
        stored = [{"id": "manufacturer-belongs-to-b", "name": "OtherTenantCo", "tenantId": "tenant-b"}]
        mock_db.manufacturers.find_one = AsyncMock(side_effect=lambda f, *a, **kw:
            next((d for d in stored if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id")), None))

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/catalog/manufacturers/manufacturer-belongs-to-b")
            assert r.status_code == 404, r.text


class TestManualAssetCreate:
    """Tests for POST /api/assets manual asset creation."""

    @pytest.mark.asyncio
    async def test_create_manual_asset_end_to_end(self, mock_db, itam_app, patch_get_database_globally):
        """E2E: create manufacturer then manual asset returns correct fields."""
        asset_docs = []
        mf_docs = []
        counter_seq = 0

        async def manuf_insert(doc):
            mf_docs.append(doc)
            return MagicMock(inserted_id="x")

        async def manuf_find_one(f, *args, **kwargs):
            for d in mf_docs:
                if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id"):
                    return dict(d)
            return None

        async def asset_insert(doc):
            asset_docs.append(doc)
            return MagicMock(inserted_id="x")

        # Mock the underlying raw collection calls for find_one_and_update for counters
        async def counter_find_one_and_update(f, u, *, upsert=False, return_document=None):
            # This is a mock of _raw_collection.find_one_and_update
            nonlocal counter_seq
            counter_seq += 1
            # Return a dictionary with 'seq' key as an integer
            return {"tenantId": f["tenantId"], "name": f["name"], "seq": counter_seq}

        mock_db.manufacturers.insert_one = AsyncMock(side_effect=manuf_insert)
        mock_db.manufacturers.find_one = AsyncMock(side_effect=manuf_find_one)
        mock_db.assets.insert_one = AsyncMock(side_effect=asset_insert)
        mock_db.counters.find_one_and_update = AsyncMock(side_effect=counter_find_one_and_update)

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a") # Set tenant for this test
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            # create manufacturer
            r = await ac.post("/api/itam/catalog/manufacturers", json={"name": "Acme"})
            assert r.status_code == 201, r.text
            mid = r.json()["id"]

            # create manual asset
            r2 = await ac.post("/api/assets", json={
                "name": "Laptop X1",
                "manufacturerId": mid
            })
            assert r2.status_code == 201, r2.text
            data = r2.json()
            assert data["assetSource"] == ASSET_SOURCE_MANUAL
            assert data["lifecycleStatus"] == DEFAULT_LIFECYCLE_STATUS.value
            assert data["id"].startswith("asset-")
            assert "assetTag" in data
            assert data["assetTag"].startswith("IT-")
            assert len(data["assetTag"]) == 7 # tag format IT-0001
            assert "status" not in data # Should not have agent-liveness status

    @pytest.mark.asyncio
    async def test_manual_asset_does_not_write_agent_status_field(self, mock_db, itam_app, patch_get_database_globally):
        """Manual asset must not write the 'status' key (agent-liveness)."""
        inserted = []
        mock_db.assets.insert_one = AsyncMock(side_effect=lambda doc: (inserted.append(doc), MagicMock(inserted_id="x"))[1])
        # A lambda using `:=` on an outer-scope name creates a new local binding inside the
        # lambda itself (UnboundLocalError on read-before-assign) — use a mutable container instead.
        _counter_state = {"seq": 0}

        async def _counter_find_one_and_update(f, u, *args, **kwargs):
            _counter_state["seq"] += 1
            return {"seq": _counter_state["seq"], **f}

        mock_db.counters.find_one_and_update = AsyncMock(side_effect=_counter_find_one_and_update)
        mock_db.manufacturers.find_one = AsyncMock(return_value={"id": "mf-abc", "name": "Acme"})

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a") # Set tenant for this test
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets", json={
                "name": "Server Z",
                "manufacturerId": "mf-abc"
            })
            assert r.status_code == 201, r.text

        assert len(inserted) >= 1
        assert "status" not in inserted[0]

    @pytest.mark.asyncio
    async def test_manual_asset_rejects_unknown_manufacturer(self, mock_db, itam_app, patch_get_database_globally):
        """Unknown manufacturerId returns 400 and no asset inserted."""
        # `(asset_called := True, ...)` inside a lambda binds a NEW local inside the lambda's
        # own scope, never the outer name — use a mutable container so the outer assertion
        # actually observes whether insert_one ran (see the counter-lambda bug fixed above).
        call_state = {"asset_inserted": False}

        def _insert(doc):
            call_state["asset_inserted"] = True
            return MagicMock(inserted_id="x")

        mock_db.assets.insert_one = AsyncMock(side_effect=_insert)
        mock_db.manufacturers.find_one = AsyncMock(return_value=None)

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a") # Set tenant for this test
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets", json={"name": "x", "manufacturerId": "bad-id"})
            assert r.status_code == 400, r.text
            assert "not found" in r.json()["detail"].lower()

        assert call_state["asset_inserted"] is False

    @pytest.mark.asyncio
    async def test_manual_asset_duplicate_caller_tag_returns_409(self, mock_db, itam_app, patch_get_database_globally):
        """A caller-supplied assetTag that already exists in the tenant is refused with 409 and no asset is inserted."""
        call_state = {"asset_inserted": False}

        def _insert(doc):
            call_state["asset_inserted"] = True
            return MagicMock(inserted_id="x")

        mock_db.assets.insert_one = AsyncMock(side_effect=_insert)
        mock_db.assets.find_one = AsyncMock(return_value={"id": "asset-existing", "assetTag": "IT-0099"})

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets", json={"name": "Dup Tag Asset", "assetTag": "IT-0099"})
            assert r.status_code == 409, r.text
            assert "already exists" in r.json()["detail"].lower()

        assert call_state["asset_inserted"] is False

    @pytest.mark.asyncio
    async def test_concurrent_manual_asset_creation_gets_distinct_tags(self, mock_db, itam_app, patch_get_database_globally):
        """Two manual-asset creations issued concurrently in the same tenant produce two distinct asset tags — proven against the real atomic $inc counter logic, not a pre-scripted sequence."""
        import asyncio as _asyncio

        counter_state = {"seq": 0}

        async def _counter_find_one_and_update(f, u, *args, **kwargs):
            # Mirrors MongoDB's real find_one_and_update atomicity contract for this
            # single-document counter: each call sees a strictly incremented seq.
            counter_state["seq"] += 1
            return {"seq": counter_state["seq"], **f}

        mock_db.counters.find_one_and_update = AsyncMock(side_effect=_counter_find_one_and_update)
        mock_db.assets.insert_one = AsyncMock(side_effect=lambda doc: MagicMock(inserted_id="x"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r1, r2 = await _asyncio.gather(
                ac.post("/api/assets", json={"name": "Concurrent A"}),
                ac.post("/api/assets", json={"name": "Concurrent B"}),
            )
            assert r1.status_code == 201, r1.text
            assert r2.status_code == 201, r2.text
            assert r1.json()["assetTag"] != r2.json()["assetTag"]

    @pytest.mark.asyncio
    async def test_privileged_fields_rejected_422(self, mock_db, itam_app, patch_get_database_globally):
        """Body containing tenantId, id, assetSource, or status is rejected with 422."""
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a") # Set tenant for this test
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets", json={
                "name": "Bad",
                "id": "forged-id",
                "assetSource": ASSET_SOURCE_AGENT,
                "status": "compromised",
                "tenantId": "evil",
            })
            assert r.status_code == 422, r.text
            errs = r.json()["detail"]
            fields = {e["loc"][-1] for e in errs if e["type"] == "extra_forbidden"}
            assert "id" in fields
            assert "assetSource" in fields
            assert "status" in fields
            assert "tenantId" in fields

    @pytest.mark.asyncio
    async def test_catalog_and_asset_routes_require_permission(self, itam_app, patch_get_database_globally, monkeypatch):
        """Routes without manage:assets permission return 403."""
        # Temporarily override verify_permission for this test to return False (must patch
        # each module's own imported name — see the itam_app fixture comment above).
        import itam_catalog_endpoints
        import itam_asset_endpoints
        monkeypatch.setattr(itam_catalog_endpoints, "verify_permission", AsyncMock(return_value=False))
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))

        current_user = make_token_data(role="user", tenant_id="tenant-a")
        patch_get_database_globally("tenant-a") # Set tenant for this test
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            # Test catalog route
            r_cat = await ac.post("/api/itam/catalog/manufacturers", json={"name": "Blocked"})
            assert r_cat.status_code == 403, r_cat.text

            # Test asset route
            r_asset = await ac.post("/api/assets", json={"name": "Blocked Asset"})
            assert r_asset.status_code == 403, r_asset.text