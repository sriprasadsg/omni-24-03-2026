"""ITAM audit trail tests — Phase 65 Plan 02 (ITAM-DAT-02).

Reuses the hand-rolled MockTenantIsolatedCollection/Database convention
established in test_itam_foundation.py / test_itam_catalog.py. Because
AuditService.get_logs now chains .sort().skip().limit().to_list() instead of
a single .to_list(length=100) call, the audit_logs collection fake needs a
small cursor double (_FakeCursor) whose sort/skip/limit each return self and
whose to_list is a real `async def` returning the seeded rows.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import make_test_app, make_token_data, _make_col
from authentication_service import get_current_user as real_get_current_user


class _FakeCursor:
    """Minimal Motor-cursor double supporting .sort().skip().limit().to_list()."""

    def __init__(self, docs):
        self._docs = list(docs)
        self._skip = 0
        self._limit = None

    def sort(self, *args, **kwargs):
        self._docs = sorted(self._docs, key=lambda d: d.get("timestamp", ""), reverse=True)
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, length=None):
        docs = self._docs[self._skip:]
        if self._limit is not None:
            docs = docs[: self._limit]
        return docs


class MockTenantIsolatedCollection:
    """Same shape as test_itam_foundation.py's — real `async def` proxy methods, never
    AsyncMock(side_effect=lambda ...) wrapping another AsyncMock."""

    def __init__(self, collection_name, tenant_id, raw_collection_mock):
        self._collection_name = collection_name
        self._tenant_id = tenant_id
        self._raw_collection = raw_collection_mock

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


AUDIT_TEST_COLLECTIONS = (
    "assets", "manufacturers", "asset_categories", "locations", "suppliers",
    "asset_models", "counters", "audit_logs", "licenses", "license_assignments",
    "consumables", "components",
)


@pytest.fixture
def mock_db():
    """Basic mock database plus an in-memory-backed audit_logs collection."""
    db = MagicMock()
    for name in AUDIT_TEST_COLLECTIONS:
        setattr(db, name, _make_col())

    # _make_col() does not wire find_one_and_update — itam_asset_endpoints.next_asset_tag
    # needs a real counter-increment double, matching test_itam_foundation.py's convention.
    _counter_seq = {"n": 0}

    async def _counter_find_one_and_update(f, u, *, upsert=False, return_document=None):
        _counter_seq["n"] += 1
        return {"tenantId": f.get("tenantId"), "name": f.get("name"), "seq": _counter_seq["n"]}

    db.counters.find_one_and_update = AsyncMock(side_effect=_counter_find_one_and_update)

    audit_store: list = []
    db.audit_logs._store = audit_store  # exposed so tests can seed/inspect entries
    db.audit_logs._last_query = None

    async def _audit_insert_one(doc):
        audit_store.append(dict(doc))
        return MagicMock(inserted_id=doc.get("id"))

    def _audit_find(f=None, *args, **kwargs):
        f = f or {}
        db.audit_logs._last_query = f
        matched = [d for d in audit_store if all(d.get(k) == v for k, v in f.items())]
        return _FakeCursor(matched)

    async def _audit_find_one(f=None, *args, **kwargs):
        f = f or {}
        for d in sorted(audit_store, key=lambda x: x.get("timestamp", ""), reverse=True):
            if all(d.get(k) == v for k, v in f.items()):
                return dict(d)
        return None

    db.audit_logs.insert_one = AsyncMock(side_effect=_audit_insert_one)
    db.audit_logs.find = MagicMock(side_effect=_audit_find)
    db.audit_logs.find_one = AsyncMock(side_effect=_audit_find_one)
    return db


@pytest.fixture(autouse=True)
def patch_get_database_globally(mock_db, monkeypatch):
    """itam_*_endpoints.py and audit_service.py all do `from database import
    get_database` (name-binding import), so patching database.get_database alone
    does not affect their already-bound local references — each importing
    module's own name must be patched too."""
    import database
    import itam_asset_endpoints
    import itam_catalog_endpoints
    import itam_lifecycle_endpoints
    import itam_finance_endpoints
    import itam_license_endpoints
    import itam_consumable_endpoints
    import itam_component_endpoints
    import audit_service
    _current_tenant_id = "tenant-a"

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(database, "get_database", get_mock_tenant_db)
        for mod in (
            itam_asset_endpoints, itam_catalog_endpoints, itam_lifecycle_endpoints,
            itam_finance_endpoints, itam_license_endpoints, itam_consumable_endpoints,
            itam_component_endpoints, audit_service,
        ):
            monkeypatch.setattr(mod, "get_database", get_mock_tenant_db, raising=False)

    _patch_all()

    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def itam_app(mock_db, patch_get_database_globally, monkeypatch):
    """Mounts the asset router (write path) and the audit router (read path)."""
    import itam_asset_endpoints
    import audit_endpoints
    import rbac_utils

    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(itam_asset_endpoints, "invalidate_cache", MagicMock())
    # audit_endpoints.py's route is gated by rbac_utils.require_permission("view:audit_log"),
    # whose inner dependency calls rbac_utils.verify_permission — bypass it the same way the
    # ITAM routers bypass their own verify_permission import, and pin get_tenant_id to the
    # fixture's tenant rather than relying on the real ContextVar (this minimal test app has
    # no tenant-context middleware to populate it).
    monkeypatch.setattr(rbac_utils, "verify_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(audit_endpoints, "get_tenant_id", lambda: "tenant-a")

    app, _ = make_test_app(itam_asset_endpoints.router, audit_endpoints.router)
    return app


class TestAssetCreateAuditBackfill:
    """Task 1: creating a manual asset writes one entry to the shared ledger."""

    @pytest.mark.asyncio
    async def test_create_manual_asset_logs_one_audit_entry(self, mock_db, itam_app, patch_get_database_globally):
        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="alice@tenant.com")
        patch_get_database_globally("tenant-a")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets", json={"name": "Laptop X1"})
            assert r.status_code == 201, r.text
            asset_id = r.json()["id"]

        assert len(mock_db.audit_logs._store) == 1
        entry = mock_db.audit_logs._store[0]
        assert entry["resourceType"] == "itam_asset"
        assert entry["resourceId"] == asset_id
        assert entry["action"] == "itam_asset.create"
        assert entry["userName"] == "alice@tenant.com"

    @pytest.mark.asyncio
    async def test_asset_create_still_succeeds_when_audit_write_raises(
        self, mock_db, itam_app, patch_get_database_globally, monkeypatch
    ):
        import itam_audit_service

        class _RaisingAuditService:
            async def log_action_async(self, *args, **kwargs):
                raise RuntimeError("ledger unavailable")

        monkeypatch.setattr(itam_audit_service, "get_audit_service", lambda: _RaisingAuditService())

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets", json={"name": "Laptop X2"})
            assert r.status_code == 201, r.text
        # Zero entries were persisted — the raise happened before insert_one — but the
        # write itself is what matters here: the route did not fail.
        assert len(mock_db.audit_logs._store) == 0


class TestAuditLogsFilterRoute:
    """GET /api/audit-logs honours resourceType/resourceId/limit/skip."""

    @pytest.mark.asyncio
    async def test_get_audit_logs_filters_by_resource_type_and_id(self, mock_db, itam_app, patch_get_database_globally):
        patch_get_database_globally("tenant-a")
        mock_db.audit_logs._store.extend([
            {
                "id": "log-1", "timestamp": "2026-01-01T00:00:00Z", "userName": "alice",
                "action": "itam_asset.create", "resourceType": "itam_asset", "resourceId": "asset-1",
                "details": "x", "tenantId": "tenant-a", "hash": "h1", "previousHash": "0" * 64,
            },
            {
                "id": "log-2", "timestamp": "2026-01-02T00:00:00Z", "userName": "alice",
                "action": "itam_asset.checkout", "resourceType": "itam_asset", "resourceId": "asset-2",
                "details": "y", "tenantId": "tenant-a", "hash": "h2", "previousHash": "h1",
            },
        ])
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/audit-logs", params={"resourceType": "itam_asset", "resourceId": "asset-1"})
            assert r.status_code == 200, r.text
            data = r.json()
            assert len(data) == 1
            assert data[0]["resourceId"] == "asset-1"

    @pytest.mark.asyncio
    async def test_get_audit_logs_forwards_limit_and_skip(self, mock_db, itam_app, patch_get_database_globally):
        patch_get_database_globally("tenant-a")
        mock_db.audit_logs._store.extend([
            {
                "id": f"log-{i}", "timestamp": f"2026-01-{i:02d}T00:00:00Z", "userName": "alice",
                "action": "itam_asset.create", "resourceType": "itam_asset", "resourceId": f"asset-{i}",
                "details": "x", "tenantId": "tenant-a", "hash": f"h{i}", "previousHash": "0" * 64,
            }
            for i in range(1, 6)
        ])
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/audit-logs", params={"limit": 2, "skip": 1})
            assert r.status_code == 200, r.text
            data = r.json()
            assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_audit_logs_query_always_carries_tenant_id(self, mock_db, itam_app, patch_get_database_globally):
        """Filters narrow the tenant-scoped query, they never replace the tenantId term —
        a resource filter can never leak another tenant's entries."""
        patch_get_database_globally("tenant-a")
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/audit-logs", params={"resourceType": "itam_asset", "resourceId": "asset-1"})
            assert r.status_code == 200, r.text

        assert mock_db.audit_logs._last_query is not None
        assert mock_db.audit_logs._last_query.get("tenantId") == "tenant-a"
        assert mock_db.audit_logs._last_query.get("resourceType") == "itam_asset"
        assert mock_db.audit_logs._last_query.get("resourceId") == "asset-1"
