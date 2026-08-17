"""ITAM Labels barcode tests — Phase 58 Plan 03, Task 1.

Code128 1D barcode generation (generate_barcode_png) and its route
(GET /api/assets/{asset_id}/label/barcode), mirroring test_itam_labels.py's
QR-equivalent test classes.

Shared mock DB/fixtures live in itam_label_test_support.py.
"""
import sys
import os
from unittest.mock import AsyncMock

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

from authentication_service import get_current_user as real_get_current_user
from itam_label_service import LabelEncodingError, generate_barcode_png

# Candidate chosen at test-authoring time by attempting generate_barcode_png
# on several non-ASCII / control-character candidates and keeping the first
# one that actually raised. python-barcode's Code128 class rejects any
# character outside its own supported set (verified live against the
# installed 0.16.1 wheel — 'é' raises IllegalCharacterError, e.g.
# generate_barcode_png("IT-000é") -> "not valid for Code 128: é"). Hard-coded
# here rather than driven by a hand-written allowlist, so the library stays
# the authority on encodability.
_UNENCODABLE_TAG = "IT-000é"


class TestBarcodeGeneration:
    """Unit, no app: PNG signature, determinism, LabelEncodingError cases."""

    def test_barcode_generation_returns_png_signature(self):
        png = generate_barcode_png("IT-0001")
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(png) > 100

    def test_barcode_generation_is_deterministic(self):
        first = generate_barcode_png("IT-0001")
        second = generate_barcode_png("IT-0001")
        assert first == second

    def test_barcode_generation_raises_on_empty_tag(self):
        with pytest.raises(LabelEncodingError):
            generate_barcode_png("")

    def test_barcode_generation_raises_on_none_tag(self):
        with pytest.raises(LabelEncodingError):
            generate_barcode_png(None)

    def test_barcode_generation_raises_on_non_string_tag(self):
        with pytest.raises(LabelEncodingError):
            generate_barcode_png(123)

    def test_barcode_generation_raises_on_unencodable_characters(self):
        with pytest.raises(LabelEncodingError):
            generate_barcode_png(_UNENCODABLE_TAG)


class TestBarcodeInvalidTag:
    """Route-level: 400 for missing tag and 400 for unencodable tag — and
    specifically NOT 500, which is the whole point of this test class."""

    @pytest.mark.asyncio
    async def test_barcode_invalid_tag_missing_returns_400_not_500(self, mock_db, label_app):
        asset_without_tag = tagged_asset()
        asset_without_tag.pop("assetTag")
        mock_db.assets.find_one = AsyncMock(return_value=asset_without_tag)

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/barcode")

        assert r.status_code == 400, r.text
        assert r.status_code != 500
        assert "assetTag" in r.text

    @pytest.mark.asyncio
    async def test_barcode_invalid_tag_unencodable_returns_400_not_500(self, mock_db, label_app):
        mock_db.assets.find_one = AsyncMock(return_value=tagged_asset(assetTag=_UNENCODABLE_TAG))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/barcode")

        assert r.status_code == 400, r.text
        assert r.status_code != 500
        # No response body that could be mistaken for image bytes.
        assert not r.content.startswith(b"\x89PNG\r\n\x1a\n")


class TestBarcodeRouteEndToEnd:
    """200 + PNG signature + content-disposition, mirroring the QR route's
    end-to-end test — selectable with -k barcode_generation."""

    @pytest.mark.asyncio
    async def test_barcode_generation_route_end_to_end(self, mock_db, label_app):
        mock_db.assets.find_one = AsyncMock(return_value=tagged_asset())

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/barcode")

        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("image/png")
        assert r.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert "IT-0001" in r.headers["content-disposition"]


class TestBarcodeRbac:
    """A caller without manage:assets receives 403 (T-58-04)."""

    @pytest.mark.asyncio
    async def test_barcode_rbac_denied_without_manage_assets(self, mock_db, label_app, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))
        mock_db.assets.find_one = AsyncMock(return_value=tagged_asset())

        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/barcode")

        assert r.status_code == 403, r.text


class TestBarcodeTenantIsolation:
    """A cross-tenant asset id is indistinguishable from an unknown one
    (T-58-01), matching the QR route's identical guarantee."""

    @pytest.mark.asyncio
    async def test_barcode_tenant_isolation_cross_tenant_asset_returns_404(
        self, mock_db, label_app, patch_label_get_database
    ):
        stored = [tagged_asset()]
        mock_db.assets.find_one = AsyncMock(side_effect=lambda f, *a, **kw:
            next((d for d in stored if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id")), None))
        patch_label_get_database("tenant-b")

        current_user = make_token_data(tenant_id="tenant-b", role="admin", username="admin@example.com")
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/barcode")

        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_barcode_tenant_isolation_404_matches_unknown_id_404(
        self, mock_db, label_app, patch_label_get_database
    ):
        stored = [tagged_asset()]
        mock_db.assets.find_one = AsyncMock(side_effect=lambda f, *a, **kw:
            next((d for d in stored if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id")), None))
        patch_label_get_database("tenant-b")

        current_user = make_token_data(tenant_id="tenant-b", role="admin", username="admin@example.com")
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            cross_tenant_resp = await ac.get("/api/assets/asset-1/label/barcode")
            unknown_id_resp = await ac.get("/api/assets/does-not-exist/label/barcode")

        assert cross_tenant_resp.status_code == unknown_id_resp.status_code == 404
        assert cross_tenant_resp.text == unknown_id_resp.text
