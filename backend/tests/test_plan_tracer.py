"""Phase 88 plan 01 tracer: create on a plan, enroll, the Free trial ends, the next new machine is held
trial_ended while the first carries on, and the licence view reports it (real MongoDB, skips without one).

Value: protects=a tenant created on a plan takes its seats and trial from the stored plan table (an
explicit seat number is a named override), a new machine of a Free tenant whose trial has ended waits
Pending with trial_ended while the machine enrolled earlier keeps its seat, the platform organization
is never held, missing data fails open, and the licence route reports plan, seats and trial;
fails_when=seats or trial are read from code constants, an ended trial stops a running agent or is
ignored for a new one, platform-admin is held, a tenant with no trial record is held, or the licence
view drops a D-19 field; no_claim=the HTTP layer (route functions are called directly with a
TokenData), the later network and cross-tenant rules, and the trial reminders.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pending_agents
import plan_service
import plan_trial
import tenant_endpoints as te
from auth_types import TokenData
from tests import _enrollment_harness as harness
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)


@pytest.fixture(autouse=True)
def _fresh_status_cache():
    pending_agents._status_cache.clear()
    yield


@pytest.fixture
def wired(mongo_db):
    """The tenant routes run against the private database; auditing and notifications are mocked."""
    audit = MagicMock(log_action_async=AsyncMock())
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)), \
            patch("audit_service.get_audit_service", return_value=audit), \
            patch("notification_service.get_notification_service", return_value=MagicMock(send_alert=AsyncMock())), \
            patch("notification_service.send_notification", new=AsyncMock()), \
            patch.object(te, "get_database", return_value=mongo_db), \
            patch.object(te, "revoke_user_sessions", new=AsyncMock()):
        yield mongo_db


async def _stored(db, tenant_id):
    return await db.tenants.find_one({"id": tenant_id}, {"_id": 0})


def _near_now(iso, seconds=5):
    return abs(datetime.fromisoformat(iso) - datetime.now(timezone.utc)) < timedelta(seconds=seconds)


async def _end_trial(db, tenant_id, minutes_ago=1):
    ended = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"trial.endsAt": ended}})


# -- creation reads the stored plan -------------------------------------------------------------

async def test_free_tenant_takes_seats_and_trial_from_the_plan_table(wired):
    await plan_service.ensure_plans(wired)
    await wired.plans.update_one({"key": "Free"}, {"$set": {"seats": 6, "trialDays": 10}})
    out = await te.create_tenant(te.TenantCreate(name="Trial Co"), current_user=SUPER)
    stored = await _stored(wired, out["id"])
    assert stored["subscriptionTier"] == "Free"
    assert stored["license"]["maxAgents"] == 6 and "seatOverride" not in stored["license"]  # D-03: plan, not code
    trial = stored["trial"]
    assert _near_now(trial["startedAt"]) and trial["consumed"] is False
    assert datetime.fromisoformat(trial["endsAt"]) - datetime.fromisoformat(trial["startedAt"]) == timedelta(days=10)
    assert trial["extensions"] == [] and trial["remindersSent"] == []


async def test_free_defaults_are_five_seats_and_fourteen_days_with_an_empty_plans_collection(wired):
    defaults = await plan_service.plans(wired)
    assert {k: (p["seats"], p["trialDays"]) for k, p in defaults.items()} == {
        "Free": (5, 14), "Pro": (50, None), "Enterprise": (500, None), "Custom": (None, None)}
    out = await te.create_tenant(te.TenantCreate(name="Default Co"), current_user=SUPER)
    stored = await _stored(wired, out["id"])
    trial = stored["trial"]
    assert stored["license"]["maxAgents"] == 5
    assert datetime.fromisoformat(trial["endsAt"]) - datetime.fromisoformat(trial["startedAt"]) == timedelta(days=14)


async def test_explicit_seat_number_is_a_named_override(wired):
    out = await te.create_tenant(te.TenantCreate(name="Seven Co", maxAgents=7), current_user=SUPER)
    stored = await _stored(wired, out["id"])
    assert stored["license"]["maxAgents"] == 7 and stored["license"]["seatOverride"] == 7


async def test_pro_tenant_gets_a_consumed_trial_and_the_pro_seats(wired):
    out = await te.create_tenant(te.TenantCreate(name="Pro Co", subscriptionTier="pro"), current_user=SUPER)
    stored = await _stored(wired, out["id"])
    assert stored["subscriptionTier"] == "Pro" and stored["license"]["maxAgents"] == 50
    assert stored["trial"]["startedAt"] is None and stored["trial"]["consumed"] is True
    assert _near_now(stored["trial"]["endsAt"])


@pytest.mark.parametrize("plan,fragment", [("Custom", "seat number"), ("Gold", "Unknown plan")])
async def test_custom_without_seats_and_unknown_plans_are_refused_and_store_nothing(wired, plan, fragment):
    with pytest.raises(HTTPException) as err:
        await te.create_tenant(te.TenantCreate(name="Refused Co", subscriptionTier=plan), current_user=SUPER)
    assert err.value.status_code == 422 and fragment in err.value.detail
    assert await wired.tenants.count_documents({"name": "Refused Co"}) == 0


async def test_custom_with_a_seat_number_is_created(wired):
    out = await te.create_tenant(te.TenantCreate(name="Custom Co", subscriptionTier="Custom", maxAgents=12),
                                 current_user=SUPER)
    stored = await _stored(wired, out["id"])
    assert stored["license"]["maxAgents"] == 12 and stored["trial"]["consumed"] is True


# -- the tracer: create, enroll, trial ends, new machine held, first machine carries on ---------

async def test_trial_end_holds_the_next_new_machine_and_leaves_the_enrolled_one_alone(wired):
    out = await te.create_tenant(te.TenantCreate(name="Trial Co"), current_user=SUPER)
    tid, key = out["id"], out["registrationKey"]
    import importlib
    await importlib.import_module("migrations.013_enrollment_controls").up(wired)

    code, first = await harness.register(wired, "m1", key=key, hardware=harness.hw("S1"))
    assert code == 200
    await _end_trial(wired, tid)

    code, second = await harness.register(wired, "m2", key=key, hardware=harness.hw("S2"))
    assert code == 202 and second["pendingReason"] == "trial_ended"
    held = await wired.agents.find_one({"hostname": "m2"})
    assert held["status"] == "Pending" and held["pendingReason"] == "trial_ended"

    code, again = await harness.register(wired, "m1", key=key, hardware=harness.hw("S1"),
                                         agentSecret=first["agentSecret"])
    assert code == 200
    assert (await wired.agents.find_one({"hostname": "m1"}))["status"] == "Online"  # PROH-88-01: keeps its seat
    assert (await _stored(wired, tid))["license"]["seatsUsed"] == 1

    view = await te.get_tenant_license(tid, current_user=TokenData(
        username="a@trial.example", role="Tenant Admin", tenant_id=tid, mfa_verified=True))
    assert view["plan"] == "Free" and view["maxAgents"] == 5 and view["planSeats"] == 5
    assert view["seatOverride"] is None and view["partnerManaged"] is False and view["exempt"] is False
    assert view["trial"]["ended"] is True and view["trial"]["daysLeft"] == 0
    # 88-05: the first machine taught the tenant its network (D-06), and the view reports it
    assert [(n["cidr"], n["source"]) for n in view["allowedNetworks"]] == [("203.0.113.7/32", "learned")]
    assert view["seatsUsed"] == 1


async def test_a_running_trial_does_not_hold_new_machines(wired):
    out = await te.create_tenant(te.TenantCreate(name="Open Co"), current_user=SUPER)
    import importlib
    await importlib.import_module("migrations.013_enrollment_controls").up(wired)
    code, _ = await harness.register(wired, "m1", key=out["registrationKey"], hardware=harness.hw("S1"))
    assert code == 200


async def test_pro_tenant_new_machine_is_not_held_by_its_consumed_trial(mongo_db):
    await harness.tenant(mongo_db, "t-pro", plan="Pro", trial=plan_trial.consumed_trial(datetime.now(timezone.utc)))
    code, _ = await harness.register(mongo_db, "m1", hardware=harness.hw("S1"))
    assert code == 200


async def test_platform_admin_is_never_held_trial_ended(mongo_db):
    await harness.tenant(mongo_db, plan_service.PLATFORM_TENANT_ID, plan="Free",
                         trial=plan_trial.new_trial(datetime.now(timezone.utc) - timedelta(days=30), 14))
    code, _ = await harness.register(mongo_db, "m1", hardware=harness.hw("S1"))
    assert code == 200


async def test_a_tenant_with_no_plan_and_no_trial_record_is_not_held(mongo_db):
    await harness.tenant(mongo_db, "t-bare", plan=None, trial=None)
    assert plan_service.plan_key_of(await mongo_db.tenants.find_one({"id": "t-bare"})) == "Free"
    code, _ = await harness.register(mongo_db, "m1", hardware=harness.hw("S1"))
    assert code == 200


async def test_an_unreadable_trial_record_fails_open(mongo_db):
    await harness.tenant(mongo_db, "t-junk", plan="Free", trial={"endsAt": "not a date"})
    code, _ = await harness.register(mongo_db, "m1", hardware=harness.hw("S1"))
    assert code == 200


async def test_the_old_agent_build_sees_the_trial_ended_text(mongo_db):
    await harness.tenant(mongo_db, "t-old", plan="Free", trial=plan_trial.new_trial(
        datetime.now(timezone.utc) - timedelta(days=15), 14))
    code, detail = await harness.register(mongo_db, "m1", hardware=harness.hw("S1"), supportsPending=False)
    assert code == 403 and detail.startswith("trial_ended:")
    assert "free trial" in pending_agents.reason_text("trial_ended")


# -- the trial record is pure data ---------------------------------------------------------------

def test_trial_ended_boundary_counts_the_exact_instant_as_ended():
    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    tenant = {"trial": {"endsAt": now.isoformat()}}
    assert plan_trial.ended(tenant, now) is True
    assert plan_trial.ended(tenant, now - timedelta(seconds=1)) is False
    assert plan_trial.ended({}, now) is False and plan_trial.ended(None, now) is False


def test_days_left_rounds_up_and_never_goes_below_zero():
    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    tenant = {"trial": {"endsAt": (now + timedelta(days=13, hours=2)).isoformat()}}
    assert plan_trial.days_left(tenant, now) == 14
    assert plan_trial.days_left({"trial": {"endsAt": (now - timedelta(days=3)).isoformat()}}, now) == 0
    assert plan_trial.days_left({"trial": {"endsAt": (now + timedelta(days=2)).isoformat()}}, now) == 2
    assert plan_trial.days_left({}, now) is None
    assert plan_trial.view(tenant, now)["daysLeft"] == 14 and plan_trial.view({}, now) is None


# -- the licence view ------------------------------------------------------------------------------

async def test_licence_view_for_the_platform_organization_has_no_seat_limit(mongo_db):
    await harness.tenant(mongo_db, plan_service.PLATFORM_TENANT_ID, plan="Free", max_agents=5)
    view = await plan_service.licence_view(mongo_db, plan_service.PLATFORM_TENANT_ID)
    assert view["exempt"] is True and view["maxAgents"] is None and view["seatsAvailable"] is None
    assert view["overBy"] == 0


async def test_licence_view_reports_a_partner_customers_override_and_projects_networks(mongo_db):
    await harness.tenant(mongo_db, "t-net", plan="Pro", partnerId="p1", max_agents=30,
                         license={"maxAgents": 30, "seatsUsed": 0, "inactiveReclaimDays": 30, "seatOverride": 30},
                         allowedNetworks=[{"cidr": "203.0.113.0/24", "source": "learned",
                                           "addedAt": "2026-11-10T00:00:00+00:00", "addedBy": "secret@x.example",
                                           "hostname": "pc-1"}])
    view = await plan_service.licence_view(mongo_db, "t-net")
    assert view["partnerManaged"] is True and view["seatOverride"] == 30 and view["planSeats"] == 50
    assert view["allowedNetworks"] == [{"cidr": "203.0.113.0/24", "source": "learned",
                                        "addedAt": "2026-11-10T00:00:00+00:00"}]  # no addedBy, no hostname
    assert view["trial"] is None


async def test_ensure_plans_never_overwrites_a_changed_plan(mongo_db):
    await plan_service.ensure_plans(mongo_db)
    await mongo_db.plans.update_one({"key": "Pro"}, {"$set": {"seats": 80}})
    await plan_service.ensure_plans(mongo_db)
    assert await mongo_db.plans.count_documents({}) == 4
    assert (await plan_service.plans(mongo_db))["Pro"]["seats"] == 80
