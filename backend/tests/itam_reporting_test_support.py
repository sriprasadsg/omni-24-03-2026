"""Shared test support for the ITAM Reporting test suite (Phase 72).

Fixture set adapted from itam_finance_test_support.py: assets built with
_make_col(); itam_reporting_endpoints.get_database and
itam_reporting_service.get_database (both name-binding imports) patched at
their own bound names; itam_asset_endpoints.verify_permission patched (the
RBAC dependency this router's _require_itam_admin imports).

Seeds every collection the reporting stack (this plan and later ones) reads
so later plans' join tests can extend this file unchanged rather than
building a second fixture module.

This module is deliberately not named test_*.py so pytest does not try to
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
        # self._db (not self._raw_db) so the hasattr(db, "_db") unwrap guard
        # itam_finance_service.get_warranty_alert_window relies on resolves
        # this mock's real raw handle via a plain attribute read rather than
        # falling through to __getattr__ (which would return a bogus
        # tenant-wrapped collection instead) — mirrors
        # itam_finance_test_support.py's own MockTenantIsolatedDatabase.
        self._db = raw_db_mock
        self._tenant_id = tenant_id

    def __getattr__(self, name):
        return MockTenantIsolatedCollection(name, self._tenant_id, getattr(self._db, name))

    def __getitem__(self, name):
        return self.__getattr__(name)


@pytest.fixture
def mock_db():
    """Mock database carrying every collection the reporting stack (this
    plan and later ones) touches — seeded via _make_col() so a later plan's
    join tests can extend this fixture unchanged."""
    db = MagicMock()
    for name in (
        "assets", "licenses", "itam_consumables", "components",
        "assignment_history", "license_assignments", "asset_models",
        "system_settings", "itam_report_exports",
    ):
        setattr(db, name, _make_col())
    return db


@pytest.fixture
def patch_reporting_get_database(mock_db, monkeypatch):
    """Patch get_database at both itam_reporting_endpoints' and
    itam_reporting_service's own bound names (name-binding imports —
    patching database.get_database alone would not affect either). Returns
    a set_current_tenant_id callable."""
    import itam_reporting_endpoints
    import itam_reporting_service
    _current_tenant_id = "tenant-a"

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(itam_reporting_endpoints, "get_database", get_mock_tenant_db)
        monkeypatch.setattr(itam_reporting_service, "get_database", get_mock_tenant_db)

    _patch_all()

    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def reporting_app(mock_db, patch_reporting_get_database, monkeypatch):
    """Test FastAPI app mounting only itam_reporting_endpoints.router."""
    import itam_reporting_endpoints
    import itam_asset_endpoints

    # The RBAC dependency this router uses (_require_itam_admin) is imported
    # from itam_asset_endpoints, so verify_permission must be patched at that
    # module's own bound name.
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))

    app, _ = make_test_app(itam_reporting_endpoints.router)
    return app


def report_asset(**overrides):
    doc = {
        "id": "asset-1",
        "tenantId": "tenant-a",
        "assetTag": "IT-0001",
        "name": "Laptop X1",
        "lifecycleStatus": "deployed",
        "purchaseDate": None,
        "warrantyMonths": None,
    }
    doc.update(overrides)
    return doc


def report_license(**overrides):
    doc = {
        "id": "lic-1",
        "tenantId": "tenant-a",
        "name": "Acme Suite",
        "seatCount": 10,
    }
    doc.update(overrides)
    return doc


def report_consumable(**overrides):
    doc = {
        "id": "con-1",
        "tenantId": "tenant-a",
        "name": "USB-C Cable",
        "initialQuantity": 20,
        "availableQuantity": 20,
    }
    doc.update(overrides)
    return doc
