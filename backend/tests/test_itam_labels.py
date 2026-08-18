"""ITAM Labels tests — Phase 58.

Plan 01, Task 1: "print a QR label for one asset" end-to-end.
Plan 01, Task 2: payload fidelity, missing tag, RBAC, and cross-tenant
hardening (TestQrPayloadFidelity, TestQrLabelMissingTag, TestQrLabelRbac,
TestQrLabelTenantIsolation).

Shared mock DB/fixtures live in itam_label_test_support.py (split out to keep
this file under the CLAUDE.md 500-line limit).
"""
import io
import sys
import os
from unittest.mock import AsyncMock

import pytest
import qrcode
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
from api_key_auth import get_current_user_or_api_key  # Phase 73 (D-01/D-02): routes gated by _require_itam_admin now resolve through this dependency, not get_current_user
from itam_label_service import LabelEncodingError, generate_qr_png


def _reference_qr_png(payload: str) -> bytes:
    """Build a reference QR render with the exact params generate_qr_png uses,
    without importing anything from itam_label_service — pins D-02 independently."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestQrLabelRouteEndToEnd:
    """Task 1 — end-to-end 'print a QR label for one asset', one path only."""

    @pytest.mark.asyncio
    async def test_qr_generation_route_end_to_end(self, mock_db, label_app):
        mock_db.assets.find_one = AsyncMock(return_value=tagged_asset())

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/qr")

        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("image/png")
        assert r.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert "IT-0001" in r.headers["content-disposition"]


class TestQrPayloadFidelity:
    """Task 2 — unit-level, no app: pins D-02's bare-tag QR payload."""

    def test_qr_payload_matches_bare_tag_reference(self):
        assert generate_qr_png("IT-0001") == _reference_qr_png("IT-0001")

    def test_qr_payload_differs_from_url_wrapped_tag(self):
        url_wrapped = _reference_qr_png("https://example.com/assets/IT-0001")
        assert generate_qr_png("IT-0001") != url_wrapped

    def test_qr_payload_is_deterministic_across_calls(self):
        first = generate_qr_png("IT-0001")
        second = generate_qr_png("IT-0001")
        assert first == second

    def test_qr_payload_raises_on_empty_tag(self):
        with pytest.raises(LabelEncodingError):
            generate_qr_png("")

    def test_qr_payload_raises_on_non_string_tag(self):
        with pytest.raises(LabelEncodingError):
            generate_qr_png(None)


class TestQrLabelMissingTag:
    """Task 2 — an asset that resolves but carries no assetTag returns 400."""

    @pytest.mark.asyncio
    async def test_missing_tag_returns_400_naming_asset_tag(self, mock_db, label_app):
        asset_without_tag = tagged_asset()
        asset_without_tag.pop("assetTag")
        mock_db.assets.find_one = AsyncMock(return_value=asset_without_tag)

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/qr")

        assert r.status_code == 400, r.text
        assert "assetTag" in r.text


class TestQrLabelRbac:
    """Task 2 — a caller without manage:assets receives 403 (T-58-04)."""

    @pytest.mark.asyncio
    async def test_qr_route_denied_without_manage_assets(self, mock_db, label_app, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))
        mock_db.assets.find_one = AsyncMock(return_value=tagged_asset())

        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/qr")

        assert r.status_code == 403, r.text


class TestQrLabelTenantIsolation:
    """Task 2 — a cross-tenant asset id is indistinguishable from an unknown one
    (T-58-01), and a sanitized filename never carries a header-control character
    from the raw tag (T-58-05)."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_cross_tenant_asset_returns_404(self, mock_db, label_app, patch_label_get_database):
        # Only a tenant-a document exists; the tenantId-injecting mock collection
        # resolves nothing when the effective filter (with tenantId="tenant-b"
        # injected) is applied against it.
        stored = [tagged_asset()]
        mock_db.assets.find_one = AsyncMock(side_effect=lambda f, *a, **kw:
            next((d for d in stored if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id")), None))
        patch_label_get_database("tenant-b")

        current_user = make_token_data(tenant_id="tenant-b", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/qr")

        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_tenant_isolation_cross_tenant_404_matches_unknown_id_404(self, mock_db, label_app, patch_label_get_database):
        stored = [tagged_asset()]
        mock_db.assets.find_one = AsyncMock(side_effect=lambda f, *a, **kw:
            next((d for d in stored if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id")), None))
        patch_label_get_database("tenant-b")

        current_user = make_token_data(tenant_id="tenant-b", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            cross_tenant_resp = await ac.get("/api/assets/asset-1/label/qr")
            unknown_id_resp = await ac.get("/api/assets/does-not-exist/label/qr")

        assert cross_tenant_resp.status_code == unknown_id_resp.status_code == 404
        assert cross_tenant_resp.text == unknown_id_resp.text

    @pytest.mark.asyncio
    async def test_tenant_isolation_filename_sanitized_for_unsafe_characters(self, mock_db, label_app):
        unsafe_tag = "IT-0001\r\nX-Injected: true"
        mock_db.assets.find_one = AsyncMock(return_value=tagged_asset(assetTag=unsafe_tag))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/qr")

        assert r.status_code == 200, r.text
        content_disposition = r.headers["content-disposition"]
        assert "\r" not in content_disposition
        assert "\n" not in content_disposition
        filename_value = content_disposition.split("filename=", 1)[1]
        for ch in unsafe_tag:
            if ch not in "IT-0001" and not ch.isalnum():
                assert ch not in filename_value
