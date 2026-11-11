"""Phase 88 plan 10: plans inside the partner channel (real MongoDB).

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Route functions are called with a TokenData; the audit writer
and the invite mailer are mocked, so nothing reaches the live database or a mail server.
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import partner_endpoints as pe
import partner_platform_endpoints as ppe
import partner_store
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)


@pytest.fixture
def wired(mongo_db):  # noqa: F811
    handle = SimpleNamespace(db=mongo_db)
    with patch.object(ppe, "mongodb", handle), patch.object(pe, "mongodb", handle), \
            patch("audit_ledger.event", new=AsyncMock()) as audit, \
            patch("partner_invites.send_invite_email", new=AsyncMock(return_value=False)):
        yield SimpleNamespace(db=mongo_db, audit=audit)


def _body(response):
    return json.loads(response.body)


def _actions(wired, action, tenant=None):
    return [c for c in wired.audit.await_args_list
            if c.args[0] == action and (tenant is None or c.args[1] == tenant)]


async def _appoint(name="Retailer A", **extra):
    out = await ppe.create_partner(
        ppe.PartnerCreate(name=name, poolSize=100, screenCeiling=["all"], adminName="Bo Boss",
                          adminEmail=f"boss@{name.lower().replace(' ', '')}.test", **extra),
        current_user=SUPER)
    return out["partner"]


async def _stored_partner(wired, pid):
    return (await wired.db.tenants.find_one({"id": pid}))["partner"]


# --- Task 1: the Super Admin sets each partner's plan ceiling (D-13) ---------------------------------------

async def test_appointing_with_a_plan_ceiling_stores_canonical_keys_in_order(wired):
    """protects=D-13 the ceiling is stored as canonical plan keys; fails_when=case is kept or a duplicate stays."""
    summary = await _appoint(planCeiling=["Pro", "free", "PRO"])
    assert (await _stored_partner(wired, summary["id"]))["planCeiling"] == ["Pro", "Free"]
    assert summary["planCeiling"] == ["Pro", "Free"]


async def test_appointing_without_a_plan_ceiling_stores_free_only(wired):
    """protects=an omitted ceiling is ['Free']; fails_when=a partner can sell paid plans by default."""
    summary = await _appoint()
    assert (await _stored_partner(wired, summary["id"]))["planCeiling"] == ["Free"]
    assert summary["planCeiling"] == ["Free"]


async def test_an_unknown_plan_at_appointment_is_refused_before_anything_is_written(wired):
    """protects=422 invalid_plan with no partner stored; fails_when=a half-appointed partner remains."""
    out = await ppe.create_partner(
        ppe.PartnerCreate(name="Bad", poolSize=5, screenCeiling=["all"], adminName="Bo", adminEmail="bo@bad.test",
                          planCeiling=["Gold"]), current_user=SUPER)
    assert out.status_code == 422 and _body(out)["code"] == "invalid_plan"
    assert await wired.db.tenants.count_documents({"type": "partner"}) == 0


async def test_editing_the_plan_ceiling_stores_it_and_records_the_change_on_both_ledgers(wired):
    """protects=D-13 update records before and after; fails_when=no ledger entry or the platform ledger is missed."""
    pid = (await _appoint())["id"]
    out = await ppe.update_partner(pid, ppe.PartnerUpdate(planCeiling=["Free", "Pro", "Enterprise"]), current_user=SUPER)
    assert out["partner"]["planCeiling"] == ["Free", "Pro", "Enterprise"]
    assert (await _stored_partner(wired, pid))["planCeiling"] == ["Free", "Pro", "Enterprise"]
    changed = _actions(wired, "partner.plan_ceiling_changed")
    assert {c.args[1] for c in changed} == {pid, "platform-admin"}
    assert changed[0].kwargs["before"] == ["Free"] and changed[0].kwargs["after"] == ["Free", "Pro", "Enterprise"]


async def test_an_unknown_plan_in_an_edit_is_refused_and_changes_nothing(wired):
    """protects=422 invalid_plan; fails_when=the stored ceiling changes or an event is recorded."""
    pid = (await _appoint())["id"]
    out = await ppe.update_partner(pid, ppe.PartnerUpdate(planCeiling=["Gold"]), current_user=SUPER)
    assert out.status_code == 422 and _body(out)["code"] == "invalid_plan"
    assert (await _stored_partner(wired, pid))["planCeiling"] == ["Free"]
    assert _actions(wired, "partner.plan_ceiling_changed") == []


async def test_saving_the_same_ceiling_again_records_nothing(wired):
    """protects=no noise in the ledger; fails_when=an unchanged list is recorded as a change."""
    pid = (await _appoint(planCeiling=["Free", "Pro"]))["id"]
    await ppe.update_partner(pid, ppe.PartnerUpdate(planCeiling=["free", "pro"]), current_user=SUPER)
    assert _actions(wired, "partner.plan_ceiling_changed") == []


async def test_an_empty_ceiling_is_allowed_and_means_no_plan_changes(wired):
    """protects=an empty list is stored as given; fails_when=it is replaced by the default."""
    pid = (await _appoint())["id"]
    out = await ppe.update_partner(pid, ppe.PartnerUpdate(planCeiling=[]), current_user=SUPER)
    assert out["partner"]["planCeiling"] == []
    assert (await _stored_partner(wired, pid))["planCeiling"] == []


async def test_a_partner_stored_before_phase_88_summarizes_as_free_only(wired):
    """protects=A-88-PLAN-CEILING-DEFAULT, fail closed; fails_when=the summary invents paid plans or omits the field."""
    doc = {"id": "partner_old", "name": "Old", "type": "partner", "partner": {"poolSize": 5, "allocated": 0}}
    assert partner_store.plan_ceiling(doc) == ["Free"]
    assert partner_store.partner_summary(doc, 0)["planCeiling"] == ["Free"]
    assert partner_store.partner_summary({**doc, "partner": {"planCeiling": ["Pro"]}}, 0)["planCeiling"] == ["Pro"]


# --- Task 2: a partner's new customer starts on a plan with its trial (D-11, D-13, D-23, D-30) -------------

import partner_portal_service  # noqa: E402
import plan_trial  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402


def _user(pid, role="partner_admin"):
    return TokenData(username=f"{role}@retail.test", role=role, tenant_id=pid, mfa_verified=True)


async def _partner(wired, pid="partner_a", ceiling=("Free", "Pro"), pool=100, with_ceiling=True):
    partner = {"poolSize": pool, "allocated": 0, "status": "active", "screenCeiling": ["all"], "expiresAt": None}
    if with_ceiling:
        partner["planCeiling"] = list(ceiling)
    await wired.db.tenants.insert_one({"id": pid, "type": "partner", "name": f"Partner {pid}",
                                       "license": {"maxAgents": 0}, "maxAgents": 0, "partner": partner})
    return pid


async def _ctx(pid="partner_a", role="partner_admin"):
    return await pe.current_partner(current_user=_user(pid, role))


def _new(name="Cafe One", seats=20, email="owner@cafeone.test", plan=None):
    return pe.CustomerCreate(name=name, seats=seats, adminName="Owner", adminEmail=email, plan=plan)


async def _stored(wired, cid):
    return await wired.db.tenants.find_one({"id": cid})


async def test_a_new_customer_starts_on_free_with_a_fourteen_day_trial_and_the_allotment_as_seats(wired):
    """protects=D-23 and D-11; fails_when=the plan's 5 seats replace the allotment, no trial starts or the row hides them."""
    await _partner(wired)
    before = datetime.now(timezone.utc)
    out = await pe.post_customer(_new(), ctx=await _ctx())
    row = out["customer"]
    doc = await _stored(wired, row["id"])
    assert doc["subscriptionTier"] == "Free" and doc["license"]["maxAgents"] == 20 and "seatOverride" not in doc["license"]
    trial = doc["trial"]
    assert trial["consumed"] is False and trial["startedAt"]
    ends = datetime.fromisoformat(trial["endsAt"])
    assert timedelta(days=13, hours=23) < ends - before < timedelta(days=14, minutes=1)
    assert row["plan"] == "Free" and row["trialEndsAt"] == trial["endsAt"] and row["seatsAssigned"] == 20


async def test_a_new_customer_on_a_paid_plan_inside_the_ceiling_has_a_consumed_trial(wired):
    """protects=D-23; fails_when=a paid customer gets a running trial or the row shows a trial end."""
    await _partner(wired)
    out = await pe.post_customer(_new(plan="pro"), ctx=await _ctx())
    doc = await _stored(wired, out["customer"]["id"])
    assert doc["subscriptionTier"] == "Pro" and doc["trial"]["consumed"] is True and doc["license"]["maxAgents"] == 20
    assert out["customer"]["plan"] == "Pro" and out["customer"]["trialEndsAt"] is None


async def test_a_plan_outside_the_ceiling_is_refused_before_any_pool_claim(wired):
    """protects=T-88-29 at creation; fails_when=seats are claimed or a customer stored."""
    await _partner(wired)
    out = await pe.post_customer(_new(plan="Enterprise"), ctx=await _ctx())
    assert out.status_code == 422 and _body(out)["code"] == "plan_outside_ceiling"
    assert (await wired.db.tenants.find_one({"id": "partner_a"}))["partner"]["allocated"] == 0
    assert await wired.db.tenants.count_documents({"partnerId": "partner_a"}) == 0


async def test_an_unknown_plan_at_customer_creation_is_a_422(wired):
    """protects=unknown_plan; fails_when=an unknown value is stored or reads as Free."""
    await _partner(wired)
    out = await pe.post_customer(_new(plan="Gold"), ctx=await _ctx())
    assert out.status_code == 422 and _body(out)["code"] == "unknown_plan"
    assert await wired.db.tenants.count_documents({"partnerId": "partner_a"}) == 0


async def test_a_partner_without_a_stored_ceiling_can_only_create_free_customers(wired):
    """protects=A-88-PLAN-CEILING-DEFAULT; fails_when=an old partner sells a paid plan."""
    await _partner(wired, with_ceiling=False)
    out = await pe.post_customer(_new(plan="Pro"), ctx=await _ctx())
    assert out.status_code == 422 and _body(out)["code"] == "plan_outside_ceiling"
    ok = await pe.post_customer(_new(), ctx=await _ctx())
    assert ok["customer"]["plan"] == "Free"


async def test_every_customer_row_is_exactly_the_customer_fields_ending_with_plan_and_trial_end(wired):
    """protects=T-88-30 and D-01; fails_when=a key is added, reordered or a trial record leaks."""
    await _partner(wired)
    await pe.post_customer(_new(), ctx=await _ctx())
    await pe.post_customer(_new(name="Cafe Two", email="o@cafetwo.test", plan="Pro"), ctx=await _ctx())
    await wired.db.tenants.insert_one({"id": "old", "name": "Old", "partnerId": "partner_a", "license": {"maxAgents": 3}})
    rows = (await pe.get_overview(ctx=await _ctx()))["customers"]
    assert len(rows) == 3 and all(tuple(row) == partner_store.CUSTOMER_FIELDS for row in rows)
    assert partner_store.CUSTOMER_FIELDS[-2:] == ("plan", "trialEndsAt")
    old = next(r for r in rows if r["id"] == "old")
    assert old["plan"] == "Free" and old["trialEndsAt"] is None  # no trial record


async def test_the_overview_shows_the_plan_ceiling_beside_the_screen_ceiling(wired):
    """protects=D-30 the picker can show which plans are sellable; fails_when=planCeiling is missing."""
    await _partner(wired, ceiling=("Free", "Pro"))
    out = await pe.get_overview(ctx=await _ctx())
    assert out["planCeiling"] == ["Free", "Pro"] and "ceiling" in out
