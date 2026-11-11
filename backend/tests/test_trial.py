"""Phase 88 plan 06: the Super Admin extends a Free trial and clears a seat override; a sign-up's trial starts
at approval; every Free trial is reminded 7 and 1 days before it ends (real MongoDB).

Value: protects=a trial extension is bounded, Free-only, audited and never lost to a concurrent one, a seat
override returns to the plan's number only for a direct tenant on a numbered plan, and an ended trial stops
nothing that is running; fails_when=an extension runs for a paid plan or the platform organization, two
extensions silently overwrite each other, a partner customer's allotment is cleared as an override, or a
tenant admin can extend its own trial; no_claim=the HTTP layer (route functions are called directly with a
TokenData) and the e-mail channel; the audit ledger and audit service are mocked.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import licensing
import notification_audience
import pending_agents
import plan_service
import plan_trial
import tenant_endpoints as te
import tenant_signup_endpoints as tse
from auth_types import TokenData
from tests import _enrollment_harness as harness
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)
ADMIN = TokenData(username="admin@t1.example", role="Tenant Admin", tenant_id="t1", mfa_verified=True)
NOW = datetime.now(timezone.utc)


@pytest.fixture
def wired(mongo_db):
    """The tenant routes run against the private database; the ledger and auditing are mocked."""
    audit = MagicMock(log_action_async=AsyncMock())
    ledger = AsyncMock()
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)), \
            patch("audit_service.get_audit_service", return_value=audit), \
            patch("audit_ledger.event", new=ledger):
        mongo_db.ledger = ledger
        yield mongo_db


def _trial_ending_in(**delta):
    """A running Free trial whose end is ``delta`` from now (negative: it ended that long ago)."""
    ends = NOW + timedelta(**delta)
    return {**plan_trial.new_trial(ends - timedelta(days=14), 14), "remindersSent": [7]}


async def _tenant(db, tid="t1", plan="Free", seats=5, trial=None, override=None, partner_id=None, **extra):
    doc = {"id": tid, "name": f"Org {tid}", "maxAgents": seats,
           "license": {"maxAgents": seats, "seatsUsed": 0, "inactiveReclaimDays": 30}, **extra}
    if plan is not None:
        doc["subscriptionTier"] = plan
    if trial is not None:
        doc["trial"] = trial
    if override is not None:
        doc["license"]["seatOverride"] = override
    if partner_id:
        doc["partnerId"] = partner_id
    await db.tenants.insert_one(doc)
    return tid


async def _stored(db, tid="t1"):
    return await db.tenants.find_one({"id": tid}, {"_id": 0})


def _events(db, name):
    return [c for c in db.ledger.await_args_list if c.args and c.args[0] == name]


async def _patch(db, tid, **fields):
    return await te.update_tenant_license(tid, te.LicenseUpdate(**fields), current_user=SUPER)


# -- LIC-03 (D-15): the Super Admin extends a Free trial -----------------------------------------------------

async def test_an_extension_moves_the_end_clears_reminders_and_is_recorded(wired):
    await _tenant(wired, trial=_trial_ending_in(days=3))
    old_end = plan_trial.ends_at(await _stored(wired))
    out = await _patch(wired, "t1", trialExtendDays=7)
    stored = await _stored(wired)
    assert plan_trial.ends_at(stored) == old_end + timedelta(days=7)
    assert stored["trial"]["remindersSent"] == []
    (ext,) = stored["trial"]["extensions"]
    assert ext["by"] == "root@example.com" and ext["days"] == 7
    assert ext["from"] == old_end.isoformat() and ext["to"] == (old_end + timedelta(days=7)).isoformat()
    assert out["trial"]["daysLeft"] == 10 and out["trial"]["ended"] is False
    (call,) = _events(wired, "trial.extended")
    assert call.args[1] == "t1" and call.kwargs["days"] == 7


async def test_extending_an_ended_trial_reopens_it_from_now(wired):
    await _tenant(wired, trial=_trial_ending_in(days=-2))
    out = await _patch(wired, "t1", trialExtendDays=7)
    stored = await _stored(wired)
    assert abs(plan_trial.ends_at(stored) - (datetime.now(timezone.utc) + timedelta(days=7))) < timedelta(seconds=10)
    assert out["trial"]["ended"] is False and out["trial"]["daysLeft"] == 7


async def test_extending_a_tenant_with_no_trial_record_starts_one(wired):
    await _tenant(wired, trial=None)
    await _patch(wired, "t1", trialExtendDays=5)
    stored = await _stored(wired)
    assert stored["trial"]["consumed"] is False and len(stored["trial"]["extensions"]) == 1
    assert plan_trial.days_left(stored) == 5


@pytest.mark.parametrize("days", [0, 366, -1])
def test_extension_days_are_bounded_by_validation(days):
    with pytest.raises(ValueError):
        te.LicenseUpdate(trialExtendDays=days)


@pytest.mark.parametrize("tid,plan", [("t1", "Pro"), ("platform-admin", "Free")])
async def test_only_a_free_tenant_can_be_extended_and_nothing_is_written(wired, tid, plan):
    await _tenant(wired, tid=tid, plan=plan, trial=_trial_ending_in(days=3))
    before = (await _stored(wired, tid))["trial"]
    with pytest.raises(HTTPException) as err:
        await _patch(wired, tid, trialExtendDays=7)
    assert err.value.status_code == 422 and "trial" in err.value.detail.lower()
    assert (await _stored(wired, tid))["trial"] == before
    assert _events(wired, "trial.extended") == []


async def test_two_concurrent_extensions_never_lose_one_silently(wired):
    await _tenant(wired, trial=_trial_ending_in(days=3))
    old_end = plan_trial.ends_at(await _stored(wired))
    results = await asyncio.gather(
        plan_trial.extend(wired, "t1", 7, actor=SUPER, via="super_admin"),
        plan_trial.extend(wired, "t1", 7, actor=SUPER, via="super_admin"), return_exceptions=True)
    stored = await _stored(wired)
    landed = [r for r in results if not isinstance(r, BaseException)]
    lost = [r for r in results if isinstance(r, BaseException)]
    assert len(landed) >= 1 and len(landed) + len(lost) == 2
    assert all(isinstance(e, plan_trial.TrialError) and e.status == 409 and e.code == "trial_changed" for e in lost)
    assert plan_trial.ends_at(stored) == old_end + timedelta(days=7 * len(landed))
    assert len(stored["trial"]["extensions"]) == len(landed)


async def test_a_tenant_admin_cannot_extend_its_own_trial(wired):
    await _tenant(wired, trial=_trial_ending_in(days=3))
    with pytest.raises(HTTPException) as err:
        await te.update_tenant_license("t1", te.LicenseUpdate(trialExtendDays=30), current_user=ADMIN)
    assert err.value.status_code == 403
    assert (await _stored(wired))["trial"]["extensions"] == []


# -- LIC-01 (D-09, D-25): an override returns to the plan's number --------------------------------------------

async def test_clearing_an_override_restores_the_plans_seats_and_announces_it(wired):
    await _tenant(wired, seats=12, override=12, trial=_trial_ending_in(days=3))
    out = await _patch(wired, "t1", clearSeatOverride=True)
    stored = await _stored(wired)
    assert "seatOverride" not in stored["license"]
    assert (stored["license"]["maxAgents"], stored["maxAgents"], out["maxAgents"]) == (5, 5, 5)
    (call,) = _events(wired, "seats.changed")
    assert (call.kwargs["before"], call.kwargs["after"]) == (12, 5)


async def test_clearing_is_refused_for_a_partner_customer_and_for_custom(wired):
    await _tenant(wired, tid="cust", plan="Pro", seats=8, partner_id="p1")
    await _tenant(wired, tid="cu", plan="Custom", seats=9, override=9)
    with pytest.raises(HTTPException) as err:
        await _patch(wired, "cust", clearSeatOverride=True)
    assert err.value.status_code == 409
    with pytest.raises(HTTPException) as err:
        await _patch(wired, "cu", clearSeatOverride=True)
    assert err.value.status_code == 422
    assert (await _stored(wired, "cust"))["license"]["maxAgents"] == 8
    assert (await _stored(wired, "cu"))["license"]["seatOverride"] == 9


async def test_a_seat_number_set_on_a_direct_tenant_is_an_override_and_is_announced(wired):
    await _tenant(wired, trial=_trial_ending_in(days=3))
    await _patch(wired, "t1", maxAgents=9)
    stored = await _stored(wired)
    assert stored["license"]["seatOverride"] == 9 and stored["license"]["maxAgents"] == 9
    (call,) = _events(wired, "seats.changed")
    assert (call.kwargs["before"], call.kwargs["after"]) == (5, 9)


async def test_a_licence_patch_that_changes_no_seats_announces_nothing(wired):
    await _tenant(wired, trial=_trial_ending_in(days=3))
    await _patch(wired, "t1", inactiveReclaimDays=14)
    assert _events(wired, "seats.changed") == []


# -- LIC-03 (D-23): a sign-up's trial starts when the Super Admin approves it --------------------------------

async def _pending_signup(db, tid="tp"):
    """The tenant document /api/auth/signup writes: Free, a top-level seat number and no licence or trial."""
    await db.tenants.insert_one({"id": tid, "name": "ABC", "status": "pending_approval", "subscriptionTier": "Free",
                                 "maxAgents": 5, "signupRequestedAt": datetime.now(timezone.utc).isoformat()})
    await db.users.insert_one({"email": "p@abc.test", "tenantId": tid, "status": "Pending"})


async def test_approving_a_signup_starts_its_trial_and_sets_its_seats(mongo_db):
    await _pending_signup(mongo_db)
    await mongo_db.plans.insert_one({"key": "Free", "seats": 6, "trialDays": 14})
    with patch.object(tse, "mongodb", SimpleNamespace(db=mongo_db)), patch.object(tse, "_audit", AsyncMock()):
        out = await tse.approve_signup("tp", current_user=SUPER)
    assert out["approved"] == "tp"
    stored = await _stored(mongo_db, "tp")
    assert stored["status"] == "active" and stored["license"]["maxAgents"] == 6 and stored["maxAgents"] == 6
    assert stored["trial"]["consumed"] is False and plan_trial.days_left(stored) == 14
    assert abs(datetime.fromisoformat(stored["trial"]["startedAt"]) - datetime.now(timezone.utc)) < timedelta(seconds=10)


async def test_starting_a_trial_twice_changes_nothing(mongo_db):
    await _pending_signup(mongo_db)
    assert await plan_trial.start_for_signup(mongo_db, "tp") is True
    first = await _stored(mongo_db, "tp")
    assert await plan_trial.start_for_signup(mongo_db, "tp") is False
    assert await _stored(mongo_db, "tp") == first


async def test_a_signup_whose_trial_could_not_start_is_still_approved(mongo_db):
    await _pending_signup(mongo_db)
    with patch.object(tse, "mongodb", SimpleNamespace(db=mongo_db)), patch.object(tse, "_audit", AsyncMock()), \
            patch.object(plan_trial, "start_for_signup", AsyncMock(side_effect=RuntimeError("store down"))):
        out = await tse.approve_signup("tp", current_user=SUPER)
    assert out["approved"] == "tp" and (await _stored(mongo_db, "tp"))["status"] == "active"


async def test_start_for_signup_leaves_a_paid_plan_and_a_tenant_with_a_trial_alone(mongo_db):
    await _tenant(mongo_db, tid="pro", plan="Pro", seats=50)
    await _tenant(mongo_db, tid="has", trial=_trial_ending_in(days=3))
    before = await _stored(mongo_db, "has")
    assert await plan_trial.start_for_signup(mongo_db, "pro") is False
    assert await plan_trial.start_for_signup(mongo_db, "has") is False
    assert "trial" not in await _stored(mongo_db, "pro") and await _stored(mongo_db, "has") == before


# -- LIC-03 (D-16): the 7-day and 1-day reminders -------------------------------------------------------------

def _running(hours_left):
    ends = NOW + timedelta(hours=hours_left)
    return plan_trial.new_trial(ends - timedelta(days=14), 14)


async def _notices(db, tenant_id):
    return await db.notifications.find({"tenantId": tenant_id, "metadata.event": "trial.reminder"}).to_list(20)


async def test_reminders_go_out_once_per_threshold_and_re_arm_after_an_extension(wired):
    await _tenant(wired, trial=_running(6 * 24))
    assert await plan_trial.send_trial_reminders(wired, NOW) == 1
    assert await plan_trial.send_trial_reminders(wired, NOW) == 0
    assert await wired.notifications.count_documents({"tenantId": "platform-admin", "metadata.event": "trial.reminder"}) == 1
    (tenant_notice,) = await _notices(wired, "t1")
    assert tenant_notice["metadata"]["audience"] == "tenant_admins" and tenant_notice["metadata"]["daysLeft"] == 6
    assert "Org t1" in tenant_notice["title"] and tenant_notice["severity"] == "warning"
    later = NOW + timedelta(days=5, hours=4)   # 20 hours left
    assert await plan_trial.send_trial_reminders(wired, later) == 1
    assert await plan_trial.send_trial_reminders(wired, later) == 0
    assert (await _stored(wired))["trial"]["remindersSent"] == [7, 1]
    await _patch(wired, "t1", trialExtendDays=30)
    assert await plan_trial.send_trial_reminders(wired, NOW + timedelta(days=30)) == 1   # 6 days left again


async def test_a_tenant_first_seen_inside_the_last_day_gets_one_reminder(wired):
    await _tenant(wired, trial=_running(10))
    assert await plan_trial.send_trial_reminders(wired, NOW) == 1
    assert await plan_trial.send_trial_reminders(wired, NOW) == 0
    assert set((await _stored(wired))["trial"]["remindersSent"]) == {1, 7}


async def test_paid_consumed_ended_and_platform_tenants_get_no_reminder(wired):
    await _tenant(wired, tid="pro", plan="Pro", trial=_running(48))
    await _tenant(wired, tid="used", trial={**_running(48), "consumed": True})
    await _tenant(wired, tid="over", trial=_running(-5))
    await _tenant(wired, tid="platform-admin", trial=_running(48))
    await _tenant(wired, tid="far", trial=_running(20 * 24))
    assert await plan_trial.send_trial_reminders(wired, NOW) == 0
    assert await wired.notifications.count_documents({}) == 0


async def test_a_partners_customer_is_reminded_in_the_partners_own_feed(wired):
    await wired.tenants.insert_one({"id": "p1", "name": "Partner One", "type": "partner",
                                    "subscriptionTier": "Free", "trial": _running(48)})
    await _tenant(wired, tid="cust", trial=_running(48), partner_id="p1")
    assert await plan_trial.send_trial_reminders(wired, NOW) == 1   # the partner organization itself is not a trial
    (notice,) = await _notices(wired, "p1")
    assert "audience" not in notice["metadata"] and notice["metadata"]["customerId"] == "cust"
    admin = TokenData(username="boss@retail.test", role="partner_admin", tenant_id="p1", mfa_verified=True)
    with patch.object(notification_audience.rbac_service, "get_user_permissions", AsyncMock(return_value=["view:dashboard"])), \
            patch.object(notification_audience, "is_ticket_staff", AsyncMock(return_value=False)):
        flt = await notification_audience.reader_filter(admin, "p1")
    seen = await wired.notifications.find(flt).to_list(20)
    assert [n["alert_id"] for n in seen] == [notice["alert_id"]]
    (tenant_notice,) = await _notices(wired, "cust")
    assert tenant_notice["metadata"]["audience"] == "tenant_admins"


async def test_the_hourly_tick_sends_trial_reminders_even_when_an_earlier_step_raises(wired):
    import app_background_tasks
    await _tenant(wired, trial=_running(48))
    with patch.object(licensing, "reclaim_inactive_agents", AsyncMock(side_effect=RuntimeError("boom"))):
        await app_background_tasks.license_seat_tick(wired, 1)
    assert len(await _notices(wired, "t1")) == 1


# -- LIC-03 (D-20, D-21, D-22): an ended trial holds new machines and stops nothing else ----------------------

async def test_a_trial_ended_hold_is_approved_like_any_hold_and_the_trial_stays_ended(mongo_db):
    ended = {**plan_trial.new_trial(NOW - timedelta(days=20), 14)}
    await harness.tenant(mongo_db, "t-end", plan="Free", trial=ended)
    code, held = await harness.register(mongo_db, "m1", hardware=harness.hw("S1"))
    assert code == 202 and held["pendingReason"] == "trial_ended"
    agent = await mongo_db.agents.find_one({"hostname": "m1"})
    with patch("audit_service.get_audit_service", return_value=MagicMock(log_action_async=AsyncMock())):
        out = await pending_agents.approve(mongo_db, agent["id"], "root@example.com")
    assert out["status"] == "Offline"
    stored = await _stored(mongo_db, "t-end")
    assert stored["trial"]["endsAt"] == ended["endsAt"] and plan_trial.ended(stored)


async def test_an_ended_trial_changes_no_agent_status_and_no_enabled_feature(mongo_db):
    features = ["view:dashboard", "screen:dashboard", "screen:agents"]
    await harness.tenant(mongo_db, "t-run", plan="Free", trial=_running(48), enabledFeatures=features)
    code, first = await harness.register(mongo_db, "m1", hardware=harness.hw("S1"))
    assert code == 200
    before = await mongo_db.agents.find_one({"hostname": "m1"}, {"_id": 0, "status": 1})
    await mongo_db.tenants.update_one({"id": "t-run"}, {"$set": {"trial.endsAt": (NOW - timedelta(minutes=1)).isoformat()}})
    assert await plan_trial.send_trial_reminders(mongo_db, NOW) == 0
    code, _ = await harness.register(mongo_db, "m2", hardware=harness.hw("S2"))
    assert code == 202
    assert await mongo_db.agents.find_one({"hostname": "m1"}, {"_id": 0, "status": 1}) == before
    assert (await _stored(mongo_db, "t-run"))["enabledFeatures"] == features


async def test_a_tenant_back_on_free_after_a_paid_plan_has_no_trial_left(mongo_db):
    await harness.tenant(mongo_db, "t-back", plan="Pro", trial=plan_trial.consumed_trial(NOW - timedelta(days=40)))
    with patch("audit_ledger.event", new=AsyncMock()):
        out = await plan_service.change_plan(mongo_db, "t-back", "Free", actor=SUPER, via="super_admin")
    assert out["changed"] is True and out["licence"]["trial"]["ended"] is True
    code, held = await harness.register(mongo_db, "m1", hardware=harness.hw("S1"))
    assert code == 202 and held["pendingReason"] == "trial_ended"
