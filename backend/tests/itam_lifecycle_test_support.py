"""Shared test support for the ITAM Lifecycle test suite (Phase 57).

Fixture set copied from test_itam_foundation.py (no equivalent lives in
conftest.py) and adapted: assets/users/locations/assignment_history built
with _make_col(); itam_lifecycle_endpoints.get_database / .invalidate_cache
patched; itam_asset_endpoints.verify_permission patched (the RBAC dependency
this router uses is imported from that module).

Split out of test_itam_lifecycle.py to keep every test file under the
CLAUDE.md 500-line limit — pytest discovers fixtures imported by name into a
test module's namespace, so `from tests.itam_lifecycle_test_support import
mock_db, patch_get_database_globally, lifecycle_app` works without a
conftest.py override.

This module is deliberately not named `test_*.py` so pytest does not try to
collect it directly.
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_test_app, _make_col


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
    # _make_col()'s bare find()/to_list() double does not survive the
    # .sort().limit().to_list() chain itam_lifecycle_service.list_history performs
    # (precedent: tests/test_remediation_guards.py:207). Default to an empty result;
    # individual tests override this AsyncMock's return_value as needed.
    db.assignment_history.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[]
    )
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


def deployable_asset(**overrides):
    doc = {
        "id": "asset-1",
        "tenantId": "tenant-a",
        "lifecycleStatus": "deployable",
        "name": "Laptop X1",
    }
    doc.update(overrides)
    return doc


def deployed_asset_after_checkout(**overrides):
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
