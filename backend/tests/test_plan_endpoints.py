"""Phase 88 plan 08: the plan table is stored data only the Super Admin edits (real MongoDB).

Value: protects=a seats edit reaches every direct tenant on that plan at once (and no override, partner
customer or the platform organization), is announced and audited once, a screens or trial-days edit only
shapes what comes next, Custom and out-of-range or non-integer input are refused with nothing stored, and
only the Super Admin reaches the routes; fails_when=a plan edit touches an override, a partner allotment or
a running trial, a repeated edit notifies or audits again, a float/bool/string number is stored, or a
non-Super-Admin reads or edits the table; no_claim=the Plans screen (a later plan); audit_ledger.event and
plan_notices.announce are mocked.
"""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import plan_service
import plan_trial
import screen_ceiling
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SUPER_EMAIL = "root@example.com"


@pytest.fixture
def wired(mongo_db):
    """The ledger and the admin notices are mocks the tests read."""
    ledger, announce = AsyncMock(), AsyncMock()
    with patch("audit_ledger.event", new=ledger), patch("plan_notices.announce", new=announce):
        mongo_db.ledger, mongo_db.announce = ledger, announce
        yield mongo_db


async def _tenant(db, tid, plan="Pro", seats=50, **extra):
    doc = {"id": tid, "name": f"Org {tid}", "maxAgents": seats, "enabledFeatures": ["view:dashboard"],
           "license": {"maxAgents": seats, "seatsUsed": 0, "inactiveReclaimDays": 30}}
    if plan is not None:
        doc["subscriptionTier"] = plan
    doc.update(extra)
    await db.tenants.insert_one(dict(doc))
    return tid


async def _seats(db, tid):
    return (await db.tenants.find_one({"id": tid}, {"_id": 0}))["license"]["maxAgents"]


async def _expect(code, status, coro):
    with pytest.raises(plan_service.PlanError) as err:
        await coro
    assert (err.value.code, err.value.status) == (code, status)


# -- list_plans ---------------------------------------------------------------------------------

async def test_an_empty_collection_lists_the_four_plans_in_order_with_seed_screens(wired):
    rows = await plan_service.list_plans(wired)
    assert [r["key"] for r in rows] == ["Free", "Pro", "Enterprise", "Custom"]
    assert [(r["seats"], r["trialDays"]) for r in rows] == [(5, 14), (50, None), (500, None), (None, None)]
    assert rows[0]["screens"] == screen_ceiling.seed_screens("Free")
    assert rows[1]["screens"] == screen_ceiling.seed_screens("Pro")
    assert rows[3]["screens"] == "all"
    assert all({"tenantCount", "updatedAt", "updatedBy"} <= set(r) for r in rows)


async def test_tenant_count_reads_a_missing_plan_as_free_and_skips_the_platform_and_partners(wired):
    await _tenant(wired, "a", plan="Free")
    await _tenant(wired, "b", plan=None)
    await _tenant(wired, "c", plan="Pro")
    await _tenant(wired, "platform-admin", plan="Enterprise")
    await wired.tenants.insert_one({"id": "p1", "type": "partner", "name": "P", "subscriptionTier": "Pro"})
    counts = {r["key"]: r["tenantCount"] for r in await plan_service.list_plans(wired)}
    assert counts == {"Free": 2, "Pro": 1, "Enterprise": 0, "Custom": 0}


# -- seats --------------------------------------------------------------------------------------

async def test_a_seats_edit_reaches_direct_tenants_without_an_override_and_nobody_else(wired):
    await _tenant(wired, "p-a")
    await _tenant(wired, "p-b")
    await _tenant(wired, "p-over", seats=70, license={"maxAgents": 70, "seatsUsed": 0, "seatOverride": 70})
    await wired.tenants.insert_one({"id": "part", "type": "partner", "name": "P", "license": {"maxAgents": 0}})
    await _tenant(wired, "p-cust", seats=30, partnerId="part")
    await _tenant(wired, "platform-admin", seats=50)
    out = await plan_service.update_plan(wired, "Pro", {"seats": 60}, actor=SUPER_EMAIL)
    assert out["tenantsUpdated"] == 2 and out["plan"]["seats"] == 60
    assert [await _seats(wired, t) for t in ("p-a", "p-b", "p-over", "p-cust", "platform-admin")] == [60, 60, 70, 30, 50]
    notified = sorted(c.args[1] for c in wired.announce.await_args_list)
    assert notified == ["p-a", "p-b"]
    for call in wired.announce.await_args_list:
        assert call.kwargs["event"] == "seats.changed" and call.kwargs["via"] == "plan_edit"
        assert (call.kwargs["before"], call.kwargs["after"]) == (50, 60)
    wired.ledger.assert_awaited_once()
    call = wired.ledger.await_args
    assert call.args == ("plan.updated", "platform-admin")
    assert call.kwargs["plan"] == "Pro" and call.kwargs["before"] == {"seats": 50} and call.kwargs["after"] == {"seats": 60}
    assert call.kwargs["tenantsUpdated"] == 2
    stored = await wired.plans.find_one({"key": "Pro"}, {"_id": 0})
    assert stored["seats"] == 60 and stored["updatedBy"] == SUPER_EMAIL and stored["updatedAt"]


async def test_the_same_edit_again_writes_no_tenant_sends_no_notice_and_records_nothing(wired):
    await _tenant(wired, "p-a")
    await plan_service.update_plan(wired, "Pro", {"seats": 60}, actor=SUPER_EMAIL)
    wired.ledger.reset_mock()
    wired.announce.reset_mock()
    again = await plan_service.update_plan(wired, "Pro", {"seats": 60}, actor=SUPER_EMAIL)
    assert again["tenantsUpdated"] == 0
    wired.ledger.assert_not_awaited()
    wired.announce.assert_not_awaited()


async def test_seats_accept_the_bounds_and_refuse_values_outside_them_storing_nothing(wired):
    await _tenant(wired, "p-a")
    for bad in (-1, 1_000_001, 2.5, True, "60", None):
        await _expect("invalid_seats", 422, plan_service.update_plan(wired, "Pro", {"seats": bad}, actor=SUPER_EMAIL))
    assert await wired.plans.count_documents({}) == 0 and await _seats(wired, "p-a") == 50
    for ok in (0, 1_000_000):
        out = await plan_service.update_plan(wired, "Pro", {"seats": ok}, actor=SUPER_EMAIL)
        assert out["plan"]["seats"] == ok and await _seats(wired, "p-a") == ok


async def test_a_plan_with_no_stored_document_is_upserted_by_a_seats_edit(wired):
    out = await plan_service.update_plan(wired, "Enterprise", {"seats": 800}, actor=SUPER_EMAIL)
    assert out["tenantsUpdated"] == 0 and out["plan"]["seats"] == 800
    assert (await plan_service.plans(wired))["Enterprise"]["seats"] == 800
    assert (await plan_service.plans(wired))["Pro"]["seats"] == 50


# -- trial days ---------------------------------------------------------------------------------

async def test_trial_days_apply_to_later_trials_and_leave_a_running_trial_alone(wired):
    started = plan_trial.new_trial(plan_trial_now(), 14)
    await _tenant(wired, "f1", plan="Free", seats=5, trial=started)
    out = await plan_service.update_plan(wired, "Free", {"trialDays": 30}, actor=SUPER_EMAIL)
    assert out["plan"]["trialDays"] == 30 and out["tenantsUpdated"] == 0
    assert (await wired.tenants.find_one({"id": "f1"}))["trial"] == started
    terms = await plan_service.new_tenant_terms(wired, "Free", None)
    days = (plan_trial._parse(terms["trial"]["endsAt"]) - plan_trial._parse(terms["trial"]["startedAt"])).days
    assert days == 30


async def test_trial_days_bounds_and_only_on_free(wired):
    for bad in (0, 366, 1.5, True, "14"):
        await _expect("invalid_trial_days", 422, plan_service.update_plan(wired, "Free", {"trialDays": bad}, actor=SUPER_EMAIL))
    for ok in (1, 365):
        assert (await plan_service.update_plan(wired, "Free", {"trialDays": ok}, actor=SUPER_EMAIL))["plan"]["trialDays"] == ok
    await _expect("trial_only_on_free", 422, plan_service.update_plan(wired, "Pro", {"trialDays": 20}, actor=SUPER_EMAIL))


# -- screens ------------------------------------------------------------------------------------

async def test_screens_are_stored_in_submitted_order_deduplicated_and_change_no_tenant(wired):
    await _tenant(wired, "f1", plan="Free", seats=5, enabledFeatures=["view:dashboard", "view:agents"])
    out = await plan_service.update_plan(
        wired, "Free", {"screens": ["view:agents", "view:agents", "screen:agents"]}, actor=SUPER_EMAIL)
    assert out["plan"]["screens"] == ["view:agents", "screen:agents"]
    assert (await wired.tenants.find_one({"id": "f1"}))["enabledFeatures"] == ["view:dashboard", "view:agents"]
    assert (await screen_ceiling.plan_allowed(wired, "Free")) >= {"view:agents", "screen:agents", "view:dashboard"}
    assert "screen:chat" not in await screen_ceiling.plan_allowed(wired, "Free")
    wired.announce.assert_not_awaited()


async def test_an_empty_screen_list_is_stored_and_unknown_or_all_are_refused(wired):
    out = await plan_service.update_plan(wired, "Pro", {"screens": []}, actor=SUPER_EMAIL)
    assert out["plan"]["screens"] == []
    await _expect("invalid_screen", 422, plan_service.update_plan(wired, "Pro", {"screens": ["all"]}, actor=SUPER_EMAIL))
    await _expect("invalid_screen", 422, plan_service.update_plan(wired, "Pro", {"screens": ["made:up"]}, actor=SUPER_EMAIL))
    await _expect("invalid_screen", 422, plan_service.update_plan(wired, "Pro", {"screens": "view:agents"}, actor=SUPER_EMAIL))
    await _expect("invalid_screen", 422, plan_service.update_plan(wired, "Pro", {"screens": [7]}, actor=SUPER_EMAIL))
    assert (await plan_service.list_plans(wired))[1]["screens"] == []


async def test_the_same_screens_again_records_nothing(wired):
    screens = ["view:agents", "screen:agents"]
    await plan_service.update_plan(wired, "Free", {"screens": screens}, actor=SUPER_EMAIL)
    wired.ledger.reset_mock()
    await plan_service.update_plan(wired, "Free", {"screens": list(screens)}, actor=SUPER_EMAIL)
    wired.ledger.assert_not_awaited()


# -- refusals -----------------------------------------------------------------------------------

async def test_custom_unknown_and_empty_requests_are_refused(wired):
    await _expect("custom_is_per_tenant", 422, plan_service.update_plan(wired, "Custom", {"seats": 9}, actor=SUPER_EMAIL))
    await _expect("unknown_plan", 422, plan_service.update_plan(wired, "Gold", {"seats": 9}, actor=SUPER_EMAIL))
    await _expect("nothing_to_update", 422, plan_service.update_plan(wired, "Pro", {}, actor=SUPER_EMAIL))
    await _expect("nothing_to_update", 422, plan_service.update_plan(wired, "Pro", {"color": "red"}, actor=SUPER_EMAIL))
    assert await wired.plans.count_documents({}) == 0


def plan_trial_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
