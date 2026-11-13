"""Migration 035: the Phase 86 indexes (digest claim, finishedAt lookup, go-live evidence).

Value: protects=the once-per-day digest claim index exists after the user's restart and the migration touches no
document, so a double digest cannot be written and no decision row is changed; fails_when=an index of the four is
missing, digest_once_per_day is not unique, a second up() changes the index set or any document count, a seeded
autonomy_actions row changes, or the runner does not discover 035 after 034; no_claim=the live database (the
user's restart applies the migration, 86-13) and the digest, export and go-live behaviour themselves.

Real-MongoDB cases use the throwaway database of tests/_mongo_test_db.py (set MONGO_TEST_URL, MONGODB_URL and
MONGO_URI to a private mongod; never the live one) and are never skipped.
"""
import importlib
import os
import sys
from datetime import datetime, timezone

import pytest
from pymongo.errors import DuplicateKeyError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from migrations import runner
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.asyncio

NAME = "035_activity_reporting"
EXPECTED = {
    "autonomy_digests": {"digest_once_per_day"},
    "autonomy_actions": {"tenant_finished"},
    "autonomy_golive_checks": {"check_recorded", "id_unique"},
}


def _migration():
    return importlib.import_module(f"migrations.{NAME}")


async def _index_names(db, collection):
    return set((await db[collection].index_information()))


async def _counts(db):
    return {name: await db[name].count_documents({}) for name in ("autonomy_actions", "autonomy_digests",
                                                                  "autonomy_golive_checks", "tenants")}


async def test_up_on_an_empty_database_creates_the_four_indexes(mongo_db):
    await _migration().up(mongo_db)
    for collection, names in EXPECTED.items():
        assert names <= await _index_names(mongo_db, collection), collection


async def test_the_digest_claim_index_is_unique_per_tenant_and_day(mongo_db):
    await _migration().up(mongo_db)
    await mongo_db.autonomy_digests.insert_one({"tenantId": "t1", "day": "2026-11-12"})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.autonomy_digests.insert_one({"tenantId": "t1", "day": "2026-11-12"})
    await mongo_db.autonomy_digests.insert_one({"tenantId": "t2", "day": "2026-11-12"})
    await mongo_db.autonomy_digests.insert_one({"tenantId": "t1", "day": "2026-11-13"})


async def test_a_second_run_changes_no_index_and_no_document_and_a_seeded_row_is_untouched(mongo_db):
    row = {"id": "AO-keep", "tenantId": "t1", "kind": "action", "state": "executed", "command": "block_ip",
           "createdAt": datetime(2026, 11, 12, 6, tzinfo=timezone.utc),
           "finishedAt": datetime(2026, 11, 12, 6, 1, tzinfo=timezone.utc)}
    await mongo_db.autonomy_actions.insert_one(dict(row))
    await mongo_db.tenants.insert_one({"id": "t1", "name": "T1"})
    migration = _migration()
    await migration.up(mongo_db)
    first_indexes = {c: await _index_names(mongo_db, c) for c in EXPECTED}
    first_counts = await _counts(mongo_db)
    await migration.up(mongo_db)
    assert {c: await _index_names(mongo_db, c) for c in EXPECTED} == first_indexes
    assert await _counts(mongo_db) == first_counts == {"autonomy_actions": 1, "autonomy_digests": 0,
                                                       "autonomy_golive_checks": 0, "tenants": 1}
    kept = await mongo_db.autonomy_actions.find_one({"id": "AO-keep"}, {"_id": 0})
    assert {k: (v.replace(tzinfo=timezone.utc) if isinstance(v, datetime) else v) for k, v in kept.items()} == row
    assert await mongo_db.tenants.find_one({"id": "t1"}, {"_id": 0}) == {"id": "t1", "name": "T1"}


async def test_the_runner_discovers_035_after_034():
    names = [name for _, name in runner._discover_pending(set())]
    assert NAME in names and "034_plan_licensing" in names
    assert names.index(NAME) == names.index("034_plan_licensing") + 1


async def test_the_runner_applies_035_and_records_it_in_the_migrations_collection(mongo_db, monkeypatch):
    real = runner._discover_pending
    monkeypatch.setattr(runner, "_discover_pending",
                        lambda applied: [(v, n) for v, n in real(applied) if v == "035"])
    await runner.run_migrations(mongo_db)
    record = await mongo_db["_migrations"].find_one({"version": "035"}, {"_id": 0})
    assert record["module"] == NAME and record["appliedAt"]
    assert EXPECTED["autonomy_digests"] <= await _index_names(mongo_db, "autonomy_digests")
