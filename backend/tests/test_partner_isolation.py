"""Phase 87 plan 09 task 3: two partners never see or change each other's customers, the portal answers only
the D-01 facts, and a partner admin manages its own team (real MongoDB).

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Route functions are called with a TokenData; the audit writer and
the invite mailer are mocked, so no email leaves.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import partner_endpoints as pe
import partner_portal_service as service
import partner_store
from auth_types import TokenData
from partner_pool import PartnerError
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

FORBIDDEN_KEYS = ("registrationKey", "apiKeys", "emailConfig", "agentCapabilities", "hashed_password",
                  "tokenHash", "token", "link")
SECRET_VALUES = ("reg_SECRET_A1", "reg_SECRET_B1", "smtp.secret.example", "key_SECRET")


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


def _walk(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key), value
            yield from _walk(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _walk(value)


def _json_of(payload):
    return json.dumps(payload if isinstance(payload, (dict, list)) else _body(payload))


def assert_clean(payload, *, allow=()):
    """No forbidden key at any depth and no seeded secret value anywhere in the answer."""
    data = payload if isinstance(payload, (dict, list)) else _body(payload)
    keys = {key for key, _ in _walk(data)}
    assert not (keys & (set(FORBIDDEN_KEYS) - set(allow))), keys & set(FORBIDDEN_KEYS)
    text = json.dumps(data)
    assert not any(secret in text for secret in SECRET_VALUES)


async def _ctx(pid, role="partner_admin"):
    return await pe.current_partner(
        current_user=TokenData(username=f"{role}@{pid}.test", role=role, tenant_id=pid, mfa_verified=True))


async def _partner(wired, pid, name, pool=100):
    await wired.db.tenants.insert_one({
        "id": pid, "type": "partner", "name": name, "license": {"maxAgents": 0}, "maxAgents": 0,
        "partner": {"poolSize": pool, "allocated": 0, "status": "active", "screenCeiling": ["all"], "expiresAt": None},
    })


async def _customer(wired, cid, name, partner=None, seats=10, secret="reg_SECRET_A1"):
    doc = {"id": cid, "name": name, "license": {"maxAgents": seats, "seatsUsed": 2}, "maxAgents": seats,
           "enabledFeatures": ["view:dashboard"], "registrationKey": secret,
           "emailConfig": {"host": "smtp.secret.example"}, "apiKeys": ["key_SECRET"],
           "agentCapabilities": {"remote": True}}
    if partner:
        doc["partnerId"] = partner
    await wired.db.tenants.insert_one(doc)


async def _two_partners(wired):
    await _partner(wired, "partner_a", "Alpha Retail")
    await _partner(wired, "partner_b", "Beta Retail")
    for i in range(1, 4):
        await _customer(wired, f"a{i}", f"A Shop {i}", "partner_a")
        await _customer(wired, f"b{i}", f"B Shop {i}", "partner_b", secret="reg_SECRET_B1")
    await _customer(wired, "direct1", "Direct Shop")
    agents = []
    for cid in ("a1", "b1", "direct1"):
        for n, status in enumerate(("Online", "Offline", "Pending", "Rejected")):
            agents.append({"id": f"{cid}-{n}", "hostname": f"{cid}-h{n}", "tenantId": cid, "status": status})
    await wired.db.agents.insert_many(agents)


# --- PART-05: isolation --------------------------------------------------------------------------

async def test_a_partner_overview_lists_only_its_own_customers_with_exactly_the_d01_keys(wired):
    """protects=D-01 + PART-05; fails_when=B's customers, the direct customer or a partner organization
    appear, a row has another key, or any secret leaves."""
    await _two_partners(wired)
    out = await pe.get_overview(ctx=await _ctx("partner_a"))
    assert [row["id"] for row in out["customers"]] == ["a1", "a2", "a3"]
    assert all(set(row) == set(partner_store.CUSTOMER_FIELDS) for row in out["customers"])
    text = json.dumps(out)
    assert not any(other in text for other in ("b1", "b2", "b3", "direct1", "partner_b", "Beta"))
    assert_clean(out, allow=())
    assert "enabledFeatures" not in {key for key, _ in _walk(out)}
    mine = out["customers"][0]
    assert (mine["agentsOnline"], mine["agentsTotal"]) == (1, 2)


async def test_another_partners_ids_answer_the_same_404_as_an_unknown_id_and_change_nothing(wired):
    """protects=T-87-26 adjacency; fails_when=a foreign, direct or partner id answers differently, or
    B's seats, screens or pool move."""
    await _two_partners(wired)
    before = {d["id"]: d async for d in wired.db.tenants.find({}, {"_id": 0})}
    ctx = await _ctx("partner_a")
    unknown = await pe.put_customer_seats("zz-unknown", pe.SeatsBody(seats=1), ctx=ctx)
    unknown_f = await pe.get_customer_features("zz-unknown", ctx=ctx)
    for foreign in ("b1", "b2", "b3", "direct1", "partner_b", "partner_a"):
        seats = await pe.put_customer_seats(foreign, pe.SeatsBody(seats=1), ctx=ctx)
        assert seats.status_code == 404 and _body(seats) == _body(unknown), foreign
        for fn in (pe.get_customer_features,):
            got = await fn(foreign, ctx=ctx)
            assert got.status_code == 404 and _body(got) == _body(unknown_f), foreign
        put = await pe.put_customer_features(foreign, pe.FeaturesBody(enabledFeatures=["view:agents"]), ctx=ctx)
        assert put.status_code == 404 and _body(put) == _body(unknown_f), foreign
    after = {d["id"]: d async for d in wired.db.tenants.find({}, {"_id": 0})}
    assert after == before


async def test_a_partner_with_no_customers_gets_an_empty_overview_with_its_pool(wired):
    await _partner(wired, "partner_a", "Alpha Retail", pool=40)
    out = await pe.get_overview(ctx=await _ctx("partner_a"))
    assert out["customers"] == [] and out["pool"]["size"] == 40 and out["pool"]["free"] == 40


async def test_the_creation_and_seat_answers_carry_no_secret(wired):
    await _two_partners(wired)
    ctx = await _ctx("partner_a")
    made = await pe.post_customer(pe.CustomerCreate(name="New Shop", seats=5, adminName="Owner",
                                                    adminEmail="owner@newshop.test"), ctx=ctx)
    assert_clean(made)
    seats = await pe.put_customer_seats(made["customer"]["id"], pe.SeatsBody(seats=6), ctx=await _ctx("partner_a"))
    assert_clean(seats)
    assert set(seats) == {"customer", "pool"} and set(seats["customer"]) == set(partner_store.CUSTOMER_FIELDS)
    features = await pe.get_customer_features("a1", ctx=ctx)
    assert_clean(features, allow=())


# --- D-17: the partner's team --------------------------------------------------------------------

async def _staff(wired, uid, name, email, tenant, role="partner_admin"):
    await wired.db.users.insert_one({"id": uid, "email": email, "name": name, "full_name": name, "role": role,
                                     "tenantId": tenant, "status": "Active", "hashed_password": "x"})


async def test_the_team_lists_only_this_partners_staff_with_their_invite_status(wired):
    """protects=D-17; fails_when=another partner's or a customer's user is listed, a status is wrong,
    or a hash or token leaves."""
    await _two_partners(wired)
    await _staff(wired, "u2", "bea", "bea@alpha.test", "partner_a", "partner_viewer")
    await _staff(wired, "u1", "Ann", "ann@alpha.test", "partner_a")
    await _staff(wired, "u3", "Zed", "zed@beta.test", "partner_b")
    await _staff(wired, "u4", "Cust", "cust@a1.test", "a1", "Tenant Admin")
    out = await pe.get_team(ctx=await _ctx("partner_a"))
    assert [m["name"] for m in out["members"]] == ["Ann", "bea"]
    assert all(set(m) == {"id", "name", "email", "role", "status"} for m in out["members"])
    assert [m["role"] for m in out["members"]] == ["partner_admin", "partner_viewer"]
    assert [m["status"] for m in out["members"]] == ["active", "active"]
    assert_clean(out)


async def test_a_new_colleague_is_invited_until_the_password_is_set_and_expired_after_seven_days(wired):
    await _two_partners(wired)
    ctx = await _ctx("partner_a")
    made = await pe.post_colleague(pe.ColleagueInvite(name="Cara", email="Cara@Alpha.test", role="partner_viewer"),
                                   ctx=ctx)
    assert set(made) == {"member", "emailSent"} and made["member"]["status"] == "invited"
    assert made["member"]["role"] == "partner_viewer" and made["member"]["email"] == "cara@alpha.test"
    token = wired.mail.await_args.kwargs["token"]
    assert token not in _json_of(made)
    user = await wired.db.users.find_one({"email": "cara@alpha.test"})
    assert user["tenantId"] == "partner_a" and user["role"] == "partner_viewer"
    assert (await wired.db.invites.find_one({"email": "cara@alpha.test"}))["roleKind"] == "partner_viewer"
    sent = [c for c in wired.audit.await_args_list if c.args[0] == "partner.invite_sent"]
    assert sent and sent[-1].args[1] == "partner_a"
    team = await pe.get_team(ctx=ctx)
    assert team["members"][0]["status"] == "invited"
    late = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    await wired.db.password_reset_tokens.update_one({"email": "cara@alpha.test"}, {"$set": {"expires_at": late}})
    assert (await pe.get_team(ctx=ctx))["members"][0]["status"] == "invite_expired"
    await wired.db.password_reset_tokens.delete_many({"email": "cara@alpha.test"})
    assert (await pe.get_team(ctx=ctx))["members"][0]["status"] == "active"


async def test_only_the_two_partner_roles_can_be_invited_and_a_used_email_is_refused(wired):
    await _two_partners(wired)
    with pytest.raises(ValidationError):
        pe.ColleagueInvite(name="X", email="x@alpha.test", role="tenant_admin")
    partner = await wired.db.tenants.find_one({"id": "partner_a"})
    with pytest.raises(PartnerError) as exc:
        await service.invite_colleague(wired.db, partner, name="X", email="x@alpha.test", role="tenant_admin",
                                       actor=TokenData(username="a@a", role="partner_admin", tenant_id="partner_a"))
    assert exc.value.status == 422 and exc.value.code == "invalid_role"
    await _staff(wired, "u1", "Ann", "ann@alpha.test", "partner_a")
    refused = await pe.post_colleague(pe.ColleagueInvite(name="Ann 2", email="ANN@alpha.test", role="partner_admin"),
                                      ctx=await _ctx("partner_a"))
    assert refused.status_code == 409 and _body(refused)["code"] == "email_unavailable"


async def test_a_viewer_cannot_read_or_change_the_team(wired):
    """protects=D-04 + R7; fails_when=a viewer reaches any team route."""
    await _two_partners(wired)
    viewer = await _ctx("partner_a", "partner_viewer")
    for call in (pe.get_team(ctx=viewer),
                 pe.post_colleague(pe.ColleagueInvite(name="X", email="x@a.test", role="partner_admin"), ctx=viewer),
                 pe.post_resend_colleague("u1", ctx=viewer)):
        with pytest.raises(HTTPException) as exc:
            await call
        assert exc.value.status_code == 403


async def test_resend_works_only_before_a_password_is_set_and_only_inside_the_partner(wired):
    """protects=T-87-29; fails_when=an active person, another partner's user or a customer admin can be re-invited."""
    await _two_partners(wired)
    ctx = await _ctx("partner_a")
    made = await pe.post_colleague(pe.ColleagueInvite(name="Cara", email="cara@alpha.test", role="partner_admin"), ctx=ctx)
    first = wired.mail.await_args.kwargs["token"]
    again = await pe.post_resend_colleague(made["member"]["id"], ctx=ctx)
    assert again["emailSent"] is False and again["member"]["status"] == "invited"
    second = wired.mail.await_args.kwargs["token"]
    assert second != first and second not in _json_of(again)
    assert await wired.db.password_reset_tokens.count_documents({"email": "cara@alpha.test"}) == 1
    await wired.db.password_reset_tokens.delete_many({"email": "cara@alpha.test"})
    done = await pe.post_resend_colleague(made["member"]["id"], ctx=ctx)
    assert done.status_code == 409 and _body(done)["code"] == "already_active"
    await _staff(wired, "ub", "Zed", "zed@beta.test", "partner_b")
    await _staff(wired, "uc", "Cust", "cust@a1.test", "a1", "Tenant Admin")
    unknown = await pe.post_resend_colleague("nobody", ctx=ctx)
    for foreign in ("ub", "uc"):
        got = await pe.post_resend_colleague(foreign, ctx=ctx)
        assert got.status_code == unknown.status_code == 404 and _body(got) == _body(unknown)
