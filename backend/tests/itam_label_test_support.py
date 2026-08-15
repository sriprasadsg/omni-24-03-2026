"""Shared test support for the ITAM Labels test suite (Phase 58).

Fixture set adapted from itam_lifecycle_test_support.py (Phase 57): assets
built with _make_col(); itam_label_endpoints.get_database patched;
itam_asset_endpoints.verify_permission patched (the RBAC dependency this
router uses is imported from that module).

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
    """Mock database carrying the assets collection the label router touches."""
    db = MagicMock()
    setattr(db, "assets", _make_col())
    return db


@pytest.fixture
def patch_label_get_database(mock_db, monkeypatch):
    """Patch get_database at itam_label_endpoints' own bound name (name-binding
    import — patching database.get_database alone would not affect it)."""
    import itam_label_endpoints
    _current_tenant_id = "tenant-a"

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(itam_label_endpoints, "get_database", get_mock_tenant_db)

    _patch_all()

    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def label_app(mock_db, patch_label_get_database, monkeypatch):
    """Test FastAPI app mounting only itam_label_endpoints.router."""
    import itam_label_endpoints
    import itam_asset_endpoints

    # The RBAC dependency this router uses (_require_itam_admin) is imported
    # from itam_asset_endpoints, so verify_permission must be patched at that
    # module's own bound name.
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))

    app, _ = make_test_app(itam_label_endpoints.router)
    return app


def tagged_asset(**overrides):
    doc = {
        "id": "asset-1",
        "tenantId": "tenant-a",
        "assetTag": "IT-0001",
        "name": "Laptop X1",
        "model": "ThinkPad T14",
    }
    doc.update(overrides)
    return doc
