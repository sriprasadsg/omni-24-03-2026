"""Phase 88 plan 03: the plan is a screen ceiling (D-27..D-30, D-46).

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>.
The seed half is pure; the ceiling half uses real MongoDB (private mongod via MONGO_TEST_URL).
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tenant_features as tf

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "backend" / "scripts" / "generate_plan_screen_seed.py"
SEED_FILE = ROOT / "shared" / "plan-screen-seed.json"


def _generator():
    spec = importlib.util.spec_from_file_location("generate_plan_screen_seed", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- D-29 / D-46: the seed ------------------------------------------------------------------------

def test_seed_has_the_reviewed_counts_and_is_nested():
    """protects=D-29 counts 19/88/208 and Free within Pro within Enterprise = every switch;
    fails_when=a rule drifts and a screen lands in the wrong plan."""
    seed = _generator().build_seed()
    assert [len(seed[k]) for k in ("Free", "Pro", "Enterprise")] == [19, 88, 208]
    assert all(seed[k] == sorted(seed[k]) for k in seed)
    assert set(seed["Free"]) <= set(seed["Pro"]) <= set(seed["Enterprise"])
    assert seed["Enterprise"] == sorted(tf.SWITCHABLE)


def test_seed_places_known_screens_in_their_plans():
    """protects=D-29 sample placements; fails_when=Overview/Agents leave Free, Reporting enters Free,
    or Settings management leaves Enterprise-only."""
    seed = _generator().build_seed()
    for key in ("screen:dashboard", "view:agents", "screen:agents"):
        assert key in seed["Free"]
    assert "view:reporting" in seed["Pro"] and "view:reporting" not in seed["Free"]
    assert "manage:settings" in seed["Enterprise"] and "manage:settings" not in seed["Pro"]


def test_committed_seed_file_is_what_the_script_writes():
    """protects=T-88-08 (a hand edit is visible); fails_when=the committed JSON differs from the
    generator's output byte for byte."""
    seed = _generator().build_seed()
    expected = json.dumps({"version": 1, "rule": "D-29", "plans": seed}, indent=2) + "\n"
    assert SEED_FILE.read_text(encoding="utf-8") == expected


# --- D-27 / D-28 / D-30: the one ceiling function --------------------------------------------------

import pytest  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

import partner_endpoints as pe  # noqa: E402
try:  # RED phase only: the module does not exist yet
    import screen_ceiling as sc  # noqa: E402
except ImportError:
    sc = None
from auth_types import TokenData  # noqa: E402
from tests._mongo_test_db import mongo_db  # noqa: E402,F401  (fixture)

START = list(tf.START_FEATURES)
PLAN_MSG = "{label} is not part of this {plan} plan."
PARTNER_MSG = "{label} is not one of the screens you can sell."


def _limits(plan_set, partner_set):
    return [(set(plan_set) | set(START), PLAN_MSG, "screen_outside_plan"),
            (set(partner_set) | set(START), PARTNER_MSG, "screen_outside_ceiling")]


def _refusal(limits, submitted, current=(), **kw):
    with pytest.raises(sc.CeilingError) as exc:
        sc.final_screens(limits, submitted, list(current), **kw)
    return exc.value


def test_a_screen_inside_both_limits_is_accepted():
    """protects=D-30 adjacency (inside both); fails_when=an accepted screen is refused or START is lost."""
    both = _limits({"view:agents"}, {"view:agents"})
    assert sc.final_screens(both, ["view:agents"], []) == ["view:agents", *START]


def test_a_screen_inside_only_one_limit_is_refused_with_that_limits_code():
    """protects=D-30 adjacency; fails_when=a screen in only the partner ceiling or only the plan is accepted,
    or the refusal names the wrong limit."""
    err = _refusal(_limits({"view:agents"}, {"view:agents", "view:reporting"}), ["view:reporting"], plan="Free")
    assert err.code == "screen_outside_plan" and tf.SWITCH_LABELS["view:reporting"] in str(err)
    assert "Free" in str(err)
    err = _refusal(_limits({"view:agents", "view:reporting"}, {"view:agents"}), ["view:reporting"], plan="Pro")
    assert err.code == "screen_outside_ceiling" and tf.SWITCH_LABELS["view:reporting"] in str(err)


def test_all_and_unknown_strings_are_refused_as_invalid():
    """protects=T-88-07; fails_when='all' or an invented string passes even for every-switch limits."""
    everything = _limits(tf.SWITCHABLE, tf.SWITCHABLE)
    for bad in ("all", "made:up", "", 7):
        assert _refusal(everything, ["view:agents", bad]).code == "invalid_screen", bad


def test_a_child_without_its_parent_is_refused_naming_the_parent():
    """protects=the switch tree; fails_when=a child is stored without its parent."""
    err = _refusal(_limits(tf.SWITCHABLE, tf.SWITCHABLE), ["screen:agents"])
    assert err.code == "missing_parent" and err.numbers["parent"] == "view:agents"


def test_screens_already_on_outside_the_plan_are_kept_but_not_added():
    """protects=D-28 (PROH-88-05); fails_when=a kept screen is refused on re-submit, cannot be unticked,
    or a new outside screen can be added."""
    free = _limits({"view:agents"}, tf.SWITCHABLE)
    current = ["view:reporting", "view:agents"]
    assert sc.final_screens(free, ["view:reporting", "view:agents"], current) == \
        ["view:reporting", "view:agents", *START]
    assert sc.final_screens(free, ["view:agents"], current) == ["view:agents", *START]
    assert _refusal(free, ["view:reporting", "screen:siem"], current).code == "screen_outside_plan"


def test_sticky_screens_stay_on_even_when_not_submitted():
    """protects=D-28 partner path; fails_when=an empty submit drops a screen only the platform could add."""
    limits = _limits(tf.SWITCHABLE, {"view:agents"})
    assert sc.final_screens(limits, [], ["manage:settings"], sticky=["manage:settings"]) == \
        ["manage:settings", *START]


def test_stored_order_is_submitted_then_sticky_then_missing_start():
    """protects=ordering edge; fails_when=duplicates survive or the groups come in another order."""
    limits = _limits(tf.SWITCHABLE, tf.SWITCHABLE)
    out = sc.final_screens(limits, ["view:assets", "view:agents", "view:assets"], ["manage:settings", "view:profile"],
                           sticky=["manage:settings", "view:profile"])
    assert out == ["view:assets", "view:agents", "manage:settings", "view:profile", "view:dashboard",
                   "screen:dashboard"]


def test_passthrough_prefixes_are_stored_without_a_ceiling_check():
    """protects=88-04 hook; fails_when=a service: entry is refused when the caller names its prefix, or
    accepted when it does not."""
    limits = _limits({"view:agents"}, {"view:agents"})
    assert "service:vpn" in sc.final_screens(limits, ["view:agents", "service:vpn"], [], passthrough_prefixes=("service:",))
    assert _refusal(limits, ["service:vpn"]).code == "invalid_screen"


# --- D-14: plan_allowed reads the stored plan at once -----------------------------------------------

async def test_plan_allowed_falls_back_to_the_seed_then_follows_the_stored_document(mongo_db):  # noqa: F811
    """protects=D-14 (no cache); fails_when=a stored edit is not seen on the next call, or a missing document
    or screens field returns nothing."""
    seed = sc.seed_screens("Free")
    assert await sc.plan_allowed(mongo_db, "Free") == set(seed) | set(START)
    await mongo_db.plans.insert_one({"key": "Free", "seats": 5})  # no screens field
    assert await sc.plan_allowed(mongo_db, "Free") == set(seed) | set(START)
    await mongo_db.plans.update_one({"key": "Free"}, {"$set": {"screens": ["view:agents"]}})
    assert await sc.plan_allowed(mongo_db, "Free") == {"view:agents", *START}
    await mongo_db.plans.update_one({"key": "Free"}, {"$set": {"screens": []}})
    assert await sc.plan_allowed(mongo_db, "Free") == set(START)
    await mongo_db.plans.update_one({"key": "Free"}, {"$set": {"screens": "all"}})
    assert await sc.plan_allowed(mongo_db, "Free") == set(tf.SWITCHABLE) | set(START)


async def test_custom_and_the_platform_organization_allow_every_switch(mongo_db):  # noqa: F811
    """protects=D-17, D-26; fails_when=Custom or the exempt organization is limited to a seed list."""
    everything = set(tf.SWITCHABLE) | set(START)
    assert await sc.plan_allowed(mongo_db, "Custom") == everything
    assert await sc.plan_allowed(mongo_db, "Free", exempt=True) == everything


# --- D-30: the partner path ----------------------------------------------------------------------------

@pytest.fixture
def wired(mongo_db):  # noqa: F811
    handle = SimpleNamespace(db=mongo_db)
    with patch.object(pe, "mongodb", handle), \
            patch("audit_ledger.event", new=AsyncMock()), \
            patch("partner_invites.send_invite_email", new=AsyncMock(return_value=False)):
        yield SimpleNamespace(db=mongo_db)


async def _partner_and_customer(wired, tier, ceiling=("all",)):
    await wired.db.tenants.insert_one({
        "id": "p1", "type": "partner", "name": "P One", "license": {"maxAgents": 0},
        "partner": {"poolSize": 100, "allocated": 0, "status": "active", "screenCeiling": list(ceiling),
                    "expiresAt": None}})
    await wired.db.tenants.insert_one({
        "id": "c1", "name": "C One", "partnerId": "p1", "subscriptionTier": tier,
        "license": {"maxAgents": 5, "seatsUsed": 0}, "enabledFeatures": list(START)})


async def _put(features):
    ctx = await pe.current_partner(current_user=TokenData(username="a@p.test", role="partner_admin",
                                                          tenant_id="p1", mfa_verified=True))
    return await pe.put_customer_features("c1", pe.FeaturesBody(enabledFeatures=features), ctx=ctx)


async def test_an_unrestricted_partner_cannot_sell_a_pro_screen_to_a_free_customer(wired):
    """protects=D-30 end to end; fails_when=the partner ceiling alone decides what a customer gets."""
    await _partner_and_customer(wired, "Free")
    refused = await _put(["view:reporting"])
    assert refused.status_code == 422 and json.loads(refused.body)["code"] == "screen_outside_plan"
    assert (await wired.db.tenants.find_one({"id": "c1"}))["enabledFeatures"] == START


async def test_the_same_screen_is_stored_for_an_enterprise_customer(wired):
    """protects=D-30; fails_when=an Enterprise customer is refused a screen both limits allow."""
    await _partner_and_customer(wired, "Enterprise")
    out = await _put(["view:reporting"])
    assert out["enabledFeatures"][0] == "view:reporting" and out["plan"] == "Enterprise"


async def test_the_features_answer_names_the_plan_and_its_screens(wired):
    """protects=the portal's read of the plan; fails_when=plan or planScreens is missing, or Custom is not ['all']."""
    await _partner_and_customer(wired, "Free")
    ctx = await pe.current_partner(current_user=TokenData(username="a@p.test", role="partner_viewer",
                                                          tenant_id="p1", mfa_verified=True))
    got = await pe.get_customer_features("c1", ctx=ctx)
    assert got["plan"] == "Free" and "view:agents" in got["planScreens"] and "view:reporting" not in got["planScreens"]
    await wired.db.tenants.update_one({"id": "c1"}, {"$set": {"subscriptionTier": "Custom"}})
    assert (await pe.get_customer_features("c1", ctx=ctx))["planScreens"] == ["all"]
