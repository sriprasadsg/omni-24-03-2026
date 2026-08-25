"""
Regression test for CRIT-01: a refresh token (no tenant_id/role claim by
design — see create_refresh_token) must never be accepted by verify_token /
verify_token_async, and a token with a missing tenant_id claim must never be
silently escalated to the "platform-admin" tenant-isolation-bypass sentinel.

Pre-fix, both functions did `_set_tenant_id(tenant_id or "platform-admin")`
with no check of the JWT "type" claim, so any user's own refresh token —
which sits in their browser's sessionStorage for 7 days — could be replayed
as a Bearer access token against any Depends(get_current_user)-only endpoint
and receive full cross-tenant database access.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

import authentication_service as auth_service
from authentication_service import (
    create_access_token,
    create_refresh_token,
    verify_token,
    verify_token_async,
)


def test_refresh_token_rejected_by_sync_verify_token():
    refresh = create_refresh_token(data={"sub": "user@example.com"})
    with pytest.raises(HTTPException) as exc_info:
        verify_token(refresh)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rejected_by_async_verify_token():
    refresh = create_refresh_token(data={"sub": "user@example.com"})
    with pytest.raises(HTTPException) as exc_info:
        await verify_token_async(refresh)
    assert exc_info.value.status_code == 401


def test_access_token_missing_tenant_id_rejected_not_escalated():
    # An access token with no tenant_id claim at all (e.g. a malformed or
    # legacy token) must be rejected outright, never defaulted to
    # "platform-admin".
    token = create_access_token(data={"sub": "user@example.com", "role": "user"})
    with pytest.raises(HTTPException) as exc_info:
        verify_token(token)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_access_token_missing_tenant_id_rejected_not_escalated_async():
    token = create_access_token(data={"sub": "user@example.com", "role": "user"})
    with pytest.raises(HTTPException) as exc_info:
        await verify_token_async(token)
    assert exc_info.value.status_code == 401


def test_valid_access_token_with_tenant_id_still_works():
    token = create_access_token(
        data={"sub": "user@example.com", "role": "user", "tenant_id": "tenant-a"}
    )
    token_data = verify_token(token)
    assert token_data.tenant_id == "tenant-a"
    assert token_data.username == "user@example.com"


@pytest.mark.asyncio
async def test_valid_access_token_with_tenant_id_still_works_async(monkeypatch):
    # verify_token_async does a DB revocation lookup keyed on jti; patch
    # get_database so this test exercises real token-decoding logic without
    # needing a live database.
    from unittest.mock import AsyncMock, MagicMock

    fake_db = MagicMock()
    fake_db._db.revoked_tokens.find_one = AsyncMock(return_value=None)
    fake_cursor = MagicMock()
    fake_cursor.limit.return_value.__aiter__ = lambda self: iter([])
    fake_db._db.revoked_tokens.find.return_value = fake_cursor
    monkeypatch.setattr("authentication_service.get_database", lambda: fake_db, raising=False)

    import database
    monkeypatch.setattr(database, "get_database", lambda: fake_db)

    token = create_access_token(
        data={"sub": "user@example.com", "role": "user", "tenant_id": "tenant-a"}
    )
    token_data = await verify_token_async(token)
    assert token_data.tenant_id == "tenant-a"


def test_explicit_platform_admin_tenant_id_still_accepted():
    # The real Super Admin path: tenant_id is an EXPLICIT claim on the
    # token (app_startup.py seeds the Super Admin user with
    # tenantId="platform-admin" and login copies it onto the token
    # verbatim) — this must keep working. Only an ABSENT tenant_id claim
    # should be rejected, not an explicit "platform-admin" value.
    token = create_access_token(
        data={"sub": "admin@example.com", "role": "Super Admin", "tenant_id": "platform-admin"}
    )
    token_data = verify_token(token)
    assert token_data.tenant_id == "platform-admin"
