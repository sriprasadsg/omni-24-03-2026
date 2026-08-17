"""Shared test support for the ITAM Finance test suite (Phase 59).

Fixture set adapted from itam_label_test_support.py (Phase 58): assets built
with _make_col(); itam_finance_endpoints.get_database patched;
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

        async def _update_one(f, u, *args, **kwargs):
            return await raw_collection_mock.update_one({**(f or {}), "tenantId": self._tenant_id}, u, *args, **kwargs)

        async def _count_documents(f, *args, **kwargs):
            return await raw_collection_mock.count_documents({**(f or {}), "tenantId": self._tenant_id}, *args, **kwargs)

        async def _find_one_and_update(f, u, *args, **kwargs):
            return await raw_collection_mock.find_one_and_update({**(f or {}), "tenantId": self._tenant_id}, u, *args, **kwargs)

        async def _delete_one(f, *args, **kwargs):
            return await raw_collection_mock.delete_one({**(f or {}), "tenantId": self._tenant_id}, *args, **kwargs)

        self.find_one = _find_one
        self.insert_one = _insert_one
        self.update_one = _update_one
        self.count_documents = _count_documents
        self.find_one_and_update = _find_one_and_update
        self.delete_one = _delete_one
        self.find = MagicMock(side_effect=lambda f=None, *args, **kwargs:
                              raw_collection_mock.find({**(f if f else {}), "tenantId": self._tenant_id}, *args, **kwargs))


class MockTenantIsolatedDatabase:
    def __init__(self, raw_db_mock, tenant_id):
        # NOT self._raw_db (the label test support's name): __getattr__ only
        # fires for attributes normal lookup misses, so an explicitly
        # assigned self._db returns the real raw mock via a plain attribute
        # read, whereas naming it self._raw_db would make db._db fall
        # through to __getattr__ and return a bogus collection wrapper — that
        # would silently break the hasattr(db, "_db") unwrap guard Plan
        # 59-03's get_warranty_alert_window relies on. Mirrors the
        # db._db = db convention test_compliance_remediation_sla.py and
        # test_evidence_lifecycle.py already use.
        self._db = raw_db_mock
        self._tenant_id = tenant_id

    def __getattr__(self, name):
        return MockTenantIsolatedCollection(name, self._tenant_id, getattr(self._db, name))

    def __getitem__(self, name):
        return self.__getattr__(name)


@pytest.fixture
def mock_db():
    """Mock database carrying the collections the finance router touches."""
    db = MagicMock()
    for name in ("assets", "suppliers", "asset_models", "counters", "system_settings"):
        setattr(db, name, _make_col())
    return db


@pytest.fixture
def patch_finance_get_database(mock_db, monkeypatch):
    """Patch get_database at itam_finance_endpoints' own bound name
    (name-binding import — patching database.get_database alone would not
    affect it). Returns a set_current_tenant_id callable."""
    import itam_finance_endpoints
    _current_tenant_id = "tenant-a"

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(itam_finance_endpoints, "get_database", get_mock_tenant_db)

    _patch_all()

    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def finance_app(mock_db, patch_finance_get_database, monkeypatch):
    """Test FastAPI app mounting only itam_finance_endpoints.router."""
    import itam_finance_endpoints
    import itam_asset_endpoints

    # The RBAC dependency this router uses (_require_itam_admin) is imported
    # from itam_asset_endpoints, so verify_permission must be patched at that
    # module's own bound name.
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))

    app, _ = make_test_app(itam_finance_endpoints.router)
    return app


@pytest.fixture
def asset_create_app(mock_db, patch_finance_get_database, monkeypatch):
    """Test FastAPI app mounting itam_asset_endpoints.router, so Task 2 can
    drive the manual-creation path. Also patches get_database at
    itam_asset_endpoints' own bound name."""
    import itam_asset_endpoints

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, "tenant-a")

    monkeypatch.setattr(itam_asset_endpoints, "get_database", get_mock_tenant_db)
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))

    app, _ = make_test_app(itam_asset_endpoints.router)
    return app


def finance_asset(**overrides):
    doc = {
        "id": "asset-1",
        "tenantId": "tenant-a",
        "assetTag": "IT-0001",
        "name": "Laptop X1",
        "modelId": "model-1",
    }
    doc.update(overrides)
    return doc


def depreciating_model(**overrides):
    doc = {
        "id": "model-1",
        "tenantId": "tenant-a",
        "name": "ThinkPad T14",
        "usefulLifeYears": 3,
        "salvageValueCents": 15000,
    }
    doc.update(overrides)
    return doc
