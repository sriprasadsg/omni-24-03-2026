"""
Tests for webhook_service.py outbound HMAC-SHA256 signing (Plan 33-02).

Covers:
  - X-Webhook-Signature is computed over the EXACT bytes sent via content= (T-33-BYTES)
  - a hook without a secret still delivers, unsigned, without error
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import hashlib
import hmac
import pytest
from unittest.mock import AsyncMock, MagicMock

from webhook_service import WebhookService


def _delivery_db():
    db = MagicMock()
    db.webhooks.update_one = AsyncMock()
    return db


def _client_with_response(status_code=200):
    client = MagicMock()
    client.post = AsyncMock(return_value=MagicMock(status_code=status_code))
    return client


@pytest.mark.asyncio
async def test_signature_covers_exact_wire_bytes():
    service = WebhookService()
    client = _client_with_response()
    hook = {"id": "wh-1", "url": "https://example.com/hook", "secret": "whsec_test"}
    payload = {"event": "grc.event", "timestamp": "2026-07-13T00:00:00", "data": {"a": 1}}

    await service._send_single_webhook(client, hook, payload, _delivery_db())

    assert client.post.await_count == 1
    args, kwargs = client.post.call_args
    assert "json" not in kwargs, "must not use httpx json= (re-serializes independently of the signature)"
    assert "content" in kwargs
    captured_body = kwargs["content"]
    expected = "sha256=" + hmac.new(
        b"whsec_test", captured_body.encode(), hashlib.sha256
    ).hexdigest()
    assert kwargs["headers"]["X-Webhook-Signature"] == expected


@pytest.mark.asyncio
async def test_signature_absent_when_hook_has_no_secret():
    service = WebhookService()
    client = _client_with_response()
    hook = {"id": "wh-2", "url": "https://example.com/hook"}
    payload = {"event": "grc.event", "data": {}}

    await service._send_single_webhook(client, hook, payload, _delivery_db())

    assert client.post.await_count == 1
    _args, kwargs = client.post.call_args
    assert "content" in kwargs
    assert "X-Webhook-Signature" not in kwargs["headers"]
