"""Phase 87-06: invite a person with a seven-day single-use link only they receive (real MongoDB).

Value: protects=the invite takeover rules (no token or link ever returned or logged, one generic
email-clash refusal, single use through the existing password-set route, no reissue once a password
is set); fails_when=invite() returns or logs a token or link, a clash names where the address is
used, a used or superseded link still reads as valid, or resend() reissues for a person who has
signed in; no_claim=real SMTP delivery (the mail sender is mocked) and the accept-invite page.
"""
import hashlib
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import auth_password_reset_endpoints as reset_ep
import partner_invites as inv
from auth_utils import verify_password
from partner_pool import PartnerError
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

GOOD_PASSWORD = "Str0ng!Passw0rd#42"
CLASH_MESSAGE = "That email address can't be used. Use a different one."


@pytest.fixture
def wired(mongo_db, monkeypatch):
    """The reset route reads the test database; sessions are not touched; no link base is set."""
    from rate_limiter import limiter as shared_limiter
    shared_limiter._storage.reset()
    monkeypatch.setattr(reset_ep, "get_database", lambda: SimpleNamespace(_db=mongo_db))
    monkeypatch.setattr(reset_ep, "revoke_user_sessions", AsyncMock())
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    return mongo_db


def _confirm_app():
    from fastapi import FastAPI
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address

    app = FastAPI()
    app.state.limiter = Limiter(key_func=get_remote_address)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(reset_ep.router)
    return app


async def _confirm(token, password=GOOD_PASSWORD):
    transport = httpx.ASGITransport(app=_confirm_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/auth/reset-password/confirm",
                                 json={"token": token, "new_password": password})


def _app_log(caplog):
    """What this codebase logged; the MongoDB driver's own command trace is not ours to police."""
    return "\n".join(r.getMessage() for r in caplog.records if not r.name.startswith("pymongo"))


async def _invite(db, email="Ada@Example.com", tenant_id="t-acme", role="Tenant Admin", kind="customer_admin"):
    return await inv.invite(db, tenant_id=tenant_id, organization_name="Acme", email=email, name="Ada",
                            role=role, role_kind=kind, invited_by="p@x")


async def _token_row(db, email="ada@example.com"):
    return await db.password_reset_tokens.find_one({"email": email, "invite": True})


async def test_invite_stores_an_active_user_with_a_password_nobody_knows(wired):
    out = await _invite(wired)
    user = await wired.users.find_one({"email": "ada@example.com"})
    assert user["status"] == "Active" and user["tenantId"] == "t-acme" and user["role"] == "Tenant Admin"
    assert not verify_password("anything", user["hashed_password"])
    assert not verify_password("Password1!", user["hashed_password"])
    assert out["user"]["email"] == "ada@example.com" and out["user"]["id"] == user["id"]


async def test_invite_stores_a_seven_day_token_row_without_a_creation_time_and_a_hash_only_record(wired):
    before = datetime.now(timezone.utc)
    await _invite(wired)
    row = await _token_row(wired)
    assert row["invite"] is True and set(row) == {"_id", "token", "email", "expires_at", "invite"}
    expires = datetime.fromisoformat(row["expires_at"])
    assert timedelta(days=6, hours=23) < expires - before < timedelta(days=7, minutes=1)
    record = await wired.invites.find_one({"email": "ada@example.com"})
    assert record["tokenHash"] == hashlib.sha256(row["token"].encode()).hexdigest()
    assert "token" not in record and row["token"] not in str(record)
    assert record["organizationName"] == "Acme" and record["roleKind"] == "customer_admin"


async def test_invite_returns_no_token_no_link_and_no_password(wired):
    out = await _invite(wired)
    row = await _token_row(wired)
    assert set(out) == {"user", "emailSent"} and out["emailSent"] is False
    assert set(out["user"]) == {"id", "name", "email", "role"}
    assert row["token"] not in repr(out) and "accept-invite" not in repr(out)


async def test_an_address_in_use_anywhere_is_refused_generically_and_nothing_is_stored(wired):
    await _invite(wired)
    with pytest.raises(PartnerError) as clash:
        await _invite(wired, email="ADA@example.com", tenant_id="t-other")
    assert clash.value.status == 409 and clash.value.code == "email_unavailable"
    assert clash.value.message == CLASH_MESSAGE
    assert "Acme" not in clash.value.message and "t-acme" not in clash.value.message
    assert await wired.users.count_documents({}) == 1
    assert await wired.password_reset_tokens.count_documents({}) == 1
    assert await wired.invites.count_documents({}) == 1


async def test_an_address_held_by_a_user_with_mixed_case_is_refused(wired):
    await wired.users.insert_one({"id": "u-1", "email": "Old.User@Example.com", "tenantId": "t-x"})
    with pytest.raises(PartnerError) as clash:
        await _invite(wired, email="old.user@example.com")
    assert clash.value.code == "email_unavailable"


async def test_an_invalid_address_is_refused_before_anything_is_stored(wired):
    for bad in ("not-an-email", "a b@c.de", "x@y", "a" * 250 + "@example.com"):
        with pytest.raises(PartnerError) as refused:
            await _invite(wired, email=bad)
        assert refused.value.status == 422 and refused.value.code == "invalid_email"
    assert await wired.users.count_documents({}) == 0


async def test_status_is_valid_then_used_after_the_existing_confirm_route_sets_a_password(wired):
    await _invite(wired)
    token = (await _token_row(wired))["token"]
    state = await inv.invite_state(wired, token)
    assert state == {"state": "valid", "organizationName": "Acme", "email": "ada@example.com",
                     "roleKind": "customer_admin"}
    response = await _confirm(token)
    assert response.status_code == 200
    assert (await inv.invite_state(wired, token)) == {"state": "used"}
    user = await wired.users.find_one({"email": "ada@example.com"})
    assert verify_password(GOOD_PASSWORD, user["password"])
    again = await _confirm(token)
    assert again.status_code == 400


async def test_status_is_expired_invalid_and_never_echoes_the_token(wired):
    await _invite(wired)
    row = await _token_row(wired)
    later = datetime.fromisoformat(row["expires_at"]) + timedelta(seconds=1)
    assert (await inv.invite_state(wired, row["token"], now=later)) == {"state": "expired"}
    assert (await inv.invite_state(wired, "nope")) == {"state": "invalid"}
    assert (await inv.invite_state(wired, "x" * 600)) == {"state": "invalid"}
    assert (await inv.invite_state(wired, "")) == {"state": "invalid"}
    assert (await inv.invite_state(wired, 12345)) == {"state": "invalid"}
    for state in (await inv.invite_state(wired, row["token"]), await inv.invite_state(wired, "nope")):
        assert row["token"] not in repr(state)


async def test_member_status_follows_the_invite_through_its_life(wired):
    await _invite(wired)
    row = await _token_row(wired)
    assert await inv.member_status(wired, "Ada@example.com") == "invited"
    later = datetime.fromisoformat(row["expires_at"]) + timedelta(seconds=1)
    assert await inv.member_status(wired, "ada@example.com", now=later) == "invite_expired"
    assert (await _confirm(row["token"])).status_code == 200
    assert await inv.member_status(wired, "ada@example.com") == "active"


async def test_resend_supersedes_the_old_link_and_issues_a_new_seven_day_one(wired):
    await _invite(wired)
    old = (await _token_row(wired))["token"]
    user = await wired.users.find_one({"email": "ada@example.com"})
    sent = await inv.resend(wired, user=user, organization_name="Acme", role_kind="customer_admin",
                            invited_by="p@x")
    assert sent is False
    new = (await _token_row(wired))["token"]
    assert new != old
    assert (await inv.invite_state(wired, old)) == {"state": "invalid"}
    assert (await inv.invite_state(wired, new))["state"] == "valid"
    assert await wired.password_reset_tokens.count_documents({"email": "ada@example.com"}) == 1
    assert (await _confirm(old)).status_code == 400


async def test_resend_is_refused_once_the_person_has_set_a_password(wired):
    await _invite(wired)
    token = (await _token_row(wired))["token"]
    assert (await _confirm(token)).status_code == 200
    user = await wired.users.find_one({"email": "ada@example.com"})
    with pytest.raises(PartnerError) as refused:
        await inv.resend(wired, user=user, organization_name="Acme", role_kind="customer_admin",
                         invited_by="p@x")
    assert refused.value.status == 409 and refused.value.code == "already_active"
    assert refused.value.message == "This person has already set a password."
    assert await wired.password_reset_tokens.count_documents({}) == 0


async def test_resend_is_refused_for_a_user_who_was_never_invited(wired):
    await wired.users.insert_one({"id": "u-2", "email": "boss@example.com", "tenantId": "t-acme",
                                  "password": "x"})
    user = await wired.users.find_one({"email": "boss@example.com"})
    with pytest.raises(PartnerError) as refused:
        await inv.resend(wired, user=user, organization_name="Acme", role_kind="customer_admin",
                         invited_by="p@x")
    assert refused.value.code == "already_active"


async def test_without_a_link_base_nothing_is_sent_and_nothing_secret_is_logged(wired, caplog):
    caplog.set_level(logging.DEBUG)
    with patch("email_service.email_service.send_email", new=AsyncMock()) as send:
        out = await _invite(wired)
    token = (await _token_row(wired))["token"]
    assert out["emailSent"] is False
    send.assert_not_awaited()
    assert token not in _app_log(caplog) and "accept-invite?token" not in _app_log(caplog)


async def test_without_a_mail_configuration_nothing_is_sent(wired, monkeypatch, caplog):
    monkeypatch.setenv("FRONTEND_URL", "https://omni.example.com")
    caplog.set_level(logging.DEBUG)
    with patch.object(reset_ep, "_resolve_smtp_config", new=AsyncMock(return_value=None)), \
            patch("email_service.email_service.send_email", new=AsyncMock()) as send, \
            patch("database.get_database", return_value=SimpleNamespace(_db=wired)):
        out = await _invite(wired)
    assert out["emailSent"] is False
    send.assert_not_awaited()
    assert (await _token_row(wired))["token"] not in _app_log(caplog)


async def test_a_link_base_that_is_not_http_is_refused(wired, monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "javascript:alert(1)")
    with patch("email_service.email_service.send_email", new=AsyncMock()) as send:
        out = await _invite(wired)
    assert out["emailSent"] is False
    send.assert_not_awaited()


async def test_with_mail_configured_the_link_goes_only_to_the_invitee_and_never_to_a_log(
        wired, monkeypatch, caplog):
    monkeypatch.setenv("FRONTEND_URL", "https://omni.example.com/")
    caplog.set_level(logging.DEBUG)
    smtp = {"smtpHost": "mail.example.com", "smtpUser": "u", "smtpPasswordEncrypted": "x"}
    with patch.object(reset_ep, "_resolve_smtp_config", new=AsyncMock(return_value=smtp)), \
            patch("email_service.email_service.send_email",
                  new=AsyncMock(return_value={"success": True, "message": "ok"})) as send, \
            patch("database.get_database", return_value=SimpleNamespace(_db=wired)):
        out = await _invite(wired)
    token = (await _token_row(wired))["token"]
    assert out["emailSent"] is True and token not in repr(out)
    kwargs = send.await_args.kwargs
    assert kwargs["to_email"] == "ada@example.com"
    link = f"https://omni.example.com/accept-invite?token={token}"
    assert link in kwargs["body_text"] and link in kwargs["body_html"]
    assert "7 days" in kwargs["body_text"]
    assert token not in _app_log(caplog) and "accept-invite?token" not in _app_log(caplog)


async def test_a_mail_failure_reports_false_and_still_keeps_the_invite(wired, monkeypatch, caplog):
    monkeypatch.setenv("FRONTEND_URL", "https://omni.example.com")
    caplog.set_level(logging.DEBUG)
    smtp = {"smtpHost": "mail.example.com", "smtpUser": "u", "smtpPasswordEncrypted": "x"}
    with patch.object(reset_ep, "_resolve_smtp_config", new=AsyncMock(return_value=smtp)), \
            patch("email_service.email_service.send_email", new=AsyncMock(side_effect=RuntimeError("boom"))), \
            patch("database.get_database", return_value=SimpleNamespace(_db=wired)):
        out = await _invite(wired)
    assert out["emailSent"] is False
    token = (await _token_row(wired))["token"]
    assert (await inv.invite_state(wired, token))["state"] == "valid"
    assert token not in _app_log(caplog)
