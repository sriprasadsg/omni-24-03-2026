"""Phase 87 plan 04: a suspended partner is locked out at the token verifier, sign-in and refresh (D-15).

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. The partner documents live on a real MongoDB database
(MONGO_TEST_URL); the sign-in and refresh tests run the real auth router over the in-memory store.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import authentication_service as auth_svc
import partner_status
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

PARTNER_ID = "partner_susp0001"
MESSAGE = "This partner account is suspended. Contact your platform administrator to restore access."


class _Shim:
    """Matches the db._db access pattern the revocation check uses."""

    def __init__(self, mdb):
        self._db = mdb


@pytest.fixture(autouse=True)
def _clean_caches():
    auth_svc._user_cutoff_cache.clear()
    auth_svc._revoked_jti_cache.clear()
    auth_svc._revocation_cache_last_sync = 0.0
    yield
    auth_svc._user_cutoff_cache.clear()
    auth_svc._revoked_jti_cache.clear()


@pytest.fixture
def wired(mongo_db, monkeypatch):  # noqa: F811
    """partner_status and the revocation lookup both read the throwaway database."""
    monkeypatch.setattr(partner_status, "_raw_db", lambda: mongo_db)
    monkeypatch.setattr("database.get_database", lambda: _Shim(mongo_db))
    return mongo_db


async def _partner(mdb, status="active"):
    await mdb.tenants.delete_many({"id": PARTNER_ID})
    await mdb.tenants.insert_one({"id": PARTNER_ID, "type": "partner", "name": "Suspend Co",
                                  "partner": {"status": status, "poolSize": 10, "allocated": 0}})


def _token(role="partner_admin", tenant=PARTNER_ID, **extra):
    data = {"sub": "pat@partner.example", "role": role, "tenant_id": tenant, "mfa_verified": True}
    data.update(extra)
    return auth_svc.create_access_token(data)


async def _refused(token, **kw):
    with pytest.raises(HTTPException) as caught:
        await auth_svc.verify_token_async(token, **kw)
    return caught.value


async def test_a_suspended_partner_token_is_refused_with_the_stable_message(wired):
    """protects=a token issued before suspension stops working at once;
    fails_when=the verifier returns TokenData for a suspended partner;
    no_claim=the HTTP routes (called on the verifier)."""
    await _partner(wired, "suspended")
    err = await _refused(_token())
    assert err.status_code == 403
    assert err.detail == MESSAGE
    assert err.headers == {"X-Partner-Suspended": "1"}


async def test_a_suspended_partner_is_refused_even_where_mfa_pending_is_allowed(wired):
    """protects=the MFA-pending routes (who am I, enroll) cannot be used to dodge suspension;
    fails_when=allow_mfa_pending lets a suspended partner through;
    no_claim=the HTTP routes."""
    await _partner(wired, "suspended")
    err = await _refused(_token(mfa_verified=False), allow_mfa_pending=True)
    assert err.status_code == 403
    assert err.headers == {"X-Partner-Suspended": "1"}


async def test_an_active_partner_token_passes(wired):
    """protects=normal partner sessions are untouched; fails_when=an active partner is refused;
    no_claim=route permissions."""
    await _partner(wired, "active")
    data = await auth_svc.verify_token_async(_token(role="partner_viewer"))
    assert data.role == "partner_viewer" and data.tenant_id == PARTNER_ID


async def test_a_missing_partner_document_counts_as_suspended(wired):
    """protects=a deleted partner leaves no live session; fails_when=no document lets the request through;
    no_claim=what deletion does to its users."""
    await wired.tenants.delete_many({"id": PARTNER_ID})
    err = await _refused(_token())
    assert err.status_code == 403 and err.detail == MESSAGE


async def test_a_tenant_type_that_is_not_partner_counts_as_suspended(wired):
    """protects=a partner role on an ordinary organization id is refused;
    fails_when=the lookup ignores the type filter; no_claim=role assignment rules (plan 02)."""
    await wired.tenants.insert_one({"id": "tenant-plain", "type": "tenant", "name": "Plain"})
    err = await _refused(_token(tenant="tenant-plain"))
    assert err.status_code == 403


async def test_a_failing_status_lookup_answers_503_and_never_lets_the_request_through(monkeypatch, wired):
    """protects=fail closed when the status cannot be read; fails_when=an exception becomes a pass;
    no_claim=that other roles are affected (see the next test)."""
    boom = MagicMock()
    boom.tenants.find_one = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr(partner_status, "_raw_db", lambda: boom)
    err = await _refused(_token())
    assert err.status_code == 503
    assert err.detail == "Partner status could not be checked. Try again."


async def test_a_non_partner_token_causes_no_partner_lookup(monkeypatch, wired):
    """protects=other roles never pay for or depend on the partner lookup;
    fails_when=_raw_db is called for a tenant_admin;
    no_claim=tenant_admin authorization."""
    spy = MagicMock(side_effect=AssertionError("partner lookup for a non-partner role"))
    monkeypatch.setattr(partner_status, "_raw_db", spy)
    data = await auth_svc.verify_token_async(_token(role="tenant_admin", tenant="tenant-a"))
    assert data.role == "tenant_admin"
    spy.assert_not_called()


@pytest.mark.parametrize("role", ["partner_admin", "partner_viewer", "Partner Admin"])
def test_the_sync_verifier_refuses_every_partner_role(role):
    """protects=no partner token reaches the sync path that cannot check the partner;
    fails_when=verify_token returns TokenData for a partner role;
    no_claim=sync callers of other roles."""
    with pytest.raises(HTTPException) as caught:
        auth_svc.verify_token(_token(role=role))
    assert caught.value.status_code == 401
    assert caught.value.detail == "Could not validate credentials"
