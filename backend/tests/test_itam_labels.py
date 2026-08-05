"""ITAM Labels tests — Phase 58.

Plan 01, Task 1: "print a QR label for one asset" end-to-end.
Plan 01, Task 2: payload fidelity, missing tag, RBAC, and cross-tenant
hardening (TestQrPayloadFidelity, TestQrLabelMissingTag, TestQrLabelRbac,
TestQrLabelTenantIsolation).

Shared mock DB/fixtures live in itam_label_test_support.py (split out to keep
this file under the CLAUDE.md 500-line limit).
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


class TestQrLabelRouteEndToEnd:
    """Task 1 — end-to-end 'print a QR label for one asset', one path only."""

    @pytest.mark.asyncio
    async def test_qr_generation_route_end_to_end(self, mock_db, label_app):
        mock_db.assets.find_one = AsyncMock(return_value=tagged_asset())

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        label_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=label_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/label/qr")

        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("image/png")
        assert r.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert "IT-0001" in r.headers["content-disposition"]
