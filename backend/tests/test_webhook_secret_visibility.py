"""
GET /api/webhooks needs only a login, so it must never return the HMAC signing
secret: a read-only tenant user could otherwise forge signed deliveries to the
tenant's receivers (CSO run 1791369231841-4b97a042b01547a9, finding 48b0dfb9).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import webhook_endpoints
from auth_types import TokenData

_HOOK = {
    "id": "wh-1", "name": "soar", "url": "https://soar.example.com/hook",
    "secret": "whsec_do_not_leak", "tenantId": "t1", "status": "Active",
}


def _project(doc, projection):
    hidden = {k for k, v in (projection or {}).items() if v == 0}
    return {k: v for k, v in doc.items() if k not in hidden}


def _db_with(doc):
    db = MagicMock()
    cursor = MagicMock()
    db.webhooks.find = MagicMock(
        side_effect=lambda q, proj=None: (
            setattr(cursor, "to_list", AsyncMock(return_value=[_project(doc, proj)])) or cursor
        )
    )
    db.webhooks.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    db.webhooks.find_one = AsyncMock(side_effect=lambda q, proj=None: _project(doc, proj))
    return db


@pytest.mark.asyncio
async def test_list_hides_signing_secret_from_viewer():
    viewer = TokenData(username="analyst@t1.test", role="viewer", tenant_id="t1")
    with patch.object(webhook_endpoints, "get_database", return_value=_db_with(_HOOK)):
        hooks = await webhook_endpoints.get_webhooks(current_user=viewer)
    assert hooks and hooks[0]["id"] == "wh-1"
    assert "secret" not in hooks[0]


@pytest.mark.asyncio
async def test_update_response_hides_signing_secret():
    admin = TokenData(username="admin@t1.test", role="admin", tenant_id="t1")
    with patch.object(webhook_endpoints, "get_database", return_value=_db_with(_HOOK)):
        updated = await webhook_endpoints.update_webhook("wh-1", {"name": "soar-2"}, current_user=admin)
    assert "secret" not in updated


@pytest.mark.asyncio
async def test_create_still_returns_secret_once():
    admin = TokenData(username="admin@t1.test", role="admin", tenant_id="t1")
    db = MagicMock()
    db.webhooks.insert_one = AsyncMock()
    with patch.object(webhook_endpoints, "get_database", return_value=db), \
         patch.object(webhook_endpoints, "verify_permission", AsyncMock(return_value=True)), \
         patch.object(webhook_endpoints, "_is_safe_webhook_url", return_value=True):
        created = await webhook_endpoints.create_webhook(
            {"name": "soar", "url": "https://soar.example.com/hook"}, current_user=admin
        )
    assert created["secret"].startswith("whsec_")
