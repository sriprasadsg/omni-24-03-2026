"""
Regression tests for the SSRF fixes (2026-08-25 audit):
- ticket_webhook_service.py had zero URL validation at all.
- webhook_endpoints.py validated on create but never on update, and never
  re-validated immediately before dispatch (test_webhook / dispatch_event).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

import ticket_webhook_service


@pytest.mark.asyncio
async def test_register_webhook_rejects_internal_url():
    with patch("ticket_webhook_service.mongodb") as mock_mongodb:
        mock_mongodb.db.ticket_webhooks.insert_one = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await ticket_webhook_service.register_webhook(
                "tenant-a", "http://169.254.169.254/latest/meta-data/", ["ticket.created"]
            )
        assert exc_info.value.status_code == 400
        mock_mongodb.db.ticket_webhooks.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_webhook_accepts_public_url():
    with patch("ticket_webhook_service.mongodb") as mock_mongodb, \
         patch("ticket_webhook_service.is_safe_webhook_url", return_value=True):
        mock_mongodb.db.ticket_webhooks.insert_one = AsyncMock()
        hook = await ticket_webhook_service.register_webhook(
            "tenant-a", "https://example.com/hook", ["ticket.created"]
        )
        assert hook["url"] == "https://example.com/hook"
        mock_mongodb.db.ticket_webhooks.insert_one.assert_awaited()


@pytest.mark.asyncio
async def test_dispatch_event_skips_hook_that_fails_revalidation():
    """A hook that was somehow stored with a bad URL (e.g. registered before
    this fix) must not be dispatched to, even though it's still active."""
    bad_hook = {"id": "h1", "url": "http://127.0.0.1:9999/x", "secret": ""}
    with patch("ticket_webhook_service.mongodb") as mock_mongodb, \
         patch("ticket_webhook_service.is_safe_webhook_url", return_value=False), \
         patch("ticket_webhook_service.httpx.AsyncClient") as mock_client_cls:
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[bad_hook])
        mock_mongodb.db.ticket_webhooks.find.return_value = cursor

        await ticket_webhook_service.dispatch_event("tenant-a", "ticket.created", {})

        mock_client_cls.assert_not_called()
