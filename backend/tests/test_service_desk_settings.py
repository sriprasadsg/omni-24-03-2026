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
