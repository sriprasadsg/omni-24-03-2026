"""ExportControlMiddleware for API-key callers (Phase 86 review WR-01): an export authenticated by X-API-Key
gets the same daily allowance, usage record, audit event and bulk-export check as one by a bearer token."""
from unittest.mock import AsyncMock

import pytest

import api_key_auth
import export_controls
from auth_types import TokenData

EXPORT = "/api/autonomous-ops/export"
OWNER = TokenData(username="owner@example.test", role="tenant_admin", tenant_id="t1")


def _scope(headers):
    return {"type": "http", "method": "GET", "path": EXPORT, "headers": headers}


async def _run(scope):
    sent, routed = [], []

    async def route(scope, receive, send):
        routed.append(True)
        await send({"type": "http.response.start", "status": 200, "headers": [(b"x-export-rows", b"3")]})
        await send({"type": "http.response.body", "body": b"a,b\n1,2\n"})

    async def send(message):
        sent.append(message)

    await export_controls.ExportControlMiddleware(route)(scope, None, send)
    return sent, routed


@pytest.fixture
def controls(monkeypatch):
    record = AsyncMock()
    monkeypatch.setattr(export_controls, "_usage", AsyncMock(return_value={}))
    monkeypatch.setattr(export_controls, "_record", record)
    monkeypatch.setattr(api_key_auth, "resolve_api_key", AsyncMock(return_value=OWNER))
    return record


async def test_an_api_key_export_is_recorded_under_the_key_owner(controls):
    sent, routed = await _run(_scope([(b"x-api-key", b"omni_key")]))

    assert routed and sent[0]["status"] == 200
    who, path, size, rows, _ = controls.await_args.args
    assert (who["email"], who["tenantId"], path, size, rows) == ("owner@example.test", "t1", EXPORT, 8, 3)


async def test_an_api_key_export_past_the_daily_allowance_answers_429(controls, monkeypatch):
    monkeypatch.setattr(export_controls, "_usage", AsyncMock(return_value={"count": export_controls.DAILY_EXPORTS}))

    sent, routed = await _run(_scope([(b"x-api-key", b"omni_key")]))

    assert not routed and sent[0]["status"] == 429
    controls.assert_not_awaited()


async def test_an_invalid_api_key_is_left_for_the_route_to_refuse(controls, monkeypatch):
    monkeypatch.setattr(api_key_auth, "resolve_api_key", AsyncMock(return_value=None))

    sent, routed = await _run(_scope([(b"x-api-key", b"not-a-key")]))

    assert routed and sent[0]["status"] == 200
    controls.assert_not_awaited()


async def test_a_failed_key_lookup_never_fails_the_request(controls, monkeypatch):
    monkeypatch.setattr(api_key_auth, "resolve_api_key", AsyncMock(side_effect=RuntimeError("db down")))

    sent, routed = await _run(_scope([(b"x-api-key", b"omni_key")]))

    assert routed and sent[0]["status"] == 200
    controls.assert_not_awaited()


async def test_a_request_with_neither_credential_passes_through(controls):
    sent, routed = await _run(_scope([]))

    assert routed
    controls.assert_not_awaited()
