"""ITAM Labels sheet ROUTE tests — Phase 58 Plan 04, Task 2.

POST /api/assets/labels/sheet's no-silent-drop contract: 200 path with
ordering/duplicates preserved, and every refusal (empty, over-cap,
unresolved ids, untagged assets) named explicitly. Split out of
test_itam_labels_sheet.py to keep both files under the CLAUDE.md 500-line
limit.

Shared mock DB/fixtures live in itam_label_test_support.py; extract_pdf_text
is reused from test_itam_labels_sheet.py's Task 1 helpers.
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_token_data
from tests.itam_label_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    mock_db,
    patch_label_get_database,
    label_app,
    tagged_asset,
)
from tests.test_itam_labels_sheet import extract_pdf_text

from authentication_service import get_current_user as real_get_current_user
from api_key_auth import get_current_user_or_api_key  # Phase 73 (D-01/D-02): routes gated by _require_itam_admin now resolve through this dependency, not get_current_user
from itam_models import MAX_LABEL_SHEET_ASSETS


def _find_result(docs):
    m = MagicMock()
    m.to_list = AsyncMock(return_value=docs)
    return m


def _wire_find(mock_db, stored):
    """Wire mock_db.assets.find to honour the tenantId + $in filter that
    MockTenantIsolatedCollection.find injects, so cross-tenant/unresolved
    behavior is actually exercised rather than always returning everything."""

    def _side_effect(f, *args, **kwargs):
        tenant_id = f.get("tenantId")
        wanted_ids = set(f.get("id", {}).get("$in", []))
        matched = [d for d in stored if d.get("tenantId") == tenant_id and d.get("id") in wanted_ids]
        return _find_result(matched)

    mock_db.assets.find = MagicMock(side_effect=_side_effect)


class TestSheetRoute:
    """The 200 path — header, content type, ordering, duplicates."""

    @pytest.mark.asyncio
    async def test_sheet_route_200_with_three_ids_in_order(self, mock_db, label_app):
        stored = [
            tagged_asset(id="asset-1", assetTag="IT-0001"),
            tagged_asset(id="asset-2", assetTag="IT-0002"),
            tagged_asset(id="asset-3", assetTag="IT-0003"),
        ]
        _wire_find(mock_db, stored)

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post(
                "/api/assets/labels/sheet",
                json={"assetIds": ["asset-3", "asset-1", "asset-2"]},
            )

        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content.startswith(b"%PDF-")
        assert "filename=" in r.headers["content-disposition"]

        text = extract_pdf_text(r.content)
        # Order in the response must match request order (asset-3, asset-1,
        # asset-2), not the order the $in query happened to return rows in.
        pos3 = text.find(b"IT-0003")
        pos1 = text.find(b"IT-0001")
        pos2 = text.find(b"IT-0002")
        assert pos3 != -1 and pos1 != -1 and pos2 != -1
        assert pos3 < pos1 < pos2

    @pytest.mark.asyncio
    async def test_sheet_route_duplicate_ids_yield_two_labels(self, mock_db, label_app):
        stored = [tagged_asset(id="asset-1", assetTag="IT-0001")]
        _wire_find(mock_db, stored)

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post(
                "/api/assets/labels/sheet",
                json={"assetIds": ["asset-1", "asset-1"]},
            )

        assert r.status_code == 200, r.text
        text = extract_pdf_text(r.content)
        assert text.count(b"IT-0001") >= 2


class TestSheetRequestGuards:
    @pytest.mark.asyncio
    async def test_sheet_request_guards_empty_list_returns_400(self, mock_db, label_app):
        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/labels/sheet", json={"assetIds": []})

        assert r.status_code == 400, r.text

    @pytest.mark.asyncio
    async def test_sheet_request_guards_over_cap_returns_400_not_trimmed(self, mock_db, label_app):
        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        over_cap_ids = [f"asset-{i}" for i in range(MAX_LABEL_SHEET_ASSETS + 1)]

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/labels/sheet", json={"assetIds": over_cap_ids})

        assert r.status_code == 400, r.text
        assert not r.content.startswith(b"%PDF-")

    @pytest.mark.asyncio
    async def test_sheet_request_guards_unresolved_ids_returns_400_with_exact_set(
        self, mock_db, label_app
    ):
        stored = [tagged_asset(id="asset-1", assetTag="IT-0001")]
        _wire_find(mock_db, stored)

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post(
                "/api/assets/labels/sheet",
                json={"assetIds": ["asset-1", "does-not-exist-1", "does-not-exist-2"]},
            )

        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert set(detail["unresolvedAssetIds"]) == {"does-not-exist-1", "does-not-exist-2"}

    @pytest.mark.asyncio
    async def test_sheet_request_guards_missing_tag_returns_400_with_exact_set(
        self, mock_db, label_app
    ):
        stored = [
            tagged_asset(id="asset-1", assetTag="IT-0001"),
            tagged_asset(id="asset-2", assetTag=""),
        ]
        _wire_find(mock_db, stored)

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post(
                "/api/assets/labels/sheet",
                json={"assetIds": ["asset-1", "asset-2"]},
            )

        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert detail["assetIdsMissingTag"] == ["asset-2"]


class TestSheetRbac:
    @pytest.mark.asyncio
    async def test_sheet_rbac_denied_without_manage_assets(self, mock_db, label_app, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))

        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/labels/sheet", json={"assetIds": ["asset-1"]})

        assert r.status_code == 403, r.text


class TestSheetTenantIsolation:
    """A cross-tenant id and a fabricated id both land in unresolvedAssetIds
    with the identical status/message shape (T-58-01) — the response cannot
    be used to probe whether an id exists in another tenant."""

    @pytest.mark.asyncio
    async def test_sheet_tenant_isolation_cross_tenant_id_returns_400(
        self, mock_db, label_app, patch_label_get_database
    ):
        stored = [tagged_asset(id="asset-1", assetTag="IT-0001", tenantId="tenant-a")]
        _wire_find(mock_db, stored)
        patch_label_get_database("tenant-b")

        current_user = make_token_data(tenant_id="tenant-b", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            cross_tenant_resp = await ac.post(
                "/api/assets/labels/sheet", json={"assetIds": ["asset-1"]}
            )
            fabricated_resp = await ac.post(
                "/api/assets/labels/sheet", json={"assetIds": ["fabricated-id"]}
            )

        assert cross_tenant_resp.status_code == fabricated_resp.status_code == 400
        cross_detail = cross_tenant_resp.json()["detail"]
        fab_detail = fabricated_resp.json()["detail"]
        assert cross_detail["message"] == fab_detail["message"]
        assert set(cross_detail.keys()) == set(fab_detail.keys())
        assert cross_detail["unresolvedAssetIds"] == ["asset-1"]
        assert fab_detail["unresolvedAssetIds"] == ["fabricated-id"]
