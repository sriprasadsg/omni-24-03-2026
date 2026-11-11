"""Migration 034: the plan-licensing go-live (plans, plan seats, trials, allowed networks, hardware indexes).

Value: protects=the one-way D-18 seat overwrite records what it replaces, leaves the platform, partner
customers, partner organizations and every tenant's screens alone, never overwrites a plan an administrator
edited, and a second run changes nothing; fails_when=a seat number is replaced without
license.maxAgentsBeforePlans, a partner customer or the platform gets a plan number, enabledFeatures moves,
a trial or network list is overwritten, or up() twice writes anything; no_claim=the live database (the user's
restart applies the migration, 88-16) and the HTTP layer.
"""
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import licensing
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

migration = importlib.import_module("migrations.034_plan_licensing")

pytestmark = pytest.mark.asyncio

ABC_IP = "103.174.161.233"
FEATURES = {"exafluence": ["overview", "assets"], "abc": ["overview"], "shield": ["overview"],
            "pro12": ["overview", "agents"], "custom40": ["overview"], "enterprise-lower": ["overview"],
            "notier": ["overview"], "cust-1": ["overview"], "platform-admin": ["all"]}


def _lic(seats, **extra):
    return {"maxAgents": seats, "seatsUsed": 0, "inactiveReclaimDays": 30, **extra}


def _tenant(tid, plan="Free", seats=5, **extra):
    doc = {"id": tid, "name": tid.title(), "license": _lic(seats), "enabledFeatures": FEATURES[tid], **extra}
    if plan is not None:
        doc["subscriptionTier"] = plan
    return doc


def _agent(n, tenant, hostname, status="Online", **extra):
    return {"id": f"agent-{n}", "tenantId": tenant, "hostname": hostname, "status": status, **extra}


async def _seed(db):
    """The four live shapes of 2026-11-10 plus the extra cases the migration has to tell apart."""
    await db.tenants.insert_many([
        _tenant("platform-admin", "Enterprise"),
        _tenant("exafluence", "Pro", **{"license": _lic(5, expiresAt="2026-10-30T23:59:59+00:00")}),
        _tenant("abc"), _tenant("shield"),
        _tenant("pro12", "Pro", 12),
        _tenant("custom40", "Custom", 40),
        _tenant("enterprise-lower", "enterprise",
                allowedNetworks=[{"cidr": "9.9.9.0/24", "source": "learned"}]),
        _tenant("notier", None, trial={"startedAt": "2026-01-01T00:00:00+00:00",
                                       "endsAt": "2026-01-15T00:00:00+00:00", "consumed": False}),
        _tenant("cust-1", None, 30, partnerId="partner-1"),
        {"id": "partner-1", "name": "Partner One", "type": "partner", "license": _lic(0)},
    ])
    await db.agents.insert_many([
        _agent(1, "platform-admin", "pa-host", sourceIp="10.0.0.4"),
        _agent(2, "abc", "EILT0197", publicIp=ABC_IP, sourceIp=ABC_IP),
        _agent(3, "exafluence", "exa-1", publicIp="5.6.7.8"),
        _agent(4, "pro12", "p-1", publicIp="5.6.7.8", sourceIp="5.6.7.8"),
        _agent(5, "pro12", "p-2", publicIp="5.6.7.9"),
        _agent(6, "custom40", "c-private", publicIp="10.1.2.3"),
        _agent(7, "custom40", "c-bad", publicIp="bad"),
        _agent(8, "custom40", "c-none"),
        _agent(9, "custom40", "c-pending", status="Pending", publicIp="9.9.9.9"),
        _agent(10, "custom40", "c-rejected", status="Rejected", sourceIp="9.9.9.10"),
        _agent(11, "cust-1", "cust-host", publicIp="8.8.4.4"),
        _agent(12, "enterprise-lower", "e-host", publicIp="7.7.7.7"),
        _agent(13, "partner-1", "partner-host", publicIp="6.6.6.6"),
    ])


async def _run(db, ledger=None):
    ledger = ledger or AsyncMock()
    with patch("audit_ledger.event", new=ledger):
        await migration.up(db)
    return ledger


async def _t(db, tid):
    return await db.tenants.find_one({"id": tid}, {"_id": 0})


async def _snapshot(db):
    out = {}
    for name in sorted(await db.list_collection_names()):
        out[name] = await db[name].find({}).sort("_id", 1).to_list(None)
    return out


async def test_plans_hold_the_four_d03_documents_and_never_overwrite_an_edit(mongo_db):
    await mongo_db.plans.insert_one({"key": "Pro", "seats": 60, "trialDays": None, "screens": ["overview"]})
    await _run(mongo_db)
    plans = {p["key"]: p async for p in mongo_db.plans.find({}, {"_id": 0})}
    assert sorted(plans) == ["Custom", "Enterprise", "Free", "Pro"]
    assert (plans["Free"]["seats"], plans["Free"]["trialDays"]) == (5, 14)
    assert (plans["Enterprise"]["seats"], plans["Enterprise"]["trialDays"]) == (500, None)
    assert plans["Custom"]["seats"] is None and plans["Custom"]["screens"] == "all"
    assert plans["Pro"]["seats"] == 60 and plans["Pro"]["screens"] == ["overview"]
    import screen_ceiling
    assert plans["Free"]["screens"] == screen_ceiling.seed_screens("Free")
    assert plans["Enterprise"]["screens"] == screen_ceiling.seed_screens("Enterprise")
    assert plans["Free"]["updatedBy"] == "migration 034"


async def test_direct_tenants_take_their_plan_seats_and_record_the_old_number(mongo_db):
    await _seed(mongo_db)
    ledger = await _run(mongo_db)
    exa = await _t(mongo_db, "exafluence")
    assert (exa["license"]["maxAgents"], exa["maxAgents"], exa["license"]["maxAgentsBeforePlans"]) == (50, 50, 5)
    assert "seatOverride" not in exa["license"]
    assert exa["license"]["expiresAt"] == "2026-10-30T23:59:59+00:00"
    for tid in ("abc", "shield"):
        t = await _t(mongo_db, tid)
        assert (t["license"]["maxAgents"], t["license"]["maxAgentsBeforePlans"]) == (5, 5)
        assert "seatOverride" not in t["license"]
    lower = await _t(mongo_db, "enterprise-lower")
    assert lower["subscriptionTier"] == "Enterprise" and lower["license"]["maxAgents"] == 500
    notier = await _t(mongo_db, "notier")
    assert notier["subscriptionTier"] == "Free" and notier["license"]["maxAgentsBeforePlans"] == 5
    adopted = {c.args[1]: c.kwargs for c in ledger.await_args_list if c.args[0] == "plan.seats_adopted"}
    assert set(adopted) == {"exafluence", "abc", "shield", "pro12", "custom40", "enterprise-lower", "notier"}
    assert (adopted["exafluence"]["before"], adopted["exafluence"]["after"], adopted["exafluence"]["plan"]) == (5, 50, "Pro")
    assert adopted["exafluence"]["actor"] == {"email": "migration 034"}
    assert ledger.await_count == len(adopted)


async def test_platform_partner_customer_and_partner_org_keep_their_seats(mongo_db):
    await _seed(mongo_db)
    ledger = await _run(mongo_db)
    for tid, seats in (("platform-admin", 5), ("cust-1", 30), ("partner-1", 0)):
        t = await _t(mongo_db, tid)
        assert t["license"]["maxAgents"] == seats and "maxAgentsBeforePlans" not in t["license"], tid
        assert "seatOverride" not in t["license"]
        assert tid not in {c.args[1] for c in ledger.await_args_list}
    assert "trial" not in await _t(mongo_db, "platform-admin")
    assert "allowedNetworks" not in await _t(mongo_db, "platform-admin")
    org = await _t(mongo_db, "partner-1")
    assert "trial" not in org and "allowedNetworks" not in org and "subscriptionTier" not in org


async def test_a_hand_set_number_or_a_custom_tenant_keeps_its_number_as_an_override(mongo_db):
    await _seed(mongo_db)
    await _run(mongo_db)
    pro = await _t(mongo_db, "pro12")
    assert (pro["license"]["maxAgents"], pro["license"]["seatOverride"], pro["license"]["maxAgentsBeforePlans"]) == (12, 12, 12)
    custom = await _t(mongo_db, "custom40")
    assert (custom["license"]["maxAgents"], custom["license"]["seatOverride"]) == (40, 40)


async def test_trials_start_at_go_live_on_free_and_are_consumed_elsewhere(mongo_db):
    await _seed(mongo_db)
    before = datetime.now(timezone.utc)
    await _run(mongo_db)
    abc = (await _t(mongo_db, "abc"))["trial"]
    started, ends = datetime.fromisoformat(abc["startedAt"]), datetime.fromisoformat(abc["endsAt"])
    assert abs((started - before).total_seconds()) < 5 and ends == started + timedelta(days=14)
    assert abc["consumed"] is False
    exa = (await _t(mongo_db, "exafluence"))["trial"]
    assert exa["consumed"] is True and exa["startedAt"] is None
    assert (await _t(mongo_db, "shield"))["trial"]["consumed"] is False
    assert (await _t(mongo_db, "cust-1"))["trial"]["consumed"] is False
    assert (await _t(mongo_db, "custom40"))["trial"]["consumed"] is True
    assert (await _t(mongo_db, "notier"))["trial"]["startedAt"] == "2026-01-01T00:00:00+00:00"


async def test_allowed_networks_hold_the_public_addresses_of_admitted_agents_only(mongo_db):
    await _seed(mongo_db)
    await _run(mongo_db)
    abc = (await _t(mongo_db, "abc"))["allowedNetworks"]
    assert [(e["cidr"], e["source"], e["hostname"]) for e in abc] == [(f"{ABC_IP}/32", "migrated", "EILT0197")]
    pro = (await _t(mongo_db, "pro12"))["allowedNetworks"]
    assert sorted(e["cidr"] for e in pro) == ["5.6.7.8/32", "5.6.7.9/32"]
    assert [e["cidr"] for e in (await _t(mongo_db, "cust-1"))["allowedNetworks"]] == ["8.8.4.4/32"]
    assert [e["cidr"] for e in (await _t(mongo_db, "enterprise-lower"))["allowedNetworks"]] == ["9.9.9.0/24"]
    for tid in ("custom40", "shield"):
        assert "allowedNetworks" not in await _t(mongo_db, tid), tid
    assert [e["cidr"] for e in (await _t(mongo_db, "exafluence"))["allowedNetworks"]] == ["5.6.7.8/32"]


async def test_no_tenant_screen_list_moves(mongo_db):
    await _seed(mongo_db)
    await _run(mongo_db)
    for tid, expected in FEATURES.items():
        assert (await _t(mongo_db, tid))["enabledFeatures"] == expected, tid


async def test_hardware_indexes_exist_and_are_sparse(mongo_db):
    await _run(mongo_db)
    info = await mongo_db.agents.index_information()
    for name in ("agents_hw_serial_sparse", "agents_hw_uuid_sparse"):
        assert info[name].get("sparse") is True
    assert "cross_tenant_reports_key" in await mongo_db.cross_tenant_reports.index_information()


async def test_a_second_run_changes_no_document_and_records_no_audit_entry(mongo_db):
    await _seed(mongo_db)
    await _run(mongo_db)
    first = await _snapshot(mongo_db)
    ledger = await _run(mongo_db)
    assert await _snapshot(mongo_db) == first
    assert ledger.await_count == 0


async def test_an_audit_failure_does_not_stop_the_migration(mongo_db):
    await _seed(mongo_db)
    await _run(mongo_db, AsyncMock(side_effect=RuntimeError("ledger down")))
    assert (await _t(mongo_db, "exafluence"))["license"]["maxAgents"] == 50


async def test_adopt_plan_seats_records_the_previous_number_once(mongo_db):
    await mongo_db.tenants.insert_many([_tenant("shield"), _tenant("cust-1", None, 30, partnerId="partner-1")])
    assert await licensing.adopt_plan_seats(mongo_db, "shield", seats=50, override=None, previous=5) is True
    t = await _t(mongo_db, "shield")
    assert (t["license"]["maxAgents"], t["maxAgents"], t["license"]["maxAgentsBeforePlans"]) == (50, 50, 5)
    assert await licensing.adopt_plan_seats(mongo_db, "shield", seats=500, override=None, previous=50) is False
    assert (await _t(mongo_db, "shield"))["license"]["maxAgents"] == 50
    assert await licensing.adopt_plan_seats(mongo_db, "cust-1", seats=50, override=None, previous=30) is False
    assert (await _t(mongo_db, "cust-1"))["license"]["maxAgents"] == 30
