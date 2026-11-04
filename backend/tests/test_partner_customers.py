"""Phase 87 plan 09 task 1: a partner creates a customer with its first admin invited, changes its seats,
and is refused after the pool expires (real MongoDB).

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Route functions are called with a TokenData; the audit writer and
the invite mailer are mocked, so nothing reaches the live database or a mail server.
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import partner_endpoints as pe
import partner_invites
import partner_store
from auth_types import TokenData
from partner_pool import PartnerError
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

PAST = "2020-01-01T00:00:00+00:00"
EXPIRED_CREATE = "Your seat pool has expired. You can't create customers."
EXPIRED_HAND_OUT = "Your seat pool has expired. You can't hand out seats."


@pytest.fixture
def wired(mongo_db):  # noqa: F811
    handle = SimpleNamespace(db=mongo_db)
    mail = AsyncMock(return_value=False)
    with patch.object(pe, "mongodb", handle), \
            patch("audit_ledger.event", new=AsyncMock()) as audit, \
            patch("partner_invites.send_invite_email", new=mail):
        yield SimpleNamespace(db=mongo_db, audit=audit, mail=mail)


def _body(response):
    return json.loads(response.body)


def _user(partner_id, role="partner_admin"):
    return TokenData(username=f"{role}@retail.test", role=role, tenant_id=partner_id, mfa_verified=True)


async def _partner(wired, pid="partner_a", name="Retailer A", pool=100, allocated=0, expires=None, ceiling=("all",)):
    await wired.db.tenants.insert_one({
        "id": pid, "type": "partner", "name": name, "license": {"maxAgents": 0}, "maxAgents": 0,
        "partner": {"poolSize": pool, "allocated": allocated, "status": "active",
                    "screenCeiling": list(ceiling), "expiresAt": expires},
    })
    return pid


async def _ctx(pid="partner_a", role="partner_admin"):
    return await pe.current_partner(current_user=_user(pid, role))


def _new(name="Cafe One", seats=10, email="owner@cafeone.test", admin="Owner"):
    return pe.CustomerCreate(name=name, seats=seats, adminName=admin, adminEmail=email)


async def _allocated(wired, pid="partner_a"):
    return (await wired.db.tenants.find_one({"id": pid}))["partner"]["allocated"]


def _strings(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _strings(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _strings(value)
    elif node is not None:
        yield str(node)


# --- PART-02: create with the first admin --------------------------------------------------------

async def test_creating_a_customer_invites_its_first_admin_and_returns_no_secret(wired):
    """protects=D-09 shape {customer, emailSent}; fails_when=a token, link or registrationKey is in the answer
    or the admin is stored with another role; no_claim=email delivery (the mailer is mocked)."""
    await _partner(wired)
    out = await pe.post_customer(_new(email="  Owner@CafeOne.test "), ctx=await _ctx())
    assert set(out) == {"customer", "emailSent"} and out["emailSent"] is False
    assert tuple(out["customer"]) == partner_store.CUSTOMER_FIELDS
    sent = wired.mail.await_args.kwargs
    assert sent["tenant_id"] == out["customer"]["id"] and sent["email"] == "owner@cafeone.test"
    blob = list(_strings(out))
    assert not any(sent["token"] in text or "accept-invite" in text for text in blob)
    assert not any(key in blob for key in ("registrationKey", "token", "link", "url"))
    user = await wired.db.users.find_one({"email": "owner@cafeone.test"})
    assert user["tenantId"] == out["customer"]["id"] and user["role"] == "Tenant Admin"
    invite = await wired.db.invites.find_one({"tenantId": out["customer"]["id"]})
    assert invite["roleKind"] == "customer_admin" and invite["invitedBy"] == "partner_admin@retail.test"
    actions = [c.args[0] for c in wired.audit.await_args_list]
    assert "partner.customer_created" in actions and "partner.invite_sent" in actions


async def test_a_created_customer_is_never_a_partner(wired):
    """protects=D-03 no sub-dealers; fails_when=the customer document carries a type field."""
    await _partner(wired)
    out = await pe.post_customer(_new(), ctx=await _ctx())
    doc = await wired.db.tenants.find_one({"id": out["customer"]["id"]})
    assert "type" not in doc and doc["partnerId"] == "partner_a"


async def test_an_email_in_use_anywhere_is_refused_before_the_pool_is_touched(wired):
    """protects=PART-02 409 email_unavailable first; fails_when=seats are claimed or a customer stored."""
    await _partner(wired)
    await wired.db.users.insert_one({"id": "u1", "email": "owner@cafeone.test", "tenantId": "someone_else"})
    refused = await pe.post_customer(_new(email="OWNER@cafeone.TEST"), ctx=await _ctx())
    assert refused.status_code == 409 and _body(refused)["code"] == "email_unavailable"
    assert await _allocated(wired) == 0
    assert await wired.db.tenants.count_documents({"partnerId": "partner_a"}) == 0
    wired.mail.assert_not_awaited()


async def test_an_invalid_admin_email_is_refused_before_the_pool_is_touched(wired):
    await _partner(wired)
    refused = await pe.post_customer(_new(email="not-an-email"), ctx=await _ctx())
    assert refused.status_code == 422 and _body(refused)["code"] == "invalid_email"
    assert await _allocated(wired) == 0


async def test_a_failed_invite_deletes_the_customer_and_returns_its_seats(wired):
    """protects=PART-02 no half-created customer; fails_when=the customer, its seats or its user remain."""
    await _partner(wired)
    with patch("partner_invites.invite", new=AsyncMock(side_effect=RuntimeError("database went away"))):
        with pytest.raises(RuntimeError):
            await pe.post_customer(_new(seats=25), ctx=await _ctx())
    assert await wired.db.tenants.count_documents({"partnerId": "partner_a"}) == 0
    assert await _allocated(wired) == 0
    refused = await pe.post_customer(_new(seats=25), ctx=await _ctx())  # the seats really came back
    assert isinstance(refused, dict) and await _allocated(wired) == 25


async def test_an_invite_refusal_after_the_store_is_answered_and_cleaned_up(wired):
    await _partner(wired)
    clash = PartnerError(409, "email_unavailable", "That email address can't be used. Use a different one.")
    with patch("partner_invites.invite", new=AsyncMock(side_effect=clash)):
        refused = await pe.post_customer(_new(seats=7), ctx=await _ctx())
    assert refused.status_code == 409 and _body(refused)["code"] == "email_unavailable"
    assert await wired.db.tenants.count_documents({"partnerId": "partner_a"}) == 0
    assert await _allocated(wired) == 0


# --- PART-05 encoding: names ---------------------------------------------------------------------

async def test_a_name_in_use_by_any_organization_is_refused_generically(wired):
    """protects=T-87-30 one generic refusal; fails_when=the case or spacing slips past it, the message
    names an organization, or seats are claimed for the refused name."""
    await _partner(wired)
    await wired.db.tenants.insert_one({"id": "tenant_acme", "name": "Acme", "license": {"maxAgents": 1}})
    refused = await pe.post_customer(_new(name=" acme ", email="a@acme.test"), ctx=await _ctx())
    assert refused.status_code == 409
    assert _body(refused)["code"] == "name_unavailable" and _body(refused)["error"] == "That name isn't available."
    assert await _allocated(wired) == 0


async def test_a_name_taken_between_the_check_and_the_insert_is_refused_and_returns_the_seats(wired):
    """87 WR-02: protects=the 409 name contract when a concurrent create wins the race; fails_when=the
    unique index's duplicate-key error surfaces as a 500 or the claimed seats stay allocated;
    no_claim=two real concurrent requests (the pre-check is made to miss instead)."""
    await _partner(wired)
    await wired.db.tenants.create_index("name", unique=True)
    await wired.db.tenants.insert_one({"id": "tenant_acme", "name": "Acme", "license": {"maxAgents": 1}})
    with patch("partner_portal_service.name_taken", new=AsyncMock(return_value=False)):
        refused = await pe.post_customer(_new(name="Acme", email="a@acme.test"), ctx=await _ctx())
    assert refused.status_code == 409 and _body(refused)["code"] == "name_unavailable"
    assert await _allocated(wired) == 0
    assert await wired.db.users.count_documents({"email": "a@acme.test"}) == 0


async def test_non_ascii_names_are_stored_with_their_own_letters_and_collide_ignoring_case(wired):
    """protects=PART-05 encoding; fails_when=the stored name is folded or altered, or a case variant of a
    non-ASCII name is accepted as a different name."""
    await _partner(wired)
    out = await pe.post_customer(_new(name="Zoë Bâtiment", email="z@zoe.test"), ctx=await _ctx())
    assert (await wired.db.tenants.find_one({"id": out["customer"]["id"]}))["name"] == "Zoë Bâtiment"
    assert out["customer"]["name"] == "Zoë Bâtiment"
    refused = await pe.post_customer(_new(name=" ZOË BÂTIMENT", email="z2@zoe.test"), ctx=await _ctx())
    assert refused.status_code == 409 and _body(refused)["code"] == "name_unavailable"


# --- PART-04: an expired pool --------------------------------------------------------------------

async def test_an_expired_pool_refuses_every_creation_and_never_moves_the_counter(wired):
    """protects=D-08 + idempotency; fails_when=a creation succeeds after expiry or allocated changes."""
    await _partner(wired, allocated=10, expires=PAST)
    for attempt in range(3):
        refused = await pe.post_customer(_new(name=f"Late {attempt}", email=f"l{attempt}@late.test"),
                                         ctx=await _ctx())
        assert refused.status_code == 409
        assert _body(refused)["code"] == "pool_expired" and _body(refused)["error"] == EXPIRED_CREATE
        assert await _allocated(wired) == 10
    assert await wired.db.tenants.count_documents({"partnerId": "partner_a"}) == 0
    wired.mail.assert_not_awaited()


async def test_an_expired_pool_refuses_raising_seats_every_time_but_allows_lowering(wired):
    """protects=D-08 hand-out message + A-87-LOWER-AFTER-EXPIRY; fails_when=a raise succeeds after expiry
    or returning seats is refused."""
    await _partner(wired, allocated=10)
    made = await pe.post_customer(_new(seats=10), ctx=await _ctx())
    cid = made["customer"]["id"]
    await wired.db.tenants.update_one({"id": "partner_a"}, {"$set": {"partner.expiresAt": PAST}})
    for _ in range(2):
        refused = await pe.put_customer_seats(cid, pe.SeatsBody(seats=12), ctx=await _ctx())
        assert refused.status_code == 409
        assert _body(refused)["code"] == "pool_expired" and _body(refused)["error"] == EXPIRED_HAND_OUT
        assert await _allocated(wired) == 20
    lowered = await pe.put_customer_seats(cid, pe.SeatsBody(seats=6), ctx=await _ctx())
    assert lowered["customer"]["seatsAssigned"] == 6 and await _allocated(wired) == 16


# --- PART-03: seats ------------------------------------------------------------------------------

async def _customer(wired, seats=10, used=3):
    out = await pe.post_customer(_new(seats=seats), ctx=await _ctx())
    cid = out["customer"]["id"]
    await wired.db.tenants.update_one({"id": cid}, {"$set": {"license.seatsUsed": used}})
    return cid


async def test_seats_lower_to_exactly_the_seats_in_use_and_not_below(wired):
    """protects=D-06 floor; fails_when=a lowering below seatsUsed is accepted or exactly seatsUsed is refused."""
    await _partner(wired)
    cid = await _customer(wired, seats=10, used=3)
    refused = await pe.put_customer_seats(cid, pe.SeatsBody(seats=2), ctx=await _ctx())
    assert refused.status_code == 409
    assert _body(refused)["code"] == "below_used" and _body(refused)["used"] == 3
    assert await _allocated(wired) == 10
    out = await pe.put_customer_seats(cid, pe.SeatsBody(seats=3), ctx=await _ctx())
    assert out["customer"]["seatsAssigned"] == 3 and out["customer"]["seatsUsed"] == 3
    assert out["pool"] == {"size": 100, "handedOut": 3, "free": 97, "expiresAt": None, "expired": False}
    assert await _allocated(wired) == 3
    audit = [c for c in wired.audit.await_args_list if c.args[0] == "partner.allotment_changed"]
    assert audit and audit[-1].kwargs["before"] == 10 and audit[-1].kwargs["after"] == 3


async def test_seats_raise_only_within_the_free_seats(wired):
    """protects=D-06 pool bound; fails_when=a raise past the free seats is accepted or the free count is wrong."""
    await _partner(wired, pool=20)
    cid = await _customer(wired, seats=10, used=0)
    refused = await pe.put_customer_seats(cid, pe.SeatsBody(seats=21), ctx=await _ctx())
    assert refused.status_code == 409
    assert _body(refused)["code"] == "pool_full" and _body(refused)["free"] == 10
    assert await _allocated(wired) == 10
    out = await pe.put_customer_seats(cid, pe.SeatsBody(seats=20), ctx=await _ctx())
    assert out["customer"]["seatsAssigned"] == 20 and out["pool"]["free"] == 0


async def test_another_partners_customer_and_an_unknown_id_answer_the_same_404(wired):
    """protects=T-87-26; fails_when=the two answers differ."""
    await _partner(wired)
    await _partner(wired, pid="partner_b", name="Retailer B")
    mine = await _customer(wired)
    await wired.db.tenants.insert_one({"id": "theirs", "name": "Theirs", "partnerId": "partner_b",
                                       "license": {"maxAgents": 5, "seatsUsed": 0}})
    foreign = await pe.put_customer_seats("theirs", pe.SeatsBody(seats=1), ctx=await _ctx())
    unknown = await pe.put_customer_seats("no-such-id", pe.SeatsBody(seats=1), ctx=await _ctx())
    assert foreign.status_code == unknown.status_code == 404
    assert _body(foreign) == _body(unknown) and _body(foreign)["error"] == "Customer not found"
    assert (await wired.db.tenants.find_one({"id": "theirs"}))["license"]["maxAgents"] == 5
    assert mine and await _allocated(wired, "partner_b") == 0


async def test_a_viewer_cannot_create_or_change_seats(wired):
    """protects=D-04; fails_when=a viewer reaches a write."""
    await _partner(wired)
    cid = await _customer(wired)
    viewer = await _ctx(role="partner_viewer")
    with pytest.raises(HTTPException) as exc:
        await pe.post_customer(_new(name="Nope", email="n@n.test"), ctx=viewer)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await pe.put_customer_seats(cid, pe.SeatsBody(seats=5), ctx=viewer)
    assert exc.value.status_code == 403


def test_the_request_models_require_the_admin_and_bound_the_seats():
    with pytest.raises(Exception):
        pe.CustomerCreate(name="X", seats=1)
    with pytest.raises(Exception):
        pe.CustomerCreate(name="X", seats=1, adminName="", adminEmail="a@b.test")
    with pytest.raises(Exception):
        pe.SeatsBody(seats=-1)
    assert partner_invites.INVITE_DAYS == 7
