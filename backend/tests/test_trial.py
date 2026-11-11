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

import plan_service
import plan_trial
import tenant_endpoints as te
from auth_types import TokenData
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
