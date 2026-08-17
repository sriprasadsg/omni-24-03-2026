"""ITAM CSV import/export tests — Phase 65 Plan 03 (ITAM-DAT-03).

Task 1 (this file, initial content): the export half only — `GET
/api/itam/data/export` plus unit coverage of `sanitize_csv_cell`. Task 2
extends this file with the import half's behaviors.

Reuses the hand-rolled MockTenantIsolatedCollection/Database convention from
test_itam_foundation.py / test_itam_audit.py. The export route chains
.find().limit().to_list(), so the assets collection fake needs a small
cursor double (_FakeCursor) whose limit returns self and whose to_list is a
real `async def`.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import make_test_app, make_token_data, _make_col
from authentication_service import get_current_user as real_get_current_user
from itam_data_service import (
    sanitize_csv_cell,
    ASSET_EXPORT_COLUMNS,
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    parse_csv_rows,
    row_to_asset_payload,
)


class _FakeCursor:
    """Minimal Motor-cursor double supporting .limit().to_list()."""

    def __init__(self, docs):
        self._docs = list(docs)
        self._limit = None

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, length=None):
        docs = self._docs
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

        async def _find_one_and_update(f, u, *args, **kwargs):
            return await raw_collection_mock.find_one_and_update({**f, "tenantId": self._tenant_id}, u, *args, **kwargs)

        self.find_one = _find_one
        self.insert_one = _insert_one
        self.find_one_and_update = _find_one_and_update
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


DATA_TEST_COLLECTIONS = ("assets", "asset_models", "counters", "audit_logs")


@pytest.fixture
def mock_db():
    """Basic mock database plus an in-memory-backed assets/audit_logs collection."""
    db = MagicMock()
    for name in DATA_TEST_COLLECTIONS:
        setattr(db, name, _make_col())

    assets_store: list = []
    db.assets._store = assets_store

    def _assets_find(f=None, *args, **kwargs):
        f = f or {}
        matched = [
            d for d in assets_store
            if all(d.get(k) == v for k, v in f.items() if k != "tenantId")
        ]
        return _FakeCursor(matched)

    db.assets.find = MagicMock(side_effect=_assets_find)

    async def _assets_find_one(f=None, *args, **kwargs):
        f = f or {}
        for d in assets_store:
            if all(d.get(k) == v for k, v in f.items() if k != "tenantId"):
                return dict(d)
        return None

    db.assets.find_one = AsyncMock(side_effect=_assets_find_one)

    async def _assets_insert_one(doc, *args, **kwargs):
        assets_store.append(dict(doc))
        return MagicMock(inserted_id=doc.get("id"))

    db.assets.insert_one = AsyncMock(side_effect=_assets_insert_one)

    model_store: list = []
    db.asset_models._store = model_store

    async def _asset_models_find_one(f=None, *args, **kwargs):
        f = f or {}
        for d in model_store:
            if all(d.get(k) == v for k, v in f.items() if k != "tenantId"):
                return dict(d)
        return None

    db.asset_models.find_one = AsyncMock(side_effect=_asset_models_find_one)

    _counter_seq = {"n": 0}

    async def _counter_find_one_and_update(f, u, *, upsert=False, return_document=None):
        _counter_seq["n"] += 1
        return {"tenantId": f.get("tenantId"), "name": f.get("name"), "seq": _counter_seq["n"]}

    db.counters.find_one_and_update = AsyncMock(side_effect=_counter_find_one_and_update)

    audit_store: list = []
    db.audit_logs._store = audit_store

    async def _audit_insert_one(doc):
        audit_store.append(dict(doc))
        return MagicMock(inserted_id=doc.get("id"))

    db.audit_logs.insert_one = AsyncMock(side_effect=_audit_insert_one)

    return db


@pytest.fixture(autouse=True)
def patch_get_database_globally(mock_db, monkeypatch):
    """itam_asset_endpoints.py, itam_data_endpoints.py, and audit_service.py all do
    `from database import get_database` (name-binding import), so patching
    database.get_database alone does not affect their already-bound local
    references — each importing module's own name must be patched too."""
    import database
    import itam_asset_endpoints
    import itam_data_endpoints
    import audit_service

    _current_tenant_id = "tenant-a"

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(database, "get_database", get_mock_tenant_db)
        for mod in (itam_asset_endpoints, itam_data_endpoints, audit_service):
            monkeypatch.setattr(mod, "get_database", get_mock_tenant_db, raising=False)

    _patch_all()

    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def itam_app(mock_db, patch_get_database_globally, monkeypatch):
    import itam_asset_endpoints
    import itam_data_endpoints

    # itam_data_endpoints._require_itam_admin is imported from
    # itam_asset_endpoints, which calls verify_permission bound in its own
    # module namespace — patch it there, matching every other ITAM test file.
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(itam_data_endpoints, "invalidate_cache", MagicMock())

    app, _ = make_test_app(itam_data_endpoints.router)
    return app


def _csv_upload(text: str, filename: str = "assets.csv"):
    """Build the httpx `files=` kwarg for a text/csv multipart upload."""
    return {"file": (filename, text.encode("utf-8"), "text/csv")}


class TestExportAssetsRoute:
    """Task 1: GET /api/itam/data/export."""

    @pytest.mark.asyncio
    async def test_export_two_assets_returns_csv_with_header_and_custom_columns(
        self, mock_db, itam_app, patch_get_database_globally
    ):
        patch_get_database_globally("tenant-a")
        mock_db.assets._store.extend([
            {
                "id": "asset-1", "tenantId": "tenant-a", "assetTag": "IT-0001", "name": "Laptop A",
                "serialNumber": "SN1", "type": "laptop", "lifecycleStatus": "deployable",
                "createdAt": "2026-01-01T00:00:00.000Z", "updatedAt": "2026-01-01T00:00:00.000Z",
                "customFields": {"warrantyProvider": "Acme"},
            },
            {
                "id": "asset-2", "tenantId": "tenant-a", "assetTag": "IT-0002", "name": "Laptop B",
                "serialNumber": "SN2", "type": "laptop", "lifecycleStatus": "deployed",
                "createdAt": "2026-01-02T00:00:00.000Z", "updatedAt": "2026-01-02T00:00:00.000Z",
                "customFields": {"purchaseRegion": "US"},
            },
        ])

        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/data/export")

        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]

        header = r.text.splitlines()[0]
        for col in ASSET_EXPORT_COLUMNS:
            assert col in header, f"missing base column {col!r} in header {header!r}"
        assert "customFields.warrantyProvider" in header
        assert "customFields.purchaseRegion" in header
        assert "IT-0001" in r.text
        assert "IT-0002" in r.text

        # Ledger entry recorded for the export.
        assert len(mock_db.audit_logs._store) == 1
        assert mock_db.audit_logs._store[0]["resourceType"] == "itam_export"
        assert mock_db.audit_logs._store[0]["action"] == "itam_export.assets"

    @pytest.mark.asyncio
    async def test_export_neutralizes_formula_leading_cell(self, mock_db, itam_app, patch_get_database_globally):
        patch_get_database_globally("tenant-a")
        mock_db.assets._store.append({
            "id": "asset-1", "tenantId": "tenant-a", "assetTag": "IT-0001",
            "name": "=cmd|'/c calc'!A1",
            "createdAt": "2026-01-01T00:00:00.000Z", "updatedAt": "2026-01-01T00:00:00.000Z",
        })
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/data/export")

        assert r.status_code == 200, r.text
        assert "'=cmd|'/c calc'!A1" in r.text

    @pytest.mark.asyncio
    async def test_export_rejects_unsupported_entity(self, mock_db, itam_app, patch_get_database_globally):
        patch_get_database_globally("tenant-a")
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/data/export", params={"entity": "licenses"})

        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_export_with_no_assets_still_writes_a_header_row(self, mock_db, itam_app, patch_get_database_globally):
        patch_get_database_globally("tenant-a")
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/data/export")

        assert r.status_code == 200, r.text
        lines = r.text.splitlines()
        assert len(lines) == 1  # header only, no data rows
        for col in ASSET_EXPORT_COLUMNS:
            assert col in lines[0]


class TestSanitizeCsvCell:
    """Unit tests for the sole T-65-03-01 mitigation, independent of the route."""

    @pytest.mark.parametrize("leading_char", ["=", "+", "-", "@", "\t", "\r"])
    def test_prefixes_apostrophe_for_risky_leading_chars(self, leading_char):
        value = f"{leading_char}rest-of-value"
        assert sanitize_csv_cell(value) == f"'{value}"

    def test_benign_value_passes_through_unchanged(self):
        assert sanitize_csv_cell("Laptop A") == "Laptop A"

    def test_none_becomes_empty_string(self):
        assert sanitize_csv_cell(None) == ""

    def test_non_string_value_is_coerced_to_str(self):
        assert sanitize_csv_cell(1500) == "1500"


class TestRowToAssetPayload:
    """Unit tests for the import-side row-shaping helper, independent of the route."""

    def test_blank_cell_is_absent_not_empty_string(self):
        payload, problems = row_to_asset_payload({"name": "Laptop A", "notes": ""})
        assert payload == {"name": "Laptop A"}
        assert problems == []

    def test_server_owned_columns_are_dropped(self):
        payload, problems = row_to_asset_payload({
            "name": "Laptop A", "id": "asset-hostile", "tenantId": "other-tenant",
            "createdAt": "2020-01-01", "assetSource": "manual",
        })
        assert payload == {"name": "Laptop A"}
        assert problems == []

    def test_custom_field_columns_are_nested(self):
        payload, problems = row_to_asset_payload({
            "name": "Laptop A", "customFields.os": "Windows", "customFields.warrantyProvider": "Acme",
        })
        assert payload["customFields"] == {"os": "Windows", "warrantyProvider": "Acme"}
        assert problems == []

    def test_non_integer_purchase_cost_is_reported_as_a_problem(self):
        payload, problems = row_to_asset_payload({"name": "Laptop A", "purchaseCostCents": "not-a-number"})
        assert "purchaseCostCents" not in payload
        assert any("purchaseCostCents" in p for p in problems)

    def test_integer_fields_are_coerced(self):
        payload, problems = row_to_asset_payload({"purchaseCostCents": "50000", "warrantyMonths": "24"})
        assert payload["purchaseCostCents"] == 50000
        assert payload["warrantyMonths"] == 24
        assert problems == []

    def test_unknown_column_is_forwarded_verbatim_for_the_caller_to_reject(self):
        payload, problems = row_to_asset_payload({"name": "Laptop A", "totallyMadeUpColumn": "x"})
        assert payload["totallyMadeUpColumn"] == "x"
        assert problems == []


class TestParseCsvRows:
    def test_parses_rows_in_file_order(self):
        rows = parse_csv_rows("name,assetTag\nLaptop A,IT-0001\nLaptop B,IT-0002\n")
        assert [r["assetTag"] for r in rows] == ["IT-0001", "IT-0002"]


class TestImportAssetsRoute:
    """Task 2: POST /api/itam/data/import — the eight documented behaviors."""

    @pytest.mark.asyncio
    async def test_valid_row_with_known_model_creates_one_asset(
        self, mock_db, itam_app, patch_get_database_globally
    ):
        patch_get_database_globally("tenant-a")
        mock_db.asset_models._store.append({
            "id": "model-1", "tenantId": "tenant-a", "name": "Laptop X1",
            "fieldsets": [{"name": "Specs", "fields": [
                {"key": "os", "label": "OS", "type": "select", "required": False, "options": ["Windows", "macOS"]},
            ]}],
        })
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        csv_text = "name,modelId,customFields.os\nLaptop A,model-1,Windows\n"
        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/data/import", files=_csv_upload(csv_text))

        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"created": 1, "skipped": 0, "dryRun": False, "errors": [], "errorsTruncated": False}
        assert len(mock_db.assets._store) == 1
        assert mock_db.assets._store[0]["modelId"] == "model-1"
        # Per-asset + batch audit entries.
        actions = [e["action"] for e in mock_db.audit_logs._store]
        assert "itam_asset.create" in actions
        assert "itam_import.assets" in actions

    @pytest.mark.asyncio
    async def test_unknown_model_id_is_skipped_rest_of_file_still_imports(
        self, mock_db, itam_app, patch_get_database_globally
    ):
        patch_get_database_globally("tenant-a")
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        csv_text = "name,modelId\nBad Row,model-does-not-exist\nGood Row,\n"
        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/data/import", files=_csv_upload(csv_text))

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 1
        assert body["skipped"] == 1
        assert len(body["errors"]) == 1
        assert body["errors"][0]["row"] == 1
        assert any("modelId" in p for p in body["errors"][0]["problems"])

    @pytest.mark.asyncio
    async def test_custom_field_value_outside_select_options_is_skipped_with_shared_validator_message(
        self, mock_db, itam_app, patch_get_database_globally
    ):
        patch_get_database_globally("tenant-a")
        mock_db.asset_models._store.append({
            "id": "model-1", "tenantId": "tenant-a", "name": "Laptop X1",
            "fieldsets": [{"name": "Specs", "fields": [
                {"key": "os", "label": "OS", "type": "select", "required": False, "options": ["Windows", "macOS"]},
            ]}],
        })
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        csv_text = "name,modelId,customFields.os\nLaptop A,model-1,Linux\n"
        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/data/import", files=_csv_upload(csv_text))

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 0
        assert body["skipped"] == 1
        # The exact message validate_custom_field_values produces — not one this module invented.
        assert body["errors"][0]["problems"] == ["Value for 'os' is not one of the allowed options."]

    @pytest.mark.asyncio
    async def test_unknown_column_is_skipped_naming_the_column(
        self, mock_db, itam_app, patch_get_database_globally
    ):
        patch_get_database_globally("tenant-a")
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        csv_text = "name,notAModelField\nLaptop A,surprise\n"
        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/data/import", files=_csv_upload(csv_text))

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 0
        assert body["skipped"] == 1
        assert any("notAModelField" in p for p in body["errors"][0]["problems"])

    @pytest.mark.asyncio
    async def test_dry_run_reports_same_counts_and_writes_nothing(
        self, mock_db, itam_app, patch_get_database_globally
    ):
        patch_get_database_globally("tenant-a")
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        csv_text = "name\nLaptop A\n"
        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/data/import", params={"dryRun": "true"}, files=_csv_upload(csv_text))

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 1
        assert body["skipped"] == 0
        assert body["dryRun"] is True
        assert mock_db.assets._store == []
        mock_db.assets.insert_one.assert_not_awaited()
        assert mock_db.audit_logs._store == []  # no audit entries for a dry run

    @pytest.mark.asyncio
    async def test_oversized_upload_refused_with_413_before_parsing(
        self, mock_db, itam_app, patch_get_database_globally
    ):
        patch_get_database_globally("tenant-a")
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        oversized = "name\n" + ("A" * (MAX_IMPORT_BYTES + 1))
        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/data/import", files=_csv_upload(oversized))

        assert r.status_code == 413, r.text
        assert mock_db.assets._store == []

    @pytest.mark.asyncio
    async def test_row_count_over_cap_refused_with_400(self, mock_db, itam_app, patch_get_database_globally):
        patch_get_database_globally("tenant-a")
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        rows = "\n".join(f"Laptop {i}" for i in range(MAX_IMPORT_ROWS + 1))
        csv_text = "name\n" + rows + "\n"
        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/data/import", files=_csv_upload(csv_text))

        assert r.status_code == 400, r.text
        assert f"{MAX_IMPORT_ROWS}" in r.text

    @pytest.mark.asyncio
    async def test_duplicate_asset_tag_is_skipped_not_aborted(
        self, mock_db, itam_app, patch_get_database_globally
    ):
        patch_get_database_globally("tenant-a")
        mock_db.assets._store.append({
            "id": "asset-existing", "tenantId": "tenant-a", "assetTag": "IT-0001", "name": "Existing",
        })
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        csv_text = "name,assetTag\nDupe Row,IT-0001\nGood Row,\n"
        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/data/import", files=_csv_upload(csv_text))

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 1
        assert body["skipped"] == 1
        assert any("IT-0001" in p for p in body["errors"][0]["problems"])

    @pytest.mark.asyncio
    async def test_non_csv_filename_rejected_with_400(self, mock_db, itam_app, patch_get_database_globally):
        patch_get_database_globally("tenant-a")
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/data/import", files=_csv_upload("name\nLaptop A\n", filename="assets.txt"))

        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_error_list_capped_and_errors_truncated_flag_set(
        self, mock_db, itam_app, patch_get_database_globally
    ):
        patch_get_database_globally("tenant-a")
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        itam_app.dependency_overrides[real_get_current_user] = lambda: current_user

        # Every row references a missing model, so every row is skipped —
        # more than the 100-entry error cap.
        rows = "\n".join(f"Laptop {i},model-missing" for i in range(120))
        csv_text = "name,modelId\n" + rows + "\n"
        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/data/import", files=_csv_upload(csv_text))

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["skipped"] == 120
        assert len(body["errors"]) == 100
        assert body["errorsTruncated"] is True
