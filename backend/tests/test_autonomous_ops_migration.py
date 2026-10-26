"""Migration 024 (explicit per-tenant autonomy settings, ledger and stamp indexes) and the
tenant-creation hooks that give a new tenant the same default (GATE-01).

Real-Mongo cases use the throwaway database from tests/_mongo_test_db.py and skip when no
server is reachable; the hook-failure cases need no database.
"""
import importlib
import logging
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-autonomy-migration")

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

migration = importlib.import_module("migrations.024_autonomous_ops")


async def _settings(db):
    return {d["tenantId"]: d async for d in db.autonomy_settings.find({}, {"_id": 0})}


async def _index_names(db, collection):
    return {name async for name in _names(db[collection])}


async def _names(coll):
    for name in (await coll.index_information()):
        yield name


# ------------------------------------------------------------------ Task 1: the migration

@pytest.mark.asyncio
async def test_migration_writes_an_explicit_document_per_tenant_and_skips_id_less(mongo_db):
    await mongo_db.tenants.insert_many([
        {"id": "platform-admin", "name": "Platform"},
        {"id": "t-a", "name": "A"},
        {"id": "t-b", "name": "B"},
        {"name": "no id at all"},
    ])
    await migration.up(mongo_db)
    docs = await _settings(mongo_db)
    assert set(docs) == {"platform-admin", "t-a", "t-b"}
    assert (docs["platform-admin"]["level"], docs["platform-admin"]["maxLevel"]) == ("off", "off")
    for tid in ("t-a", "t-b"):
        assert (docs[tid]["level"], docs[tid]["maxLevel"]) == ("undoable_auto", "undoable_auto")
    for d in docs.values():
        assert d["shadow"] is True and d["stop"] is None


@pytest.mark.asyncio
async def test_second_run_modifies_nothing_and_a_stored_level_is_kept(mongo_db):
    await mongo_db.tenants.insert_many([{"id": "t-a"}, {"id": "t-b"}])
    await mongo_db.autonomy_settings.insert_one(
        {"tenantId": "t-a", "level": "suggest", "maxLevel": "undoable_auto", "shadow": False,
         "stop": None, "breaker": None})
    await migration.up(mongo_db)
    before = await _settings(mongo_db)
    assert before["t-a"]["level"] == "suggest" and before["t-a"]["shadow"] is False

    await migration.up(mongo_db)
    after = await _settings(mongo_db)
    assert after == before
    assert await mongo_db.autonomy_settings.count_documents({}) == 2
    # No document is touched on the second run: the update-time of every document is unchanged.
    res = await mongo_db.autonomy_settings.update_many(
        {"tenantId": {"$in": list(after)}}, {"$setOnInsert": {"level": "off"}})
    assert res.modified_count == 0


@pytest.mark.asyncio
async def test_empty_tenants_only_creates_indexes(mongo_db):
    await migration.up(mongo_db)
    assert await mongo_db.autonomy_settings.count_documents({}) == 0
    assert "tenant_unique" in await _index_names(mongo_db, "autonomy_settings")


@pytest.mark.asyncio
async def test_tenant_order_does_not_change_the_result(mongo_db):
    ids = ["t-a", "platform-admin", "t-b", "t-c"]
    await mongo_db.tenants.insert_many([{"id": i} for i in ids])
    await migration.up(mongo_db)
    forward = {k: {f: v for f, v in d.items() if f not in ("updatedAt",)}
               for k, d in (await _settings(mongo_db)).items()}

    await mongo_db.autonomy_settings.delete_many({})
    await mongo_db.tenants.delete_many({})
    await mongo_db.tenants.insert_many([{"id": i} for i in reversed(ids)])
    await migration.up(mongo_db)
    backward = {k: {f: v for f, v in d.items() if f not in ("updatedAt",)}
                for k, d in (await _settings(mongo_db)).items()}
    assert forward == backward
    assert forward["platform-admin"]["level"] == "off"


@pytest.mark.asyncio
async def test_migration_creates_every_index(mongo_db):
    await migration.up(mongo_db)
    assert "tenant_unique" in await _index_names(mongo_db, "autonomy_settings")
    actions = await _index_names(mongo_db, "autonomy_actions")
    assert {"id_unique", "open_dedupe", "state_expiry"} <= actions
    assert {"id_unique", "entry_unique"} <= await _index_names(mongo_db, "autonomy_never_touch")
    for coll in ("agent_instructions", "response_tasks"):
        info = await mongo_db[coll].index_information()
        stamp = [v for v in info.values()
                 if v.get("partialFilterExpression") == {"autonomy.actionId": {"$exists": True}}]
        assert stamp, f"{coll} has no autonomy stamp partial index"
        assert [k for k, _ in stamp[0]["key"]] == ["autonomy.tenantId", "status"]
    # The partial unique dedupe index is the one the gate relies on.
    info = await mongo_db.autonomy_actions.index_information()
    assert info["open_dedupe"]["unique"] is True and "partialFilterExpression" in info["open_dedupe"]


@pytest.mark.asyncio
async def test_running_the_migration_twice_keeps_the_indexes(mongo_db):
    await migration.up(mongo_db)
    first = {c: await _index_names(mongo_db, c) for c in
             ("autonomy_settings", "autonomy_actions", "agent_instructions", "response_tasks")}
    await migration.up(mongo_db)
    second = {c: await _index_names(mongo_db, c) for c in first}
    assert first == second


def test_migration_is_discovered_by_the_runner():
    from migrations import runner
    pending = dict(runner._discover_pending(set()))
    assert pending.get("024") == "024_autonomous_ops"
    assert migration.DESCRIPTION




# ------------------------------------------------------------------ Task 2: creation hooks

def _tenant_payload():
    import tenant_endpoints
    return tenant_endpoints.TenantCreate(name="Hook Co", subscriptionTier="Free", maxAgents=5,
                                         enabledFeatures=["view:overview"])


def _super():
    from auth_types import TokenData
    return TokenData(username="super@omni.test", role="Super Admin", tenant_id="platform-admin",
                     mfa_verified=True)


async def _add_tenant(db):
    import tenant_endpoints
    with patch.object(tenant_endpoints, "mongodb", SimpleNamespace(db=db)):
        return await tenant_endpoints.create_tenant(_tenant_payload(), _super())


async def _sign_up(db):
    import authentication_endpoints as ae
    request = MagicMock()
    request.client.host = "127.0.0.1"
    data = {"companyName": "Sign Co", "name": "Sam", "email": "sam@signco.test",
            "password": "Str0ng!Passw0rd#2026"}
    with patch.object(ae, "get_database", lambda: db), patch.object(ae, "_audit_login", AsyncMock()):
        return await ae.signup.__wrapped__(request, MagicMock(), data)


@pytest.mark.asyncio
async def test_add_tenant_writes_the_default_settings(mongo_db):
    tenant = await _add_tenant(mongo_db)
    doc = await mongo_db.autonomy_settings.find_one({"tenantId": tenant["id"]}, {"_id": 0})
    assert doc is not None
    assert (doc["level"], doc["maxLevel"], doc["shadow"]) == ("undoable_auto", "undoable_auto", True)


@pytest.mark.asyncio
async def test_sign_up_writes_the_default_settings(mongo_db):
    result = await _sign_up(mongo_db)
    doc = await mongo_db.autonomy_settings.find_one({"tenantId": result["tenant"]["id"]}, {"_id": 0})
    assert doc is not None
    assert (doc["level"], doc["maxLevel"], doc["shadow"]) == ("undoable_auto", "undoable_auto", True)


@pytest.mark.asyncio
async def test_add_tenant_survives_a_settings_failure(mongo_db, caplog):
    with patch("autonomous_ops.settings.ensure_tenant", AsyncMock(side_effect=RuntimeError("boom"))):
        with caplog.at_level(logging.WARNING):
            tenant = await _add_tenant(mongo_db)
    assert await mongo_db.tenants.find_one({"id": tenant["id"]}) is not None
    assert any("autonomy" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_sign_up_survives_a_settings_failure(mongo_db, caplog):
    with patch("autonomous_ops.settings.ensure_tenant", AsyncMock(side_effect=RuntimeError("boom"))):
        with caplog.at_level(logging.WARNING):
            result = await _sign_up(mongo_db)
    assert await mongo_db.tenants.find_one({"id": result["tenant"]["id"]}) is not None
    assert any("autonomy" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_both_handlers_call_ensure_tenant_with_the_new_tenant_id(mongo_db):
    ensure = AsyncMock()
    with patch("autonomous_ops.settings.ensure_tenant", ensure):
        added = await _add_tenant(mongo_db)
        signed = await _sign_up(mongo_db)
    called = [c.args[1] for c in ensure.await_args_list]
    assert added["id"] in called and signed["tenant"]["id"] in called
