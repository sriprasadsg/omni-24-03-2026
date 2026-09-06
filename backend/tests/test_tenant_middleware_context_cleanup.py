"""Regression tests for ARCH-011 (2026-08-25 audit): TenantMiddleware must
clean up the tenant_id ContextVar for *every* request, not just the
Bearer-JWT branch.

Before this fix, TenantMiddleware only captured a reset token when it
itself resolved a tenant_id from a Bearer JWT. Two real leak paths existed:

1. Public paths (e.g. /api/auth/signup) return early, before any token was
   ever captured — but the signup handler itself calls
   set_tenant_id("platform-admin") with no reset of its own.
2. API-key-authenticated requests never carry an Authorization: Bearer
   header, so the middleware's own branch never ran at all — but
   get_current_user_or_api_key (a dependency invoked during call_next)
   calls set_tenant_id() with no reset of its own either.

In both cases the ContextVar was left holding a stale tenant_id for the
rest of the underlying asyncio Task's lifetime — visible to whatever
unrelated work reuses that task next. The fix: checkpoint the ContextVar's
pre-request value unconditionally, before the public-path/IP-ban early
returns, and reset to it exactly once in a finally wrapping the entire
dispatch — which also unwinds any set_tenant_id() call made deeper in the
stack during call_next, since contextvars.Token.reset() restores the value
captured at set() time regardless of how many further sets happened after.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import jwt as pyjwt
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tenant_middleware import TenantMiddleware
from tenant_context import get_tenant_id, set_tenant_id, reset_tenant_id
from authentication_service import SECRET_KEY, ALGORITHM


def _run(coro):
    return asyncio.run(coro)


def _make_request(path, headers=None, client_host="1.2.3.4"):
    req = MagicMock()
    req.url.path = path
    req.headers = headers or {}
    req.client = MagicMock(host=client_host)
    return req


def _jwt_for(tenant_id, role="user"):
    return pyjwt.encode({"tenant_id": tenant_id, "role": role, "sub": "u1"}, SECRET_KEY, algorithm=ALGORITHM)


@pytest.fixture(autouse=True)
def _clean_context():
    """Force a deterministic None baseline for each test regardless of
    whatever the rest of this large suite may have left in the (shared,
    process-wide) ContextVar — several other test files exercise code paths
    that call set_tenant_id() without resetting, which is exactly the class
    of bug this file is testing for — then restore whatever was ambient
    before this fixture ran."""
    outer_token = set_tenant_id(None)
    yield
    reset_tenant_id(outer_token)


class TestPublicPathLeakCleanup:

    def test_signup_style_leak_is_cleaned_up(self):
        """Simulates /api/auth/signup: a public path whose own handler calls
        set_tenant_id("platform-admin") with no reset of its own."""
        mw = TenantMiddleware(app=MagicMock())
        request = _make_request("/api/auth/signup")

        async def leaky_call_next(req):
            set_tenant_id("platform-admin")  # never reset by the handler itself
            return "signup-response"

        with patch("ip_ban_service.is_banned", new=AsyncMock(return_value=False)):
            result = _run(mw.dispatch(request, leaky_call_next))

        assert result == "signup-response"
        assert get_tenant_id() is None


class TestApiKeyPathLeakCleanup:

    def test_no_bearer_header_leak_is_cleaned_up(self):
        """Simulates an API-key-authenticated request: no Authorization:
        Bearer header at all, so the middleware's own JWT branch never
        runs — but get_current_user_or_api_key (invoked during call_next)
        calls set_tenant_id() with no reset of its own."""
        mw = TenantMiddleware(app=MagicMock())
        request = _make_request("/api/itam/licenses", headers={"X-API-Key": "sk-abc"})

        async def leaky_call_next(req):
            set_tenant_id("tenant-from-api-key")
            return "api-key-response"

        with patch("ip_ban_service.is_banned", new=AsyncMock(return_value=False)):
            result = _run(mw.dispatch(request, leaky_call_next))

        assert result == "api-key-response"
        assert get_tenant_id() is None


class TestBearerJwtPath:

    def test_tenant_id_visible_during_call_next_and_reset_after(self):
        mw = TenantMiddleware(app=MagicMock())
        token = _jwt_for("tenant-a")
        request = _make_request("/api/itam/licenses", headers={"Authorization": f"Bearer {token}"})

        seen = {}

        async def call_next(req):
            seen["tenant_id"] = get_tenant_id()
            return "ok"

        with patch("ip_ban_service.is_banned", new=AsyncMock(return_value=False)):
            result = _run(mw.dispatch(request, call_next))

        assert result == "ok"
        assert seen["tenant_id"] == "tenant-a"
        assert get_tenant_id() is None

    def test_context_reset_even_when_call_next_raises(self):
        mw = TenantMiddleware(app=MagicMock())
        token = _jwt_for("tenant-a")
        request = _make_request("/api/itam/licenses", headers={"Authorization": f"Bearer {token}"})

        async def boom(req):
            raise RuntimeError("downstream failure")

        with patch("ip_ban_service.is_banned", new=AsyncMock(return_value=False)):
            with pytest.raises(RuntimeError):
                _run(mw.dispatch(request, boom))

        assert get_tenant_id() is None

    def test_super_admin_tenant_override_header_still_works(self):
        mw = TenantMiddleware(app=MagicMock())
        token = _jwt_for("tenant-a", role="super_admin")
        request = _make_request(
            "/api/itam/licenses",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "tenant-b"},
        )

        seen = {}

        async def call_next(req):
            seen["tenant_id"] = get_tenant_id()
            return "ok"

        with patch("ip_ban_service.is_banned", new=AsyncMock(return_value=False)):
            _run(mw.dispatch(request, call_next))

        assert seen["tenant_id"] == "tenant-b"
        assert get_tenant_id() is None


class TestPreexistingContextRestored:

    def test_restores_prior_value_not_just_none(self):
        """If the ambient context already held a value before this request
        (e.g. a prior leak this fix is meant to prevent from compounding),
        the checkpoint must restore *that* value, not unconditionally wipe
        it to None."""
        mw = TenantMiddleware(app=MagicMock())
        stale_token = set_tenant_id("stale-leftover-tenant")
        try:
            request = _make_request("/api/auth/signup")

            async def call_next(req):
                return "ok"

            with patch("ip_ban_service.is_banned", new=AsyncMock(return_value=False)):
                _run(mw.dispatch(request, call_next))

            assert get_tenant_id() == "stale-leftover-tenant"
        finally:
            reset_tenant_id(stale_token)


class TestBannedIpStillBlocks:

    def test_banned_ip_returns_403_before_call_next(self):
        mw = TenantMiddleware(app=MagicMock())
        request = _make_request("/api/itam/licenses")
        call_next = AsyncMock(side_effect=AssertionError("must not reach call_next"))

        with patch("ip_ban_service.is_banned", new=AsyncMock(return_value=True)):
            response = _run(mw.dispatch(request, call_next))

        assert response.status_code == 403
        call_next.assert_not_called()
        assert get_tenant_id() is None
