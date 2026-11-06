"""Staged patch rollouts, plan 84-06 task 1: a tenant's rings, built from its own agent groups.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=PTCH-01 / PTCH-07: a tenant saves 2 to 4 rings from its own groups, the first is always the
Canary with a group, a group belongs to one ring, another tenant's group and a deleted group are refused,
every save is on the ledger and the audit chain naming the person, the platform tenant is refused, and the
agent group list shows which ring a group is in; fails_when=a ring setting outside its range is stored, a
group of another organization is accepted, a save leaves no ledger row or no audit event, or the platform
organization can save rings;
no_claim=a rollout starting (plan 84-06 task 2) or the HTTP route (plan 84-09).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import PLATFORM_TENANT_ID, ledger
from autonomous_ops.response_settings import PlatformTenantError
from autonomous_ops.rollout import messages, rings
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import seed_group, seed_rollout_agent, seed_rollout_tenant

T = "t1"
ACTOR = {"id": "u1", "username": "ann@example.com", "display": "Ann"}
BOOT = 1_700_000_000


def ring(name, groups=(), **checks):
    return {"name": name, "groupIds": list(groups), **checks}


GOOD = [ring("Canary", ["G1"]), ring("Pilot", ["G2"], soakHours=48, failPct=20, minSample=5), ring("Everyone else")]


async def world(db):
    await ledger.ensure_indexes(db)
    await seed_rollout_tenant(db, T)
    await seed_rollout_tenant(db, "t2")
    await seed_group(db, T, "G1", [])
    await seed_group(db, T, "G2", [])
    await seed_group(db, T, "G3", [])
    await seed_group(db, "t2", "X1", [])
    return db


async def refusal(db, items, sentence):
    with pytest.raises(rings.RingsError) as caught:
        await rings.save(db, T, items, actor=ACTOR)
    assert caught.value.detail == sentence
    assert await db.patch_rollout_settings.count_documents({"tenantId": T}) == 0


async def test_a_valid_save_is_stored_loaded_and_recorded_once_with_the_person(mongo_db):
    db = await world(mongo_db)
    saved = await rings.save(db, T, GOOD, actor=ACTOR)
    assert [r.name for r in saved] == ["Canary", "Pilot", "Everyone else"]
    loaded = await rings.load(db, T)
    assert loaded.readable and [r.name for r in loaded.rings] == ["Canary", "Pilot", "Everyone else"]
    assert [r.groupIds for r in loaded.rings] == [["G1"], ["G2"], []]
    first, second, last = loaded.rings
    assert (first.soakHours, first.failPct, first.minSample) == (24, 10, 10)          # the D-10 defaults
    assert (second.soakHours, second.failPct, second.minSample) == (48, 20, 5)
    assert len({r.key for r in loaded.rings}) == 3 and first.key == "canary"
    doc = await db.patch_rollout_settings.find_one({"tenantId": T})
    assert doc["updatedBy"]["name"] == "Ann" and doc["updatedAt"] is not None
    controls = [r async for r in db.autonomy_actions.find({"tenantId": T, "kind": "control"})]
    assert len(controls) == 1 and controls[0]["controlEvent"] == "rollout_rings_saved"
    assert controls[0]["actor"]["display"] == "Ann" and "Canary" in controls[0]["reasonText"]
    audit = [e async for e in db.audit_logs.find({"tenantId": T, "action": "autonomous_ops.rollout_rings_saved"})]
    assert len(audit) == 1 and audit[0]["actor"]["email"] == "ann@example.com"


async def test_saving_again_replaces_the_rings_and_writes_a_second_row(mongo_db):
    db = await world(mongo_db)
    await rings.save(db, T, GOOD, actor=ACTOR)
    await rings.save(db, T, [ring("Canary", ["G3"]), ring("Everyone else")], actor=ACTOR)
    assert [r.name for r in (await rings.load(db, T)).rings] == ["Canary", "Everyone else"]
    assert await db.autonomy_actions.count_documents({"tenantId": T, "kind": "control"}) == 2


async def test_two_to_four_rings_only(mongo_db):
    db = await world(mongo_db)
    sentence = messages.VALIDATION["ring_count"]
    await refusal(db, [ring("Canary", ["G1"])], sentence)
    await refusal(db, [], sentence)
    five = [ring("Canary", ["G1"]), ring("A", ["G2"]), ring("B", ["G3"]), ring("C", []), ring("D", [])]
    await refusal(db, five, sentence)
    await refusal(db, "not a list", sentence)
    four = [ring("Canary", ["G1"]), ring("A", ["G2"]), ring("B", ["G3"]), ring("C")]
    assert len(await rings.save(db, T, four, actor=ACTOR)) == 4


async def test_the_canary_needs_a_group_and_keeps_its_name(mongo_db):
    db = await world(mongo_db)
    await refusal(db, [ring("Canary"), ring("Everyone else")], messages.VALIDATION["canary_group"])
    await refusal(db, [ring("Early", ["G1"]), ring("Everyone else")], messages.VALIDATION["canary_name"])
    saved = await rings.save(db, T, [{"groupIds": ["G1"]}, ring("Everyone else")], actor=ACTOR)
    assert saved[0].name == "Canary"                                   # the first name is fixed, so it may be left out


async def test_ring_names_must_be_present_unique_and_short(mongo_db):
    db = await world(mongo_db)
    await refusal(db, [ring("Canary", ["G1"]), ring("  ")], messages.VALIDATION["ring_name"])
    await refusal(db, [ring("Canary", ["G1"]), {"groupIds": []}], messages.VALIDATION["ring_name"])
    await refusal(db, [ring("Canary", ["G1"]), ring("Pilot", ["G2"]), ring("pilot")],
                  messages.VALIDATION["ring_names_unique"])
    await refusal(db, [ring("Canary", ["G1"]), ring("canary")], messages.VALIDATION["ring_names_unique"])
    await refusal(db, [ring("Canary", ["G1"]), ring("x" * 41)], messages.VALIDATION["ring_name_long"])
    assert len(await rings.save(db, T, [ring("Canary", ["G1"]), ring("x" * 40)], actor=ACTOR)) == 2


@pytest.mark.parametrize("field, bad, good, key", [
    ("soakHours", 0, 1, "soak_hours"), ("soakHours", 169, 168, "soak_hours"), ("soakHours", True, 24, "soak_hours"),
    ("soakHours", "24", 24, "soak_hours"),
    ("failPct", 0, 1, "fail_pct"), ("failPct", 51, 50, "fail_pct"), ("failPct", 10.5, 10, "fail_pct"),
    ("minSample", 0, 1, "min_sample"), ("minSample", 101, 100, "min_sample"), ("minSample", None, 10, "min_sample"),
])
async def test_the_checks_stay_inside_their_ranges(mongo_db, field, bad, good, key):
    db = await world(mongo_db)
    await refusal(db, [ring("Canary", ["G1"]), ring("Pilot", ["G2"], **{field: bad})], messages.VALIDATION[key])
    assert len(await rings.save(db, T, [ring("Canary", ["G1"]), ring("Pilot", ["G2"], **{field: good})],
                                actor=ACTOR)) == 2


async def test_a_group_belongs_to_one_ring_and_must_be_the_tenants_own(mongo_db):
    db = await world(mongo_db)
    await refusal(db, [ring("Canary", ["G1"]), ring("Pilot", ["G1"])], messages.VALIDATION["group_twice"])
    await refusal(db, [ring("Canary", ["G1", "G1"]), ring("Pilot")], messages.VALIDATION["group_twice"])
    await refusal(db, [ring("Canary", ["X1"]), ring("Pilot")], messages.VALIDATION["group_unknown"])   # another tenant's group
    await refusal(db, [ring("Canary", ["G1"]), ring("Pilot", ["nope"])], messages.VALIDATION["group_unknown"])
    await refusal(db, [ring("Canary", [7]), ring("Pilot")], messages.VALIDATION["group_unknown"])
    await refusal(db, [ring("Canary", ["G1"]), ring("Pilot", "G2")], messages.VALIDATION["group_unknown"])
    await db.agent_groups.delete_one({"id": "G2"})                                                  # a deleted group
    await refusal(db, [ring("Canary", ["G1"]), ring("Pilot", ["G2"])], messages.VALIDATION["group_unknown"])


async def test_every_ring_but_the_last_needs_a_group(mongo_db):
    db = await world(mongo_db)
    await refusal(db, [ring("Canary", ["G1"]), ring("Pilot"), ring("Everyone else")], messages.VALIDATION["ring_group"])


async def test_a_refused_save_leaves_the_old_rings_and_writes_no_row(mongo_db):
    db = await world(mongo_db)
    await rings.save(db, T, GOOD, actor=ACTOR)
    with pytest.raises(rings.RingsError):
        await rings.save(db, T, [ring("Canary", ["G1"]), ring("Pilot", ["G1"])], actor=ACTOR)
    assert [r.name for r in (await rings.load(db, T)).rings] == ["Canary", "Pilot", "Everyone else"]
    assert await db.autonomy_actions.count_documents({"tenantId": T, "kind": "control"}) == 1


async def test_the_platform_tenant_cannot_save_rings(mongo_db):
    db = await world(mongo_db)
    await seed_group(db, PLATFORM_TENANT_ID, "PG", [])
    with pytest.raises(PlatformTenantError) as caught:
        await rings.save(db, PLATFORM_TENANT_ID, [ring("Canary", ["PG"]), ring("Everyone else")], actor=ACTOR)
    assert isinstance(caught.value, rings.RingsError)
    assert await db.patch_rollout_settings.count_documents({}) == 0


async def test_membership_puts_a_host_in_two_groups_in_the_earlier_ring_and_an_ungrouped_host_in_the_last(mongo_db):
    db = await world(mongo_db)
    await seed_group(db, T, "G1", ["h1", "h2"])
    await seed_group(db, T, "G2", ["h2", "h3"])
    saved = await rings.save(db, T, GOOD, actor=ACTOR)
    placed = await rings.membership(db, T, saved, ["h1", "h2", "h3", "h4"])
    assert placed == {"h1": 0, "h2": 0, "h3": 1, "h4": 2}


async def test_ring_names_by_group_lists_only_groups_a_ring_uses(mongo_db):
    db = await world(mongo_db)
    await rings.save(db, T, GOOD, actor=ACTOR)
    assert await rings.ring_names_by_group(db, T) == {"G1": "Canary", "G2": "Pilot"}
    assert await rings.ring_names_by_group(db, "t2") == {}


async def test_the_agent_group_list_carries_the_ring_name(mongo_db, monkeypatch):
    import agent_group_endpoints
    from auth import TokenData
    db = await world(mongo_db)
    await rings.save(db, T, GOOD, actor=ACTOR)
    monkeypatch.setattr(agent_group_endpoints, "get_database", lambda: db)
    user = TokenData(username="ann@example.com", tenant_id=T)
    groups = {g["id"]: g for g in await agent_group_endpoints.list_groups(current_user=user)}
    assert groups["G2"]["ringName"] == "Pilot" and groups["G1"]["ringName"] == "Canary"
    assert groups["G3"]["ringName"] is None
