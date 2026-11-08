"""The service desk's own settings (Phase 85, plan 85-11, DESK-02 / DESK-04 / DESK-05, D-03, D-22, D-23, D-25).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; the model is a
stand-in httpx.MockTransport, never a real Ollama.

Value: protects=the desk switch and the tenant's words are validated, every value that really changes leaves
one control row and one audit event naming the person, Post answers cannot come back after a breaker trip
except through Restore, and the status line says honestly why answers are or are not posted and whether
the local model runs; fails_when=a bad word is stored, an unchanged save is recorded, a change leaves no
record, Post answers is saved over a breaker, or the status view claims posting while a condition is unmet;
no_claim=the settings card (a later plan) and the real speed of the model on this server.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger
from service_desk import messages, model, runtime, settings
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant
from tests.service_desk_support import ollama_transport, seed_desk_tenant

ACTOR = {"username": "alice@example.test", "display": "Alice", "tier": "tenant"}
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    model.clear_probe_cache()


@pytest.fixture
async def world(mongo_db):  # noqa: F811
    await ledger.ensure_indexes(mongo_db)
    await seed_desk_tenant(mongo_db, "t1")
    return mongo_db


async def _controls(db, tenant, event=None):
    flt = {"tenantId": tenant, "kind": "control"}
    if event:
        flt["controlEvent"] = event
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0})]


async def _audit(db, tenant):
    return [e["action"] async for e in db.audit_logs.find({"tenantId": tenant})]


async def _stored(db, tenant):
    return (await db.autonomy_settings.find_one({"tenantId": tenant}, {"_id": 0})).get("serviceDesk")


async def _breaker(db, tenant, *, ids=("a1", "a2", "a3")):
    await db.autonomy_settings.update_one({"tenantId": tenant}, {"$set": {
        "serviceDesk": {"mode": "drafts", "breaker": {"trippedAt": NOW, "actionIds": list(ids)}}}})


# ================================================================== task 1: validation

def test_the_mode_must_be_one_of_the_three():
    assert settings.validate_changes({"mode": "post"}) == {"mode": "post"}
    for bad in ("auto", "", "POST", 3, True):
        with pytest.raises(settings.SettingsError) as raised:
            settings.validate_changes({"mode": bad})
        assert raised.value.detail == messages.API_DETAIL["mode_invalid"]


def test_words_are_trimmed_casefolded_and_checked_with_the_screen_sentences():
    assert settings.validate_changes({"words": ["Badge Printer ", "Pay-roll", "O'Brien & Co."]}) == {
        "words": ["badge printer", "pay-roll", "o'brien & co."]}
    cases = [(["a"], "word_shape"), (["x" * 41], "word_shape"), (["pay$roll"], "word_shape"),
             (["  "], "word_empty"), ([""], "word_empty"), ([7], "word_shape"), ("payroll", "word_shape"),
             ([str(i) + "x" for i in range(51)], "word_limit")]
    for words, code in cases:
        with pytest.raises(settings.SettingsError) as raised:
            settings.validate_changes({"words": words})
        assert raised.value.code == code and raised.value.detail == messages.API_DETAIL[code], words
    with pytest.raises(settings.SettingsError) as raised:
        settings.validate_changes({"words": ["Payroll", "payroll"]})
    assert raised.value.detail == "payroll is already on the list."
    assert len(settings.validate_changes({"words": [str(i) + "x" for i in range(50)]})["words"]) == 50
    assert settings.validate_changes({"words": ["x" * 40]}) and settings.validate_changes({"words": ["ab"]})


def test_nothing_to_change_is_an_empty_result():
    assert settings.validate_changes({}) == {} and settings.validate_changes({"mode": None, "words": None}) == {}


# ================================================================== task 1: saving and restoring

async def test_nothing_stored_reads_drafts_only(world):
    s = await settings.load(world, "t1")
    assert (s.mode, s.words, s.breaker, s.readable) == ("drafts", [], None, True)


async def test_a_mode_change_writes_one_control_row_and_one_audit_event_naming_the_person(world):
    saved = await settings.save(world, "t1", {"mode": "post"}, actor=ACTOR)
    assert saved.mode == "post" and (await _stored(world, "t1"))["mode"] == "post"
    rows = await _controls(world, "t1")
    assert len(rows) == 1 and rows[0]["controlEvent"] == "service_desk_mode_changed"
    assert rows[0]["actor"]["username"] == "alice@example.test" and rows[0]["scope"] == "tenant"
    assert rows[0]["reasonText"] == "Service desk set to Post answers."
    assert await _audit(world, "t1") == ["autonomous_ops.service_desk_mode_changed"]


async def test_saving_the_current_values_writes_nothing(world):
    await settings.save(world, "t1", {"mode": "post", "words": ["payroll"]}, actor=ACTOR)
    assert len(await _controls(world, "t1")) == 2
    again = await settings.save(world, "t1", {"mode": "post", "words": ["Payroll"]}, actor=ACTOR)
    assert again.mode == "post" and again.words == ["payroll"]
    assert len(await _controls(world, "t1")) == 2 and len(await _audit(world, "t1")) == 2
    assert (await settings.save(world, "t1", {}, actor=ACTOR)).mode == "post"
    assert len(await _controls(world, "t1")) == 2


async def test_a_words_change_writes_one_control_row(world):
    saved = await settings.save(world, "t1", {"words": ["Payroll", "badge printer"]}, actor=ACTOR)
    assert saved.words == ["payroll", "badge printer"] and saved.mode == "drafts"
    rows = await _controls(world, "t1", "service_desk_words_changed")
    assert len(rows) == 1 and "2 extra words" in rows[0]["reasonText"]
    assert len(await _controls(world, "t1")) == 1
    await settings.save(world, "t1", {"words": []}, actor=ACTOR)
    cleared = await _controls(world, "t1", "service_desk_words_changed")
    assert len(cleared) == 2 and (await settings.load(world, "t1")).words == []


async def test_both_values_changed_at_once_write_two_rows(world):
    await settings.save(world, "t1", {"mode": "off", "words": ["payroll"]}, actor=ACTOR, scope="platform")
    rows = await _controls(world, "t1")
    assert sorted(r["controlEvent"] for r in rows) == ["service_desk_mode_changed", "service_desk_words_changed"]
    assert {r["scope"] for r in rows} == {"platform"}


async def test_post_answers_is_refused_while_the_breaker_is_stored(world):
    await _breaker(world, "t1")
    with pytest.raises(settings.SettingsError) as raised:
        await settings.save(world, "t1", {"mode": "post"}, actor=ACTOR)
    assert raised.value.code == "breaker_tripped" and raised.value.detail == "Restore Post answers first."
    assert (await _stored(world, "t1"))["mode"] == "drafts" and await _controls(world, "t1") == []
    off = await settings.save(world, "t1", {"mode": "off"}, actor=ACTOR)       # moving down is always allowed
    assert off.mode == "off" and off.breaker is not None
    assert (await settings.save(world, "t1", {"words": ["payroll"]}, actor=ACTOR)).words == ["payroll"]


async def test_restore_clears_the_breaker_sets_post_and_records_once(world):
    await _breaker(world, "t1")
    restored = await settings.restore(world, "t1", actor=ACTOR)
    assert restored.mode == "post" and restored.breaker is None
    rows = await _controls(world, "t1", "service_desk_restored")
    assert len(rows) == 1 and rows[0]["actor"]["username"] == "alice@example.test"
    assert "autonomous_ops.service_desk_restored" in await _audit(world, "t1")
    with pytest.raises(settings.SettingsError) as raised:
        await settings.restore(world, "t1", actor=ACTOR)
    assert raised.value.code == "not_tripped"
    assert len(await _controls(world, "t1", "service_desk_restored")) == 1
    assert (await settings.save(world, "t1", {"mode": "post"}, actor=ACTOR)).mode == "post"      # breaker is gone


async def test_restore_without_a_breaker_is_refused(world):
    with pytest.raises(settings.SettingsError) as raised:
        await settings.restore(world, "t1", actor=ACTOR)
    assert raised.value.code == "not_tripped" and await _controls(world, "t1") == []


async def test_the_platform_tenant_is_refused(world):
    for call in (settings.save(world, "platform-admin", {"mode": "post"}, actor=ACTOR),
                 settings.restore(world, "platform-admin", actor=ACTOR)):
        with pytest.raises(settings.PlatformTenantError) as raised:
            await call
        assert raised.value.detail == messages.API_DETAIL["platform_tenant"]
    assert await world.autonomy_settings.find_one({"tenantId": "platform-admin"}) is None


async def test_a_change_that_cannot_be_recorded_is_put_back(world, monkeypatch):
    async def broken(*args, **kwargs):
        raise ledger.LedgerUnavailable("down")
    monkeypatch.setattr(ledger, "record_control", broken)
    with pytest.raises(ledger.LedgerUnavailable):
        await settings.save(world, "t1", {"mode": "post", "words": ["payroll"]}, actor=ACTOR)
    s = await settings.load(world, "t1")
    assert (s.mode, s.words) == ("drafts", [])
    await _breaker(world, "t1")
    with pytest.raises(ledger.LedgerUnavailable):
        await settings.restore(world, "t1", actor=ACTOR)
    s = await settings.load(world, "t1")
    assert s.mode == "drafts" and s.breaker is not None


async def test_a_value_that_was_not_understood_is_repaired_by_a_save(world):
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {"mode": "bogus"}}})
    assert (await settings.load(world, "t1")).readable is False
    saved = await settings.save(world, "t1", {"mode": "drafts"}, actor=ACTOR)
    assert saved.readable is True and saved.mode == "drafts"
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": "junk"}})
    saved = await settings.save(world, "t1", {"words": ["payroll"]}, actor=ACTOR)
    assert saved.readable is True and saved.words == ["payroll"] and saved.mode == "drafts"


# ================================================================== task 2: the status view

def _client(tags=("llama3.2:3b",), **kwargs):
    transport, calls = ollama_transport("answer", [1], tags=tags, **kwargs)
    return (lambda: model.OllamaClient(transport=transport)), calls


async def _view(db, tenant="t1", factory=None, **kwargs):
    factory = factory or _client()[0]
    return await settings.status_view(db, tenant, can_manage=True, can_restore=True, client_factory=factory, **kwargs)


async def _desk_post_ready(db, tenant="t1"):
    """Level Undoable-auto, shadow off, no stop, saved mode post: every condition met."""
    await seed_desk_tenant(db, tenant, level="undoable_auto", shadow=False, mode="post")


async def _desk_rows(db, tenant, gen_ms=(), *, count=0, age=timedelta(minutes=5)):
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:6]
    rows = [{"id": f"AO-{tenant}-{tag}-g{i}", "tenantId": tenant, "kind": "servicedesk", "state": "executed",
             "autoDispatched": True, "createdAt": now - timedelta(minutes=i + 1),
             "reason": {"ruleId": "service_desk:answer", "inputs": {"genMs": ms}}} for i, ms in enumerate(gen_ms)]
    rows += [{"id": f"AO-{tenant}-{tag}-c{i}", "tenantId": tenant, "kind": "servicedesk", "state": "executed",
              "autoDispatched": True, "createdAt": now - age, "reason": {"ruleId": "service_desk:answer", "inputs": {}}}
             for i in range(count)]
    if rows:
        await db.autonomy_actions.insert_many(rows)


async def test_a_tenant_with_nothing_stored_reads_drafts_with_the_full_shape(world):
    view = await _view(world)
    assert view["mode"] == "drafts" and view["effectiveMode"] == "drafts" and view["readable"] is True
    assert view["screensOn"] is True and view["words"] == [] and view["maxWords"] == 50 and view["breaker"] is None
    assert view["posting"] == {"posting": False, "blockers": []}
    assert view["canManage"] is True and view["canRestore"] is True
    assert set(view) == {"mode", "effectiveMode", "readable", "screensOn", "words", "maxWords", "breaker", "posting",
                         "model", "timing", "canManage", "canRestore"}


async def test_an_unreadable_value_reads_drafts_and_says_so(world):
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {"mode": "bogus"}}})
    view = await _view(world)
    assert view["mode"] == "drafts" and view["readable"] is False and view["posting"]["posting"] is False


async def test_post_with_suggest_level_and_shadow_on_lists_both_blockers(world):
    await seed_desk_tenant(world, "t1", level="suggest", shadow=True, mode="post")
    view = await _view(world)
    assert view["posting"] == {"posting": False,
                               "blockers": [{"code": "level", "level": "suggest"}, {"code": "shadow"}]}


async def test_the_deployment_master_alone_keeps_shadow_on(world, monkeypatch):
    await _desk_post_ready(world)
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "true")
    view = await _view(world)
    assert view["posting"] == {"posting": False, "blockers": [{"code": "shadow"}]}


async def test_all_conditions_met_is_posting(world):
    await _desk_post_ready(world)
    view = await _view(world)
    assert view["posting"] == {"posting": True, "blockers": []} and view["effectiveMode"] == "post"


async def test_a_tenant_stop_and_a_platform_stop_are_blockers(world):
    await _desk_post_ready(world)
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {"active": True}}})
    assert (await _view(world))["posting"]["blockers"] == [{"code": "stop"}]
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": None}})
    await world.system_settings.insert_one({"type": "autonomous_ops", "stop": {"active": True}})
    assert (await _view(world))["posting"]["blockers"] == [{"code": "stop"}]


async def test_an_unreadable_platform_stop_counts_as_stopped(world, monkeypatch):
    await _desk_post_ready(world)

    async def broken(db):
        raise RuntimeError("down")
    monkeypatch.setattr(settings.ao_settings, "platform_stop", broken)
    assert (await _view(world))["posting"]["blockers"] == [{"code": "stop"}]


async def test_twenty_desk_answers_in_the_last_hour_block_posting_nineteen_do_not(world):
    await _desk_post_ready(world)
    await _desk_rows(world, "t1", count=19)
    assert (await _view(world))["posting"]["posting"] is True
    await _desk_rows(world, "t1", count=1)
    view = await _view(world)
    assert view["posting"] == {"posting": False, "blockers": [{"code": "hourly_limit"}]}


async def test_desk_answers_older_than_an_hour_and_other_tenants_rows_do_not_count(world):
    await _desk_post_ready(world)
    await seed_tenant(world, "t2", shadow=False)
    await _desk_rows(world, "t1", count=25, age=timedelta(hours=2))
    await _desk_rows(world, "t2", count=25)
    assert (await _view(world))["posting"]["blockers"] == []


async def test_a_stored_breaker_is_a_blocker_and_shows_when_and_how_many(world):
    await _desk_post_ready(world)
    await world.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {
        "serviceDesk": {"mode": "post", "breaker": {"trippedAt": NOW, "actionIds": ["a", "b", "c"]}}}})
    view = await _view(world)
    assert {"code": "desk_breaker"} in view["posting"]["blockers"] and view["posting"]["posting"] is False
    assert view["breaker"] == {"trippedAt": "2026-01-01T12:00:00+00:00", "count": 3}


async def test_drafts_and_off_show_no_blocker_list_and_never_posting(world):
    for mode in ("drafts", "off"):
        await seed_desk_tenant(world, "t1", level="suggest", shadow=True, mode=mode)
        view = await _view(world)
        assert view["posting"] == {"posting": False, "blockers": []} and view["mode"] == mode


async def test_the_model_is_online_only_for_the_exact_tag(world):
    online = (await _view(world))["model"]
    assert online == {"state": "online", "tag": "llama3.2:3b"}
    other, calls = _client(tags=("llama3.2:1b",))
    model.clear_probe_cache()
    assert (await _view(world, factory=other))["model"]["state"] == "offline"
    assert all(c["path"] == "/api/tags" for c in calls)        # the status line never generates


async def test_a_failing_or_non_loopback_model_is_offline_and_a_factory_error_too(world):
    broken, _ = _client(fail_tags=True)
    assert (await _view(world, factory=broken))["model"]["state"] == "offline"
    model.clear_probe_cache()
    transport, calls = ollama_transport("a", [1])
    remote = lambda: model.OllamaClient(base_url="http://203.0.113.9:11434", transport=transport)  # noqa: E731
    assert (await _view(world, factory=remote))["model"]["state"] == "offline" and calls == []

    def explode():
        raise RuntimeError("no client")
    assert (await _view(world, factory=explode))["model"] == {"state": "offline", "tag": None}


async def test_the_typical_answer_time_is_the_median_of_the_last_twenty_rows(world):
    await _desk_rows(world, "t1", [60000, 100000, 140000])
    assert (await _view(world))["timing"] == {"medianSeconds": 100, "samples": 3, "measured": False}
    await _desk_rows(world, "t1", [1500, 2500])
    assert (await _view(world))["timing"]["medianSeconds"] == 60       # 5 rows, middle one 60 s


async def test_no_data_says_none_and_samples_zero_and_other_tenants_rows_are_ignored(world):
    await seed_tenant(world, "t2", shadow=False)
    await _desk_rows(world, "t2", [90000])
    assert (await _view(world))["timing"] == {"medianSeconds": None, "samples": 0, "measured": False}


async def test_only_the_newest_twenty_count(world):
    await _desk_rows(world, "t1", [10000] * 20)                 # the newest twenty
    now = datetime.now(timezone.utc)
    await world.autonomy_actions.insert_many([
        {"id": f"AO-old-{i}", "tenantId": "t1", "kind": "servicedesk", "state": "executed", "autoDispatched": True,
         "createdAt": now - timedelta(days=2, minutes=i), "reason": {"inputs": {"genMs": 200000}}} for i in range(5)])
    assert (await _view(world))["timing"] == {"medianSeconds": 10, "samples": 20, "measured": False}


async def test_a_runtime_document_makes_the_timing_measured(world):
    await runtime.save_measurement(world, {"model": "llama3.2:3b", "prefillTps": 12, "genTps": 4, "loadSeconds": 15})
    assert (await _view(world))["timing"]["measured"] is True


async def test_a_tenant_without_the_knowledge_base_screen_is_off(world):
    await seed_desk_tenant(world, "t1", level="undoable_auto", shadow=False, mode="post", screens=False)
    view = await _view(world)
    assert view["screensOn"] is False and view["effectiveMode"] == "off" and view["mode"] == "post"
    assert view["posting"]["posting"] is False
    await seed_desk_tenant(world, "t1", level="undoable_auto", shadow=False, mode="post")
    await world.tenants.update_one({"id": "t1"}, {"$pull": {"enabledFeatures": "screen:internalTickets"}})
    assert (await _view(world))["screensOn"] is False


async def test_the_status_view_never_sends_a_real_request(world):
    """A client built with a mock transport is the only way a request leaves; the default factory is the
    loopback client and its probe is bounded, so it is exercised only through the stand-in here."""
    factory, calls = _client()
    await _view(world, factory=factory)
    assert [c["method"] + " " + c["path"] for c in calls] == ["GET /api/tags"]
