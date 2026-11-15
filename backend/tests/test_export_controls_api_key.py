"""ExportControlMiddleware for API-key callers (Phase 86 review WR-01): an export authenticated by X-API-Key
gets the same daily allowance, usage record, audit event and bulk-export check as one by a bearer token."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import api_key_auth
import export_controls
from auth_types import TokenData

EXPORT = "/api/autonomous-ops/export"
OWNER = TokenData(username="owner@example.test", role="tenant_admin", tenant_id="t1")


def _scope(headers, path=EXPORT):
    return {"type": "http", "method": "GET", "path": path, "headers": headers}


async def _run(scope, status=200, body=b"a,b\n1,2\n"):
    sent, routed = [], []

    async def route(scope, receive, send):
        routed.append(True)
        await send({"type": "http.response.start", "status": status, "headers": [(b"x-export-rows", b"3")]})
        await send({"type": "http.response.body", "body": body})

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


async def test_an_empty_export_uses_no_allowance_and_is_not_audited(controls):
    """Review IN-03: a 204 (nothing matched) hands nothing out."""
    sent, routed = await _run(_scope([(b"x-api-key", b"omni_key")]), status=204, body=b"")

    assert routed and sent[0]["status"] == 204
    controls.assert_not_awaited()


async def test_a_request_with_neither_credential_passes_through(controls):
    sent, routed = await _run(_scope([]))

    assert routed
    controls.assert_not_awaited()


@pytest.mark.parametrize("path", [EXPORT, "/api/reports/export"])
@pytest.mark.parametrize("authorization", [b"Bearer not-a-jwt", b"Bearer aaa.bbb.ccc", b"Basic dTpw"])
async def test_a_request_with_both_credentials_is_refused_before_the_route(controls, path, authorization):
    """Eng review R1: export routes differ in the credential they accept (most take a bearer token only), so a
    request that sends both cannot be attributed the way its route will authenticate it. A junk bearer header
    beside a valid key used to pass uncounted."""
    sent, routed = await _run(_scope([(b"authorization", authorization), (b"x-api-key", b"omni_key")], path))

    assert not routed and sent[0]["status"] == 400
    assert json.loads(sent[1]["body"])["detail"] == export_controls.BOTH_CREDENTIALS
    controls.assert_not_awaited()
    api_key_auth.resolve_api_key.assert_not_awaited()


async def test_a_blank_api_key_header_beside_a_bearer_token_is_not_refused(controls):
    sent, routed = await _run(_scope([(b"authorization", b"Bearer not-a-jwt"), (b"x-api-key", b"  ")]))

    assert routed and sent[0]["status"] == 200   # the route answers; a junk bearer names no caller to charge
    controls.assert_not_awaited()


async def test_the_limiter_identifies_the_key_without_spending_its_rate_limit(controls):
    """Eng review R7: the route's own lookup counts the request and stamps the use; the limiter's must not."""
    await _run(_scope([(b"x-api-key", b"omni_key")]))

    api_key_auth.resolve_api_key.assert_awaited_once_with("omni_key", touch=False)


async def test_a_validity_only_lookup_counts_no_unit_and_writes_nothing(monkeypatch):
    """R7 at the source: touch=False identifies a key, even one over its rate limit, and stamps no use."""
    key = {"id": "k1", "keyPrefix": "omni_abcdefg", "keyHash": "h", "rateLimit": 1}
    owner = {"email": "owner@example.test", "role": "tenant_admin", "tenantId": "t1", "apiKeys": [key]}
    users = SimpleNamespace(find_one=AsyncMock(return_value=owner), update_one=AsyncMock())
    monkeypatch.setattr(api_key_auth, "mongodb", SimpleNamespace(db=SimpleNamespace(users=users)))
    monkeypatch.setattr(api_key_auth, "verify_password", lambda *_: True)
    monkeypatch.setattr(api_key_auth.APIKeyService, "_to_model", lambda self, doc: doc)
    monkeypatch.setitem(api_key_auth._usage_windows, "k1", type(api_key_auth._usage_windows["k1"])())
    service, secret = api_key_auth.APIKeyService(), "omni_abcdefghijkl"

    for _ in range(3):
        assert (await service._validate_and_touch(secret, touch=False))["owner_email"] == "owner@example.test"
    users.update_one.assert_not_awaited()
    assert len(api_key_auth._usage_windows["k1"]) == 0

    assert await service._validate_and_touch(secret) is not None            # the route's lookup: the one unit
    assert users.update_one.await_count == 1
    with pytest.raises(HTTPException) as refused:
        await service._validate_and_touch(secret)
    assert refused.value.status_code == 429
    assert (await service._validate_and_touch(secret, touch=False))["owner_email"] == "owner@example.test"
