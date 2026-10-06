"""
Agent identity (CSO findings c64a1e1d and 6973a589).

1. Agent JWTs are no longer user sessions: get_current_user rejects them,
   get_current_user_or_agent (opted into by the routes agents call) and the
   direct verify_token callers that serve agents still accept them.
2. POST /api/agents/register no longer hands an existing agent's identity to
   anyone holding the tenant registration key: re-enrolling a hostname needs
   the agent's secret, or (agents enrolled before secrets) a server-issued
   token for that exact agent. Hermetic — no Mongo.
"""
import os
import sys
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_registry_endpoints as reg
from authentication_service import (
    create_access_token,
    get_current_user,
    get_current_user_or_agent,
    verify_token,
)


@pytest.fixture(autouse=True)
def _restore_tenant_context():
    """verify_token/get_current_user set the ambient tenant context; restore it
    so later tests that assert an empty context are unaffected."""
    from tenant_context import _tenant_id_ctx
    token = _tenant_id_ctx.set(_tenant_id_ctx.get())
    yield
    _tenant_id_ctx.reset(token)


def _agent_token(agent_id="agent-1", tenant="tenant-a", expires=timedelta(days=90), **extra):
    data = {"sub": agent_id, "role": "agent", "tenant_id": tenant, **extra}
    return create_access_token(data=data, expires_delta=expires)


def _user_token():
    return create_access_token(data={"sub": "u@example.com", "role": "admin", "tenant_id": "tenant-a"})


# ── 1. agent tokens vs user sessions ────────────────────────────────────────

async def test_get_current_user_rejects_agent_token():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_agent_token())
    assert exc.value.status_code == 401


async def test_typ_claim_alone_marks_agent_token():
    token = create_access_token(data={"sub": "agent-1", "role": "user", "typ": "agent", "tenant_id": "tenant-a"})
    with pytest.raises(HTTPException):
        await get_current_user(token)


async def test_agent_routes_still_accept_agent_token():
    principal = await get_current_user_or_agent(_agent_token())
    assert principal.role == "agent" and principal.username == "agent-1"


async def test_user_token_unaffected():
    assert (await get_current_user(_user_token())).username == "u@example.com"


def test_sync_verify_token_defaults_to_accepting_agents_but_can_refuse():
    assert verify_token(_agent_token()).role == "agent"  # websocket registry path
    with pytest.raises(HTTPException):
        verify_token(_agent_token(), allow_agent=False)


# ── 2. re-registration needs proof of identity ──────────────────────────────

def _request(token=None):
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return Request({"type": "http", "method": "POST", "path": "/api/agents/register", "headers": headers})


def _db(revoked=False):
    db = MagicMock()
    db._db.revoked_tokens.find_one = AsyncMock(return_value={"_id": 1} if revoked else None)
    return db


SECRET = "s3cret-for-agent-1"
ENROLLED = {"id": "agent-1", "agentSecretHash": reg._hash_agent_secret(SECRET)}
LEGACY = {"id": "agent-1"}


async def test_matching_secret_proves_identity():
    assert await reg._proves_agent_identity(_db(), ENROLLED, "tenant-a", {"agentSecret": SECRET}, _request())


@pytest.mark.parametrize("data", [{}, {"agentSecret": "wrong"}, {"agentSecret": None}, {"previousToken": "x"}])
async def test_enrolled_agent_without_secret_is_refused(data):
    # Once a secret exists, even a valid token is not enough to re-enroll.
    data = {**data, "previousToken": _agent_token()} if data.get("previousToken") else data
    assert not await reg._proves_agent_identity(_db(), ENROLLED, "tenant-a", data, _request())


async def test_registration_key_alone_cannot_take_over_legacy_agent():
    assert not await reg._proves_agent_identity(_db(), LEGACY, "tenant-a", {"registrationKey": "k"}, _request())


async def test_legacy_agent_upgrades_with_its_own_token_even_if_expired():
    expired = _agent_token(expires=timedelta(seconds=-60))
    assert await reg._proves_agent_identity(_db(), LEGACY, "tenant-a", {"previousToken": expired}, _request())
    assert await reg._proves_agent_identity(_db(), LEGACY, "tenant-a", {}, _request(_agent_token()))


@pytest.mark.parametrize("token,tenant,revoked", [
    (lambda: _agent_token(agent_id="agent-2"), "tenant-a", False),   # another agent's token
    (lambda: _agent_token(tenant="tenant-b"), "tenant-a", False),    # other tenant
    (_user_token, "tenant-a", False),                               # a user session
    (lambda: _agent_token(), "tenant-a", True),                      # revoked
    (lambda: "not-a-jwt", "tenant-a", False),
])
async def test_legacy_upgrade_rejects_wrong_tokens(token, tenant, revoked):
    assert not await reg._proves_agent_identity(_db(revoked), LEGACY, tenant, {"previousToken": token()}, _request())


async def test_register_endpoint_returns_409_for_unproven_reenrollment():
    db = MagicMock()
    db.tenants.find_one = AsyncMock(return_value={"id": "tenant-a", "registrationKey": "k"})
    db.agents.find_one = AsyncMock(return_value=dict(ENROLLED, hostname="srv-1", tenantId="tenant-a"))
    db.agents.update_one = AsyncMock()
    with patch.object(reg, "get_database", return_value=db), patch.object(reg.limiter, "enabled", False):
        with pytest.raises(HTTPException) as exc:
            await reg.register_agent(_request(), MagicMock(), {"registrationKey": "k", "hostname": "srv-1"})
    assert exc.value.status_code == 409
    db.agents.update_one.assert_not_called()
