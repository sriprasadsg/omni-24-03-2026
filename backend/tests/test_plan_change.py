"""Phase 88 plan 04: one audited function changes a plan; the Super Admin's screen ticks stay inside it (real MongoDB).

Value: protects=every plan change is one compare-and-set that keeps the seat and trial rules, is refused for
the platform organization and for a partner's non-customers, is audited and announced exactly once, and the
Super Admin's PATCH and create answer 422 for a screen outside the plan; fails_when=two concurrent changes both
win, a change to the same plan writes an audit entry, an override or partner allotment is overwritten, a trial
record is reset, or a screen outside the plan is stored; no_claim=the HTTP layer (route functions are called
directly with a TokenData) and the payment route (covered in the second half of this module); audit writers are
mocked.
"""
import asyncio
import json
import os
import sys
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


@pytest.fixture
def wired(mongo_db):
    """The tenant routes run against the private database; the ledger, auditing and sessions are mocked."""
    audit = MagicMock(log_action_async=AsyncMock())
    ledger = AsyncMock()
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)), \
            patch("audit_service.get_audit_service", return_value=audit), \
            patch("audit_ledger.event", new=ledger), \
            patch.object(te, "get_database", return_value=mongo_db), \
            patch.object(te, "revoke_user_sessions", new=AsyncMock()):
        mongo_db.ledger = ledger
        yield mongo_db


async def _tenant(db, tid="t1", plan="Free", seats=5, trial="running", partner_id=None, override=None, features=None):
    doc = {"id": tid, "name": f"Org {tid}", "maxAgents": seats,
           "license": {"maxAgents": seats, "seatsUsed": 0, "inactiveReclaimDays": 30},
           "enabledFeatures": features if features is not None else ["view:dashboard", "view:profile", "screen:dashboard"]}
    if plan is not None:
        doc["subscriptionTier"] = plan
    if trial == "running":
        doc["trial"] = plan_trial.new_trial(plan_trial_now(), 14)
    if partner_id:
        doc["partnerId"] = partner_id
    if override is not None:
        doc["license"]["seatOverride"] = override
    await db.tenants.insert_one(doc)
    return tid


def plan_trial_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


async def _get(db, tid="t1"):
    return await db.tenants.find_one({"id": tid}, {"_id": 0})


def _events(db, name):
    return [c for c in db.ledger.await_args_list if c.args and c.args[0] == name]


def _body(resp):
    return json.loads(resp.body)


# -- change_plan: the seat rule, the trial rule, the audit and the notice --------------------------

async def test_a_direct_tenant_gets_the_new_plans_seats_an_audit_entry_and_a_notice(wired):
    await _tenant(wired)
    out = await plan_service.change_plan(wired, "t1", "pro", actor=SUPER, via="super_admin")
    stored = await _get(wired)
    assert out["changed"] is True and out["from"] == "Free" and out["to"] == "Pro"
    assert stored["subscriptionTier"] == "Pro" and stored["license"]["maxAgents"] == 50 and stored["maxAgents"] == 50
    assert stored["trial"]["consumed"] is False  # an existing trial record is never reset
    changed = _events(wired, "plan.changed")
    assert len(changed) == 1
    assert changed[0].kwargs["before"] == "Free" and changed[0].kwargs["after"] == "Pro"
    assert changed[0].kwargs["via"] == "super_admin" and changed[0].kwargs["actor"]["email"] == SUPER.username
    seats = _events(wired, "seats.changed")
    assert len(seats) == 1 and seats[0].kwargs["before"] == 5 and seats[0].kwargs["after"] == 50
    notices = await wired.notifications.find({"tenantId": "t1", "metadata.event": "plan.changed"}).to_list(10)
    assert len(notices) == 1 and notices[0]["metadata"]["audience"] == "tenant_admins"


async def test_a_seat_override_is_left_alone(wired):
    await _tenant(wired, seats=12, override=12)
    await plan_service.change_plan(wired, "t1", "Pro", actor=SUPER, via="super_admin")
    stored = await _get(wired)
    assert stored["subscriptionTier"] == "Pro" and stored["license"]["maxAgents"] == 12
    assert stored["license"]["seatOverride"] == 12 and _events(wired, "seats.changed") == []


async def test_a_partner_customers_allotment_is_left_alone(wired):
    await _tenant(wired, seats=30, partner_id="p1")
    await plan_service.change_plan(wired, "t1", "Enterprise", actor=SUPER, via="super_admin")
    stored = await _get(wired)
    assert stored["subscriptionTier"] == "Enterprise" and stored["license"]["maxAgents"] == 30


async def test_a_move_to_custom_keeps_the_current_number_as_the_override(wired):
    await _tenant(wired, plan="Pro", seats=50)
    await plan_service.change_plan(wired, "t1", "custom", actor=SUPER, via="super_admin")
    stored = await _get(wired)
    assert stored["subscriptionTier"] == "Custom"
    assert stored["license"]["seatOverride"] == 50 and stored["license"]["maxAgents"] == 50


async def test_a_change_on_a_tenant_without_a_trial_record_writes_a_consumed_trial(wired):
    await _tenant(wired, plan="Pro", seats=50, trial=None)
    await plan_service.change_plan(wired, "t1", "Free", actor=SUPER, via="super_admin")
    stored = await _get(wired)
    assert stored["trial"]["consumed"] is True and plan_trial.ended(stored) is True


async def test_an_existing_trial_record_is_never_reset(wired):
    await _tenant(wired, plan="Pro", seats=50, trial=None)
    await wired.tenants.update_one({"id": "t1"}, {"$set": {"trial": plan_trial.new_trial(plan_trial_now(), 3)}})
    before = (await _get(wired))["trial"]
    await plan_service.change_plan(wired, "t1", "Free", actor=SUPER, via="super_admin")
    assert (await _get(wired))["trial"] == before


async def test_the_platform_organization_is_refused(wired):
    await _tenant(wired, tid="platform-admin", plan="Enterprise", seats=0)
    with pytest.raises(plan_service.PlanError) as err:
        await plan_service.change_plan(wired, "platform-admin", "Pro", actor=SUPER, via="super_admin")
    assert err.value.status == 409 and err.value.code == "platform_exempt"
    assert (await _get(wired, "platform-admin"))["subscriptionTier"] == "Enterprise"


@pytest.mark.parametrize("name", ["Gold", "", "   "])
async def test_an_unknown_or_empty_plan_is_refused_and_stores_nothing(wired, name):
    await _tenant(wired)
    with pytest.raises(plan_service.PlanError) as err:
        await plan_service.change_plan(wired, "t1", name, actor=SUPER, via="super_admin")
    assert err.value.status == 422 and err.value.code == "unknown_plan"
    assert (await _get(wired))["subscriptionTier"] == "Free" and _events(wired, "plan.changed") == []


async def test_a_missing_tenant_is_a_404(wired):
    with pytest.raises(plan_service.PlanError) as err:
        await plan_service.change_plan(wired, "nope", "Pro", actor=SUPER, via="super_admin")
    assert err.value.status == 404


async def test_the_same_plan_in_any_case_writes_nothing(wired):
    await _tenant(wired)
    before = await _get(wired)
    out = await plan_service.change_plan(wired, "t1", "FREE", actor=SUPER, via="super_admin")
    assert out["changed"] is False
    assert await _get(wired) == before
    assert wired.ledger.await_count == 0
    assert await wired.notifications.count_documents({"tenantId": "t1"}) == 0


async def test_a_tenant_with_no_stored_plan_reads_as_free_and_can_move(wired):
    await _tenant(wired, plan=None)
    assert (await plan_service.change_plan(wired, "t1", "free", actor=SUPER, via="super_admin"))["changed"] is False
    out = await plan_service.change_plan(wired, "t1", "Pro", actor=SUPER, via="super_admin")
    assert out["changed"] is True and out["from"] == "Free" and (await _get(wired))["subscriptionTier"] == "Pro"


class _MeetingDb:
    """The database with the first two tenant reads held until both have answered, so both callers have read
    the same stored plan before either writes (real scheduling may or may not interleave that way)."""

    def __init__(self, db):
        self._real = db
        self._barrier = asyncio.Barrier(2)
        self._reads = 0
        outer = self

        class _Tenants:
            def __getattr__(self, name):
                return getattr(outer._real.tenants, name)

            async def find_one(self, *args, **kwargs):
                found = await outer._real.tenants.find_one(*args, **kwargs)
                outer._reads += 1
                if outer._reads <= 2:
                    await outer._barrier.wait()
                return found

        self.tenants = _Tenants()

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __getitem__(self, name):
        return self.tenants if name == "tenants" else self._real[name]


async def test_two_concurrent_changes_from_the_same_plan_end_with_one_winner(wired):
    await _tenant(wired)
    racing = _MeetingDb(wired)
    results = await asyncio.gather(
        plan_service.change_plan(racing, "t1", "Pro", actor=SUPER, via="super_admin"),
        plan_service.change_plan(racing, "t1", "Enterprise", actor=SUPER, via="super_admin"),
        return_exceptions=True)
    losers = [r for r in results if isinstance(r, plan_service.PlanError)]
    winners = [r for r in results if isinstance(r, dict)]
    assert len(winners) == 1 and len(losers) == 1, results
    assert losers[0].status == 409 and losers[0].code == "plan_changed"
    assert len(_events(wired, "plan.changed")) == 1
    assert (await _get(wired))["subscriptionTier"] == winners[0]["to"]


# -- change_plan for a partner ----------------------------------------------------------------------

def _partner(ceiling="unset", pid="p1"):
    doc = {"id": pid, "type": "partner", "partner": {}}
    if ceiling != "unset":
        doc["partner"]["planCeiling"] = ceiling
    return doc


async def test_a_partner_cannot_change_another_partners_customer(wired):
    await _tenant(wired, partner_id="p2")
    with pytest.raises(plan_service.PlanError) as err:
        await plan_service.change_plan(wired, "t1", "Free", actor=SUPER, via="partner", partner_doc=_partner(["Free", "Pro"]))
    assert err.value.status == 404
    await _tenant(wired, tid="t2")  # a direct tenant is nobody's customer
    with pytest.raises(plan_service.PlanError) as err:
        await plan_service.change_plan(wired, "t2", "Free", actor=SUPER, via="partner", partner_doc=_partner(["Free", "Pro"]))
    assert err.value.status == 404


async def test_a_partner_cannot_move_a_customer_outside_its_plan_ceiling(wired):
    await _tenant(wired, partner_id="p1", seats=30)
    with pytest.raises(plan_service.PlanError) as err:
        await plan_service.change_plan(wired, "t1", "Enterprise", actor=SUPER, via="partner", partner_doc=_partner(["Free", "Pro"]))
    assert err.value.status == 422 and err.value.code == "plan_outside_ceiling"
    assert (await _get(wired))["subscriptionTier"] == "Free"


async def test_an_absent_plan_ceiling_allows_free_only(wired):
    await _tenant(wired, plan="Pro", partner_id="p1", seats=30)
    with pytest.raises(plan_service.PlanError) as err:
        await plan_service.change_plan(wired, "t1", "Pro", actor=SUPER, via="partner", partner_doc=_partner())
    assert err.value.status == 422 and err.value.code == "plan_outside_ceiling"
    out = await plan_service.change_plan(wired, "t1", "Free", actor=SUPER, via="partner", partner_doc=_partner())
    assert out["changed"] is True


async def test_a_partner_change_inside_the_ceiling_is_audited_under_the_partner(wired):
    await _tenant(wired, partner_id="p1", seats=30)
    import partner_store
    with patch.object(partner_store, "audit", new=AsyncMock()) as partner_audit:
        out = await plan_service.change_plan(wired, "t1", "Pro", actor=SUPER, via="partner",
                                             partner_doc=_partner(["Free", "Pro"]))
    assert out["changed"] is True and (await _get(wired))["license"]["maxAgents"] == 30
    assert partner_audit.await_count == 1
    args, kwargs = partner_audit.await_args
    assert args[0] == "partner.customer_plan_changed" and kwargs["partner_id"] == "p1"
    assert kwargs["customerId"] == "t1" and kwargs["before"] == "Free" and kwargs["after"] == "Pro"


# -- the Super Admin's PATCH and create ------------------------------------------------------------

async def test_patch_changes_the_plan_and_checks_the_screens_against_the_new_plan(wired):
    await _tenant(wired)
    out = await te.update_tenant("t1", te.TenantUpdate(subscriptionTier="Pro", enabledFeatures=["view:reporting"]),
                                 current_user=SUPER)
    assert out["subscriptionTier"] == "Pro" and "view:reporting" in out["enabledFeatures"]
    assert len(_events(wired, "plan.changed")) == 1


async def test_patch_without_a_plan_changes_no_plan(wired):
    await _tenant(wired)
    await te.update_tenant("t1", te.TenantUpdate(enabledFeatures=["view:agents"]), current_user=SUPER)
    stored = await _get(wired)
    assert stored["subscriptionTier"] == "Free" and "view:agents" in stored["enabledFeatures"]
    assert _events(wired, "plan.changed") == []


async def test_patch_refuses_a_screen_outside_the_plan_and_leaves_the_list_unchanged(wired):
    await _tenant(wired)
    before = (await _get(wired))["enabledFeatures"]
    resp = await te.update_tenant("t1", te.TenantUpdate(enabledFeatures=["manage:settings"]), current_user=SUPER)
    assert resp.status_code == 422 and _body(resp)["code"] == "screen_outside_plan"
    assert (await _get(wired))["enabledFeatures"] == before


async def test_a_refused_screen_leaves_the_plan_unchanged_too(wired):
    await _tenant(wired)
    resp = await te.update_tenant("t1", te.TenantUpdate(subscriptionTier="Pro", enabledFeatures=["manage:settings"]),
                                  current_user=SUPER)
    assert resp.status_code == 422
    assert (await _get(wired))["subscriptionTier"] == "Free" and _events(wired, "plan.changed") == []


async def test_a_screen_already_on_outside_the_plan_may_be_resubmitted(wired):
    await _tenant(wired, features=["view:dashboard", "view:profile", "screen:dashboard", "manage:settings"])
    out = await te.update_tenant(
        "t1", te.TenantUpdate(enabledFeatures=["view:dashboard", "view:profile", "screen:dashboard", "manage:settings"]),
        current_user=SUPER)
    assert "manage:settings" in out["enabledFeatures"]


async def test_patch_with_an_unknown_plan_answers_422_and_stores_nothing(wired):
    await _tenant(wired)
    for name in ("Gold", ""):
        with pytest.raises(HTTPException) as err:
            await te.update_tenant("t1", te.TenantUpdate(subscriptionTier=name), current_user=SUPER)
        assert err.value.status_code == 422
    assert (await _get(wired))["subscriptionTier"] == "Free"


async def test_patch_of_the_platform_organizations_plan_is_a_409(wired):
    await _tenant(wired, tid="platform-admin", plan="Enterprise", seats=0)
    with pytest.raises(HTTPException) as err:
        await te.update_tenant("platform-admin", te.TenantUpdate(subscriptionTier="Free"), current_user=SUPER)
    assert err.value.status_code == 409


async def test_the_platform_organization_and_custom_allow_every_switch(wired):
    await _tenant(wired, tid="platform-admin", plan="Enterprise", seats=0)
    out = await te.update_tenant("platform-admin", te.TenantUpdate(enabledFeatures=["manage:settings"]), current_user=SUPER)
    assert "manage:settings" in out["enabledFeatures"]
    await _tenant(wired, tid="c1", plan="Custom", seats=9)
    out = await te.update_tenant("c1", te.TenantUpdate(enabledFeatures=["manage:settings"]), current_user=SUPER)
    assert "manage:settings" in out["enabledFeatures"]


async def test_the_super_admin_is_not_limited_by_a_partners_ceiling(wired):
    await wired.tenants.insert_one({"id": "p1", "name": "Partner", "type": "partner", "license": {"maxAgents": 0},
                                    "partner": {"poolSize": 100, "allocated": 30, "screenCeiling": ["view:agents"]}})
    await _tenant(wired, plan="Enterprise", seats=30, partner_id="p1")
    out = await te.update_tenant("t1", te.TenantUpdate(enabledFeatures=["view:reporting"]), current_user=SUPER)
    assert "view:reporting" in out["enabledFeatures"]


async def test_billable_services_are_not_screens_and_pass_through(wired):
    await _tenant(wired)
    out = await te.update_tenant("t1", te.TenantUpdate(enabledFeatures=["service:backup", "view:agents"]), current_user=SUPER)
    assert "service:backup" in out["enabledFeatures"] and "view:agents" in out["enabledFeatures"]


async def test_a_tenant_admin_still_cannot_patch_plan_or_screens(wired):
    await _tenant(wired)
    admin = TokenData(username="a@x.io", role="Tenant Admin", tenant_id="t1", mfa_verified=True)
    with pytest.raises(HTTPException) as err:
        await te.update_tenant("t1", te.TenantUpdate(subscriptionTier="Enterprise"), current_user=admin)
    assert err.value.status_code == 403
    assert (await _get(wired))["subscriptionTier"] == "Free"


async def test_create_with_a_screen_outside_the_plan_answers_422_and_stores_nothing(wired):
    resp = await te.create_tenant(te.TenantCreate(name="X", enabledFeatures=["manage:settings"]), current_user=SUPER)
    assert resp.status_code == 422 and _body(resp)["code"] == "screen_outside_plan"
    assert await wired.tenants.count_documents({"name": "X"}) == 0


async def test_create_with_screens_inside_the_plan_stores_them(wired):
    out = await te.create_tenant(te.TenantCreate(name="Y", subscriptionTier="Pro", enabledFeatures=["view:reporting"]),
                                 current_user=SUPER)
    assert "view:reporting" in out["enabledFeatures"] and out["subscriptionTier"] == "Pro"
