"""Phase 87 plan 08: the Super Admin appoints, edits, suspends and reinstates partners (real MongoDB).

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Route functions are called with a TokenData; the audit writer,
the invite mailer and the session revocation are mocked, so nothing reaches the live database or a
mail server.
"""
import json
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import partner_platform_endpoints as ppe
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)
PARTNER_ADMIN = TokenData(username="boss@retail.test", role="partner_admin", tenant_id="partner_x", mfa_verified=True)
SUPPORT = TokenData(username="help@example.com", role="platform_support", tenant_id="platform-admin", mfa_verified=True)


@pytest.fixture
def wired(mongo_db):  # noqa: F811
    handle = SimpleNamespace(db=mongo_db)
    with patch.object(ppe, "mongodb", handle), \
            patch("audit_ledger.event", new=AsyncMock()) as audit, \
            patch("partner_invites.send_invite_email", new=AsyncMock(return_value=False)) as mail, \
            patch("authentication_service.revoke_user_sessions", new=AsyncMock()) as revoke:
        yield SimpleNamespace(db=mongo_db, audit=audit, mail=mail, revoke=revoke)


def _body(response):
    return json.loads(response.body)


async def _appoint(name="Retailer A", pool=100, email=None, ceiling=None, expires=None, admin="Bo Boss"):
    email = email or f"boss@{name.lower().replace(' ', '')}.test"
    out = await ppe.create_partner(
        ppe.PartnerCreate(name=name, poolSize=pool, expiresAt=expires, screenCeiling=["all"] if ceiling is None else ceiling,
                          adminName=admin, adminEmail=email),
        current_user=SUPER)
    return out["partner"]["id"] if isinstance(out, dict) else out


def _actions(wired, action, tenant=None):
    return [c for c in wired.audit.await_args_list
            if c.args[0] == action and (tenant is None or c.args[1] == tenant)]


async def _patch(partner_id, **fields):
    return await ppe.update_partner(partner_id, ppe.PartnerUpdate(**fields), current_user=SUPER)


# --- Task 1: appoint with a first admin -------------------------------------------------------

async def test_appoint_invites_the_first_partner_admin(wired):
    # protects=the partner organization and its first admin are created together and the invite is sent
    # fails_when=no admin user, a wrong role kind, or the link returned to the caller; no_claim=real email delivery
    out = await ppe.create_partner(
        ppe.PartnerCreate(name="Retailer A", poolSize=40, screenCeiling=["view:agents"],
                          adminName="Bo Boss", adminEmail=" Boss@Retail.Test "), current_user=SUPER)
    assert out["emailSent"] is False and out["partner"]["name"] == "Retailer A" and out["partner"]["customerCount"] == 0
    partner_id = out["partner"]["id"]
    users = await wired.db.users.find({"tenantId": partner_id}).to_list(length=None)
    assert [(u["email"], u["role"], u["name"]) for u in users] == [("boss@retail.test", "partner_admin", "Bo Boss")]
    invite = await wired.db.invites.find_one({"tenantId": partner_id})
    assert invite["roleKind"] == "partner_admin" and invite["email"] == "boss@retail.test"
    assert wired.mail.await_count == 1
    assert "token" not in json.dumps(out) and "link" not in json.dumps(out).lower()
    appointed = _actions(wired, "partner.appointed")
    assert {c.args[1] for c in appointed} == {partner_id, "platform-admin"}
    assert appointed[0].kwargs["poolSize"] == 40 and appointed[0].kwargs["adminEmail"] == "boss@retail.test"


async def test_an_email_already_in_use_leaves_no_partner_behind(wired):
    # protects=the 409 comes before anything is stored; fails_when=a partner organization remains after the refusal
    await wired.db.users.insert_one({"id": "u1", "email": "Taken@Else.Test", "tenantId": "tenant_a", "role": "Tenant Admin"})
    before = await wired.db.tenants.count_documents({})
    refused = await ppe.create_partner(
        ppe.PartnerCreate(name="Retailer A", poolSize=5, screenCeiling=[], adminName="Bo", adminEmail="taken@else.test"),
        current_user=SUPER)
    assert refused.status_code == 409 and _body(refused)["code"] == "email_unavailable"
    assert await wired.db.tenants.count_documents({}) == before
    assert wired.mail.await_count == 0


async def test_a_failed_invite_removes_the_partner_it_just_created(wired):
    # protects=no half-appointed partner; fails_when=the organization or its admin user is left when the invite raises
    from partner_pool import PartnerError
    with patch("partner_invites.invite", new=AsyncMock(side_effect=PartnerError(409, "email_unavailable", "x"))):
        refused = await ppe.create_partner(
            ppe.PartnerCreate(name="Retailer A", poolSize=5, screenCeiling=[], adminName="Bo", adminEmail="bo@x.test"),
            current_user=SUPER)
    assert refused.status_code == 409
    assert await wired.db.tenants.count_documents({"type": "partner"}) == 0
    assert await wired.db.users.count_documents({}) == 0


async def test_an_invalid_admin_email_is_refused_before_a_write(wired):
    refused = await ppe.create_partner(
        ppe.PartnerCreate(name="Retailer A", poolSize=5, screenCeiling=[], adminName="Bo", adminEmail="not-an-email"),
        current_user=SUPER)
    assert refused.status_code == 422 and _body(refused)["code"] == "invalid_email"
    assert await wired.db.tenants.count_documents({}) == 0


async def test_a_taken_name_is_refused_in_any_case(wired):
    await _appoint(name="Retailer A")
    refused = await ppe.create_partner(
        ppe.PartnerCreate(name="  retailer a ", poolSize=5, screenCeiling=[], adminName="Bo", adminEmail="new@x.test"),
        current_user=SUPER)
    body = _body(refused)
    assert refused.status_code == 409 and body["code"] == "name_unavailable" and body["error"] == "That name isn't available."
    assert await wired.db.users.count_documents({"email": "new@x.test"}) == 0


async def test_an_empty_ceiling_is_a_valid_partner(wired):
    # protects=a partner may be appointed able to sell only the Dashboard; fails_when=an empty ceiling is refused or widened
    partner_id = await _appoint(ceiling=[])
    assert (await wired.db.tenants.find_one({"id": partner_id}))["partner"]["screenCeiling"] == []
    listed = await ppe.list_partners(current_user=SUPER)
    assert listed["partners"][0]["screenCeiling"] == [] and listed["partners"][0]["unrestricted"] is False


# --- Task 1: list ------------------------------------------------------------------------------

async def test_list_is_empty_without_partners(wired):
    assert await ppe.list_partners(current_user=SUPER) == {"partners": []}


async def test_list_orders_by_name_ignoring_case_then_id_and_counts_customers(wired):
    b = await _appoint(name="beta", email="b@x.test")
    a1 = await _appoint(name="Alpha", email="a1@x.test")
    await wired.db.tenants.update_one({"id": a1}, {"$set": {"id": "partner_a1"}})
    await wired.db.tenants.insert_one({"id": "partner_a0", "type": "partner", "name": "alpha",
                                       "partner": {"poolSize": 3, "allocated": 0, "status": "active"}})
    await wired.db.tenants.insert_many([
        {"id": "c1", "name": "C1", "partnerId": b, "license": {"maxAgents": 1}},
        {"id": "c2", "name": "C2", "partnerId": b, "license": {"maxAgents": 1}},
    ])
    listed = (await ppe.list_partners(current_user=SUPER))["partners"]
    assert [(p["name"], p["id"]) for p in listed] == [("alpha", "partner_a0"), ("Alpha", "partner_a1"), ("beta", b)]
    assert [p["customerCount"] for p in listed] == [0, 0, 2]
    assert {"poolSize", "allocated", "free", "expiresAt", "expired", "screenCeiling", "unrestricted", "status"} <= set(listed[0])


# --- Task 1: edit pool, expiry, ceiling, name --------------------------------------------------

async def test_pool_may_equal_the_handed_out_count_but_not_go_below(wired):
    # protects=D-07 floor, adjacency; fails_when=a pool smaller than the handed-out seats is accepted
    partner_id = await _appoint(pool=100)
    await wired.db.tenants.update_one({"id": partner_id}, {"$set": {"partner.allocated": 30}})
    ok = await _patch(partner_id, poolSize=30)
    assert ok["partner"]["poolSize"] == 30 and ok["partner"]["free"] == 0
    refused = await _patch(partner_id, poolSize=29)
    body = _body(refused)
    assert refused.status_code == 409 and body["code"] == "pool_below_handed_out" and body["handedOut"] == 30
    assert "30" in body["error"]
    assert (await wired.db.tenants.find_one({"id": partner_id}))["partner"]["poolSize"] == 30
    changed = _actions(wired, "partner.pool_changed")
    assert {c.args[1] for c in changed} == {partner_id, "platform-admin"}
    assert changed[0].kwargs["before"] == 100 and changed[0].kwargs["after"] == 30


async def test_expiry_can_be_set_cleared_and_reads_expired_once_past(wired):
    partner_id = await _appoint()
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    out = await _patch(partner_id, expiresAt=past)
    assert out["partner"]["expired"] is True and out["partner"]["expiresAt"].startswith("2020-01-01")
    out = await _patch(partner_id, expiresAt=None)  # an explicit null clears it
    assert out["partner"]["expiresAt"] is None and out["partner"]["expired"] is False
    assert len(_actions(wired, "partner.expiry_changed", "platform-admin")) == 2


async def test_a_ceiling_accepts_known_switches_or_all_and_nothing_else(wired):
    partner_id = await _appoint(ceiling=[])
    refused = await _patch(partner_id, screenCeiling=["view:nope"])
    assert refused.status_code == 422 and _body(refused)["code"] == "invalid_screen"
    out = await _patch(partner_id, screenCeiling=["view:agents", "view:agents"])
    assert out["partner"]["screenCeiling"] == ["view:agents"]
    out = await _patch(partner_id, screenCeiling=["all"])
    assert out["partner"]["unrestricted"] is True
    assert (await wired.db.tenants.find_one({"id": partner_id}))["partner"]["screenCeiling"] == ["all"]
    assert len(_actions(wired, "partner.ceiling_changed", partner_id)) == 2


async def test_a_ceiling_change_never_alters_a_customers_screens(wired):
    # protects=D-19; fails_when=narrowing the ceiling rewrites any customer's enabledFeatures
    partner_id = await _appoint(ceiling=["all"])
    features = ["view:agents", "view:tickets", "view:dashboard"]
    await wired.db.tenants.insert_one({"id": "cust1", "name": "Cafe", "partnerId": partner_id,
                                       "license": {"maxAgents": 5}, "enabledFeatures": list(features)})
    await _patch(partner_id, screenCeiling=["view:agents"])
    await _patch(partner_id, screenCeiling=[])
    assert (await wired.db.tenants.find_one({"id": "cust1"}))["enabledFeatures"] == features


async def test_a_name_taken_between_the_check_and_the_write_is_refused_and_changes_nothing(wired):
    # protects=87 WR-02, the 409 name contract when a concurrent write wins the race; fails_when=the unique
    # index's duplicate-key error surfaces as a 500, a user is left behind, or the pool resize of a refused
    # rename stays applied; no_claim=two real concurrent requests (the pre-check is made to miss instead)
    await wired.db.tenants.create_index("name", unique=True)
    a = await _appoint(name="Retailer A")
    await wired.db.tenants.insert_one({"id": "tenant_acme", "name": "Acme"})
    with patch("partner_platform_service.name_taken", new=AsyncMock(return_value=False)):
        appointed = await ppe.create_partner(
            ppe.PartnerCreate(name="Acme", poolSize=10, screenCeiling=["all"], adminName="X", adminEmail="x@acme.test"),
            current_user=SUPER)
        renamed = await _patch(a, name="Acme", poolSize=50)
    assert appointed.status_code == 409 and _body(appointed)["code"] == "name_unavailable"
    assert await wired.db.users.count_documents({"email": "x@acme.test"}) == 0
    assert renamed.status_code == 409 and _body(renamed)["code"] == "name_unavailable"
    partner = await wired.db.tenants.find_one({"id": a})
    assert partner["name"] == "Retailer A" and partner["partner"]["poolSize"] == 100
    assert not _actions(wired, "partner.pool_changed", a) and not _actions(wired, "partner.renamed", a)


async def test_a_refused_pool_resize_keeps_the_old_name(wired):
    # protects=87 WR-02, an edit is applied whole or not at all; fails_when=the rename stays after the pool
    # resize in the same request is refused; no_claim=a crash between the two writes
    a = await _appoint(name="Retailer A")
    await wired.db.tenants.update_one({"id": a}, {"$set": {"partner.allocated": 30}})
    refused = await _patch(a, name="Retailer Renamed", poolSize=10)
    assert refused.status_code == 409
    assert (await wired.db.tenants.find_one({"id": a}))["name"] == "Retailer A"
    assert not _actions(wired, "partner.renamed", a)


async def test_rename_checks_other_names_only_and_is_audited(wired):
    a = await _appoint(name="Retailer A")
    await _appoint(name="Retailer B", email="b@x.test")
    taken = await _patch(a, name="retailer b ")
    assert taken.status_code == 409 and _body(taken)["code"] == "name_unavailable"
    same = await _patch(a, name="RETAILER A")  # its own name in another case is fine
    assert same["partner"]["name"] == "RETAILER A"
    renamed = _actions(wired, "partner.renamed", a)
    assert renamed[0].kwargs["before"] == "Retailer A" and renamed[0].kwargs["after"] == "RETAILER A"


async def test_a_failed_pool_change_leaves_the_other_fields_untouched(wired):
    partner_id = await _appoint(name="Retailer A")
    await wired.db.tenants.update_one({"id": partner_id}, {"$set": {"partner.allocated": 50}})
    refused = await _patch(partner_id, name="Renamed", poolSize=10, screenCeiling=[])
    assert refused.status_code == 409
    doc = await wired.db.tenants.find_one({"id": partner_id})
    assert doc["name"] == "Retailer A" and doc["partner"]["screenCeiling"] == ["all"]


async def test_an_empty_patch_and_unknown_ids_are_refused(wired):
    partner_id = await _appoint()
    with pytest.raises(HTTPException) as exc:
        await _patch(partner_id)
    assert exc.value.status_code == 400 and exc.value.detail == "Nothing to update"
    await wired.db.tenants.insert_one({"id": "cust_plain", "name": "Plain"})
    for missing in ("nope", "cust_plain", "platform-admin"):
        refused = await _patch(missing, poolSize=5)
        assert refused.status_code == 404 and _body(refused)["code"] == "not_found"


async def test_only_the_super_admin_reaches_the_routes(wired):
    # protects=every route closes to everyone else; fails_when=a partner admin or platform support gets through
    partner_id = await _appoint()
    for user in (PARTNER_ADMIN, SUPPORT):
        with pytest.raises(HTTPException) as exc:
            await ppe.list_partners(current_user=user)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await ppe.create_partner(ppe.PartnerCreate(name="X", poolSize=5, screenCeiling=[], adminName="B", adminEmail="b@x.test"),
                                     current_user=user)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await ppe.update_partner(partner_id, ppe.PartnerUpdate(poolSize=5), current_user=user)
        assert exc.value.status_code == 403


# --- Task 2: suspend and reinstate -------------------------------------------------------------

async def _partner_with_world(wired):
    """A partner with two users, one customer, and agents; returns the partner id."""
    partner_id = await _appoint(name="Retailer A", pool=100)
    await wired.db.users.insert_one({"id": "u2", "email": "viewer@retailer.test", "role": "partner_viewer",
                                     "tenantId": partner_id, "status": "Active"})
    await wired.db.users.insert_one({"id": "u9", "email": "other@else.test", "role": "Tenant Admin",
                                     "tenantId": "tenant_other", "status": "Active"})
    await wired.db.tenants.insert_one({"id": "cust1", "name": "Cafe", "partnerId": partner_id,
                                       "license": {"maxAgents": 5, "seatsUsed": 2}, "maxAgents": 5,
                                       "enabledFeatures": ["view:agents"]})
    await wired.db.tenants.update_one({"id": partner_id}, {"$set": {"partner.allocated": 5}})
    await wired.db.agents.insert_many([
        {"id": "a1", "hostname": "h1", "tenantId": "cust1", "status": "Online"},
        {"id": "a2", "hostname": "h2", "tenantId": "cust1", "status": "Offline"},
    ])
    return partner_id


async def test_suspend_locks_the_partner_and_signs_its_users_out(wired):
    # protects=D-15 lock; fails_when=a partner user keeps a session, or the partner can still sell seats
    import partner_pool
    import partner_status
    partner_id = await _partner_with_world(wired)
    out = await ppe.suspend_partner(partner_id, current_user=SUPER)
    assert out["partner"]["status"] == "suspended"
    doc = await wired.db.tenants.find_one({"id": partner_id})
    assert doc["partner"]["status"] == "suspended" and doc["partner"]["suspendedBy"] == "root@example.com"
    assert isinstance(doc["partner"]["suspendedAt"], str)
    revoked = sorted(c.args[0] for c in wired.revoke.await_args_list)
    assert revoked == ["boss@retailera.test", "viewer@retailer.test"]
    assert all(c.args[1] == "partner suspended" for c in wired.revoke.await_args_list)
    assert await partner_pool.claim(wired.db, partner_id, 1, require_active=True) is False
    with patch.object(partner_status, "_raw_db", lambda: wired.db):
        with pytest.raises(HTTPException) as exc:
            await partner_status.refuse_if_suspended("partner_admin", partner_id)
    assert exc.value.status_code == 403
    suspended = _actions(wired, "partner.suspended")
    assert {c.args[1] for c in suspended} == {partner_id, "platform-admin"}


async def test_suspend_leaves_every_customer_and_agent_byte_for_byte(wired):
    # protects=D-15 / T-87-25; fails_when=a customer, its agents or the pool counter change
    partner_id = await _partner_with_world(wired)
    before = (await wired.db.tenants.find({"id": "cust1"}).to_list(None),
              await wired.db.agents.find({}).sort("id", 1).to_list(None))
    await ppe.suspend_partner(partner_id, current_user=SUPER)
    after = (await wired.db.tenants.find({"id": "cust1"}).to_list(None),
             await wired.db.agents.find({}).sort("id", 1).to_list(None))
    assert after == before
    assert (await wired.db.tenants.find_one({"id": partner_id}))["partner"]["allocated"] == 5
    await ppe.reinstate_partner(partner_id, current_user=SUPER)
    assert await wired.db.tenants.find({"id": "cust1"}).to_list(None) == before[0]


async def test_a_failed_sign_out_answers_503_and_the_partner_stays_suspended(wired):
    partner_id = await _partner_with_world(wired)
    wired.revoke.side_effect = RuntimeError("store down")
    refused = await ppe.suspend_partner(partner_id, current_user=SUPER)
    body = _body(refused)
    assert refused.status_code == 503 and body["error"] == "Couldn't sign this partner's users out. Try again."
    assert (await wired.db.tenants.find_one({"id": partner_id}))["partner"]["status"] == "suspended"
    wired.revoke.side_effect = None  # a retry finishes the sign-out
    again = await ppe.suspend_partner(partner_id, current_user=SUPER)
    assert again["partner"]["status"] == "suspended"
    assert wired.revoke.await_count >= 4


async def test_suspending_twice_or_reinstating_an_active_partner_changes_nothing(wired):
    partner_id = await _partner_with_world(wired)
    first = await ppe.suspend_partner(partner_id, current_user=SUPER)
    stamp = (await wired.db.tenants.find_one({"id": partner_id}))["partner"]["suspendedAt"]
    second = await ppe.suspend_partner(partner_id, current_user=SUPER)
    assert second == first
    assert (await wired.db.tenants.find_one({"id": partner_id}))["partner"]["suspendedAt"] == stamp
    assert len(_actions(wired, "partner.suspended", partner_id)) == 1
    await ppe.reinstate_partner(partner_id, current_user=SUPER)
    active = await ppe.reinstate_partner(partner_id, current_user=SUPER)
    assert active["partner"]["status"] == "active"
    assert len(_actions(wired, "partner.reinstated", partner_id)) == 1


async def test_reinstate_restores_selling_and_clears_the_suspension_fields(wired):
    import partner_pool
    partner_id = await _partner_with_world(wired)
    await ppe.suspend_partner(partner_id, current_user=SUPER)
    out = await ppe.reinstate_partner(partner_id, current_user=SUPER)
    doc = await wired.db.tenants.find_one({"id": partner_id})
    assert out["partner"]["status"] == "active"
    assert doc["partner"]["status"] == "active" and "suspendedAt" not in doc["partner"] and "suspendedBy" not in doc["partner"]
    assert await partner_pool.claim(wired.db, partner_id, 1, require_active=True) is True


async def test_suspend_and_reinstate_refuse_unknown_ids_and_other_callers(wired):
    partner_id = await _partner_with_world(wired)
    for handler in (ppe.suspend_partner, ppe.reinstate_partner):
        for missing in ("nope", "cust1"):
            refused = await handler(missing, current_user=SUPER)
            assert refused.status_code == 404 and _body(refused)["code"] == "not_found"
        for user in (PARTNER_ADMIN, SUPPORT):
            with pytest.raises(HTTPException) as exc:
                await handler(partner_id, current_user=user)
            assert exc.value.status_code == 403
    assert (await wired.db.tenants.find_one({"id": "cust1"}))["partnerId"] == partner_id
