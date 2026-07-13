"""Phase 34 tests — Passkey (WebAuthn) service functions.

Exercises the challenge lifecycle and credential persistence with the
webauthn library calls mocked (no real authenticator in CI).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import database
import passkey_service as svc


def _mock_mongo_db():
    db = MagicMock()
    db.users.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    db.users.find_one = AsyncMock(return_value=None)
    return db


async def test_build_registration_options():
    """Options come from webauthn lib; challenge is stored for later verify."""
    fake_options = MagicMock(name="registration_options")
    with patch.object(svc.webauthn, "generate_registration_options", MagicMock(return_value=fake_options)) as gen, \
         patch.object(svc, "store_challenge", MagicMock()) as store:
        options = await svc.build_registration_options("user-123", "test@user.com", "Test User")

    assert options is fake_options
    store.assert_called_once()
    user_key, challenge_type, challenge = store.call_args.args
    assert user_key == "user-123"
    assert challenge_type == "registration"
    assert isinstance(challenge, bytes) and len(challenge) == 32
    # the same challenge must be handed to the webauthn lib
    assert gen.call_args.kwargs["challenge"] == challenge


async def test_verify_and_store_registration():
    """Successful verification persists the credential on the user document."""
    verification = MagicMock()
    verification.credential_id = b"\x01\x02"
    verification.credential_public_key = b"\x03\x04"
    verification.sign_count = 0

    mongo_db = _mock_mongo_db()
    credential_response = {
        "id": "cred_id",
        "rawId": "cred_id",
        "type": "public-key",
        "response": {
            "clientDataJSON": "client_data_json",
            "attestationObject": "attestation_object",
            "transports": ["internal"],
        },
    }

    with patch.object(svc, "consume_challenge", MagicMock(return_value=b"challenge")), \
         patch.object(svc.webauthn, "verify_registration_response", MagicMock(return_value=verification)), \
         patch.object(database.mongodb, "db", mongo_db):
        cred_doc = await svc.verify_and_store_registration(
            user_id="user-123",
            credential_response=credential_response,
            db=mongo_db,
            users_collection=mongo_db.users,
            tenant_id="tenant-a",
        )

    assert cred_doc["credential_id"] == "0102"
    assert cred_doc["public_key"] == "0304"
    assert cred_doc["transports"] == ["internal"]
    mongo_db.users.update_one.assert_awaited_once()
    query, update = mongo_db.users.update_one.call_args.args
    assert query == {"id": "user-123"}
    assert update["$push"]["webauthn_credentials"]["credential_id"] == "0102"


async def test_verify_registration_expired_challenge():
    """Missing/expired challenge is rejected before touching webauthn or the db."""
    mongo_db = _mock_mongo_db()
    with patch.object(svc, "consume_challenge", MagicMock(return_value=None)), \
         patch.object(svc.webauthn, "verify_registration_response", MagicMock()) as verify, \
         patch.object(database.mongodb, "db", mongo_db):
        with pytest.raises(ValueError, match="Challenge expired or missing"):
            await svc.verify_and_store_registration(
                user_id="user-123",
                credential_response={"id": "cred_id"},
                db=mongo_db,
                users_collection=mongo_db.users,
                tenant_id="tenant-a",
            )
    verify.assert_not_called()
    mongo_db.users.update_one.assert_not_awaited()


def test_challenge_store_and_consume_roundtrip():
    """store_challenge/consume_challenge: one-shot, keyed by user+type."""
    svc.store_challenge("u1", "registration", b"abc")
    assert svc.consume_challenge("u1", "registration") == b"abc"
    # consumed — second read is empty
    assert svc.consume_challenge("u1", "registration") is None
    # wrong type never matches
    svc.store_challenge("u1", "registration", b"abc")
    assert svc.consume_challenge("u1", "authentication") is None


# ─── endpoint-level: usernameless login challenge-key roundtrip ──────────────

def _passkey_app():
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    import passkey_endpoints
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi import _rate_limit_exceeded_handler

    app = FastAPI()
    app.state.limiter = passkey_endpoints.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(passkey_endpoints.router)
    return app, passkey_endpoints, TestClient(app)


async def test_login_options_returns_challenge_key_and_json_options():
    """Options must be browser-consumable JSON plus a one-shot challenge_key."""
    app, mod, client = _passkey_app()
    res = client.post("/api/passkey/login/options", json={})
    assert res.status_code == 200
    body = res.json()
    assert "challenge_key" in body and body["challenge_key"]
    assert "options" in body and "challenge" in body["options"]
    # the challenge is stored under the login:<key> namespace, one-shot
    stored = svc.consume_challenge(f"login:{body['challenge_key']}", "authentication")
    assert stored is not None


async def test_login_verify_consumes_the_options_challenge(monkeypatch):
    """verify must consume the SAME challenge issued by login/options (bug fix:
    the old code stored under 'temp' and consumed under the user id, so login
    could never succeed)."""
    app, mod, client = _passkey_app()

    # issue options → challenge stored under login:<key>
    body = client.post("/api/passkey/login/options", json={}).json()
    key = body["challenge_key"]

    user_doc = {
        "id": "user-1",
        "username": "test@user.com",
        "role": "user",
        "tenantId": "tenant-a",
        "webauthn_credentials": [
            {"credential_id": "cred-1", "public_key": "0304", "sign_count": 0}
        ],
    }
    mongo_db = MagicMock()
    mongo_db.users.find_one = AsyncMock(return_value=user_doc)
    mongo_db.users.update_one = AsyncMock()

    verification = MagicMock()
    verification.new_sign_count = 1

    with patch.object(database.mongodb, "db", mongo_db), \
         patch.object(svc.webauthn, "verify_authentication_response",
                      MagicMock(return_value=verification)):
        res = client.post(
            "/api/passkey/login/verify",
            json={"credential": {"id": "cred-1"}, "challenge_key": key},
        )

    assert res.status_code == 200
    tokens = res.json()
    assert tokens["access_token"] and tokens["refresh_token"]
    # challenge is one-shot: replaying the same verify fails
    with patch.object(database.mongodb, "db", mongo_db), \
         patch.object(svc.webauthn, "verify_authentication_response",
                      MagicMock(return_value=verification)):
        replay = client.post(
            "/api/passkey/login/verify",
            json={"credential": {"id": "cred-1"}, "challenge_key": key},
        )
    assert replay.status_code == 401
