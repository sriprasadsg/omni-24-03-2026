"""Staged patch rollouts, plan 84-22: migration 031 and the controller loop around ``controller.tick``.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. The migration is
only ever run against that throwaway database.

Value: protects=PTCH-07 / PTCH-01: the index that keeps a computer in one rollout exists on live before the
controller acts, a repeat run changes nothing, one controller runs at a time, nothing runs without the claim
index, and a restart picks a rollout up from what is stored; fails_when=the migration backfills or deletes a
document, a second run changes an index, two controllers tick together, a tick runs while duplicate active
claims exist, a restart writes a second instruction, or a failing pass ends the loop;
no_claim=a real restart of the backend or the live database.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

migration = importlib.import_module("migrations.031_patch_rollouts")


async def _definitions(db, collection):
    info = await db[collection].index_information()
    return {name: {k: v for k, v in spec.items() if k != "v"} for name, spec in info.items()}


# ---------------------------------------------------------------- Task 1: migration 031

async def test_migration_creates_the_claim_index_and_the_lookups(mongo_db):
    await migration.up(mongo_db)
    claims = await _definitions(mongo_db, "patch_rollout_hosts")
    claim = claims["one_active_rollout_per_host"]
    assert claim["unique"] is True and claim["partialFilterExpression"] == {"active": True}
    assert [k for k, _ in claim["key"]] == ["tenantId", "agentId"]
    assert [k for k, _ in claims["tenant_rollout_ring"]["key"]] == ["tenantId", "rolloutId", "ring"]
    assert [k for k, _ in (await _definitions(mongo_db, "patch_rollouts"))["tenant_status"]["key"]] \
        == ["tenantId", "status"]


async def test_running_the_migration_twice_changes_no_index(mongo_db):
    await migration.up(mongo_db)
    first = {c: await _definitions(mongo_db, c) for c in ("patch_rollouts", "patch_rollout_hosts")}
    await migration.up(mongo_db)
    second = {c: await _definitions(mongo_db, c) for c in first}
    assert first == second


async def test_the_migration_backfills_and_deletes_nothing(mongo_db):
    rollout = {"id": "r1", "tenantId": "t1", "status": "running", "rings": [{"key": "canary"}]}
    host = {"tenantId": "t1", "rolloutId": "r1", "agentId": "a1", "ring": 0, "active": True, "state": "waiting"}
    await mongo_db.patch_rollouts.insert_one(dict(rollout))
    await mongo_db.patch_rollout_hosts.insert_one(dict(host))
    await migration.up(mongo_db)
    await migration.up(mongo_db)
    assert await mongo_db.patch_rollouts.count_documents({}) == 1
    assert await mongo_db.patch_rollout_hosts.count_documents({}) == 1
    assert await mongo_db.patch_rollouts.find_one({}, {"_id": 0}) == rollout
    assert await mongo_db.patch_rollout_hosts.find_one({}, {"_id": 0}) == host


def test_the_runner_discovers_migration_031():
    from migrations import runner
    assert dict(runner._discover_pending(set())).get("031") == "031_patch_rollouts"
    assert migration.DESCRIPTION
