"""The go-live test organization (Phase 86, plan 86-14, GATE-09, D-23).

Real MongoDB through the throwaway database of tests/_mongo_test_db.py; the platform and go-live routers are
mounted through the Phase 81 HTTP harness (the 86-07 fixtures are reused).

Value: protects=PROH-86-04 / PROH-86-14: exactly one Super Admin-marked organization may leave shadow mode
without the five checks and the seven days, every other organization keeps the full gate, the mark cannot be
set twice, set on the platform organization, or cleared while the organization is lifted or its shadow flag
cannot be confirmed (T-86-14-03: checked before the clear and again after it, and a lift of the test
organization is checked again after the write), and the read of the mark fails closed; fails_when=a second
organization is exempted, a customer organization skips the gate, a failed read exempts, the mark is cleared
while the organization is live or unconfirmed, a clear and a lift racing leave a lifted organization unmarked,
or an unprivileged caller marks; no_claim=the Going live card (86-15) and a real browser session.
"""
import logging
import os
import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import settings as ao_settings
from autonomous_ops.reporting import GOLIVE_TEST_ORG, TEST_ORG_DOC_ID, golive_test_org
from tests._autonomous_ops_http import _env, api  # noqa: F401  (fixtures)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant
from tests.test_autonomous_ops_golive import (  # noqa: F401  (fixtures and helpers of the 86-07 suite)
    ALL_SCOPES, GOLIVE, NOW, OWNER, PLAT, SHADOW, _golive, _lift, _own_flag, _put_checks, _put_shadow_row, audit,
    clock, gapi)

TEST_ORG = f"{GOLIVE}/test-organization"
NAME = "Go Live Test Organization"


async def _mark(gapi, tenant="t1", confirm=NAME, **extra):
    return await gapi.call("POST", TEST_ORG, role="super_admin", username=OWNER["username"],
                           json={"tenantId": tenant, "confirmName": confirm}, **extra)


async def _clear(gapi, tenant="t1", **extra):
    return await gapi.call("DELETE", f"{TEST_ORG}?tenantId={tenant}", role="super_admin",
                           username=OWNER["username"], **extra)


@pytest.fixture
async def named(gapi):
    """t1 is ticked and called NAME; t2 is a ticked customer organization."""
    await seed_tenant(gapi.db, "t1", shadow=True, name=NAME)
    return gapi


def _events(audit, action):
    return [c for c in audit.await_args_list if c.args[0] == action]


async def _stored_mark(db):
    return await db[GOLIVE_TEST_ORG].find_one({"_id": TEST_ORG_DOC_ID})


def _read_fails(monkeypatch, collection):
    """The settings read of ``ao_settings.load`` raises for ``collection`` (tenants or autonomy_settings);
    every other collection is the real one."""
    real = ao_settings.raw

    class _Db:
        def __init__(self, db):
            self._db = db

        def __getattr__(self, name):
            if name == collection:
                return SimpleNamespace(find_one=AsyncMock(side_effect=RuntimeError("database is down")))
            return getattr(self._db, name)

    monkeypatch.setattr(ao_settings, "raw", lambda db: _Db(real(db)))


# ------------------------------------------------------------------ marking

async def test_marking_with_the_exact_name_stores_the_mark_and_audits_it(named, audit, clock):
    """protects=D-23; fails_when=the mark is missing, shaped differently, not trimmed-compared or not audited."""
    resp = await _mark(named, confirm=f"  {NAME}  ")
    assert resp.status_code == 201
    body = resp.json()["testOrganization"]
    assert body["id"] == "t1" and body["name"] == NAME and body["markedBy"]["username"] == OWNER["username"]
    assert body["markedAt"]
    docs = await named.db[GOLIVE_TEST_ORG].find({}).to_list(10)
    assert len(docs) == 1 and docs[0]["_id"] == TEST_ORG_DOC_ID and docs[0]["tenantId"] == "t1"
    events = _events(audit, "autonomous_ops.golive_test_org_marked")
    assert len(events) == 1
    assert events[0].args[1] == "platform-admin"
    assert events[0].kwargs["organization"] == "t1" and events[0].kwargs["actor"]["email"] == OWNER["username"]


async def test_a_wrong_name_is_refused_and_stores_nothing(named, audit):
    """protects=D-23 typed confirmation; fails_when=a different case, a partial name or an empty name marks."""
    for wrong in ("go live test organization", "Go Live Test", "", "   ", "Other"):
        assert (await _mark(named, confirm=wrong)).status_code == 422, wrong
    assert await named.db[GOLIVE_TEST_ORG].count_documents({}) == 0
    assert _events(audit, "autonomous_ops.golive_test_org_marked") == []


async def test_the_platform_organization_and_unticked_or_unknown_ones_cannot_be_marked(gapi, audit):
    """protects=PROH-86-14; fails_when=the platform organization, an unticked tenant or an unknown id is marked."""
    await seed_tenant(gapi.db, "platform-admin", name="Platform")
    await seed_tenant(gapi.db, "t3", ticked=False, name="Hidden")
    assert (await _mark(gapi, "platform-admin", "Platform")).status_code == 409
    assert (await _mark(gapi, "t3", "Hidden")).status_code == 404
    assert (await _mark(gapi, "nope", "Nope")).status_code == 404
    assert await gapi.db[GOLIVE_TEST_ORG].count_documents({}) == 0
    assert _events(audit, "autonomous_ops.golive_test_org_marked") == []


async def test_a_second_mark_is_refused_and_names_the_current_organization(named, audit):
    """protects=PROH-86-14 one at a time; fails_when=a second organization is marked or the sentence omits the name."""
    await seed_tenant(named.db, "t2", shadow=True, name="Second Org")
    assert (await _mark(named)).status_code == 201
    again = await _mark(named, "t2", "Second Org")
    assert again.status_code == 409 and NAME in again.json()["detail"]
    same = await _mark(named)
    assert same.status_code == 409
    docs = await named.db[GOLIVE_TEST_ORG].find({}).to_list(10)
    assert len(docs) == 1 and docs[0]["tenantId"] == "t1"
    assert len(_events(audit, "autonomous_ops.golive_test_org_marked")) == 1


async def test_two_marks_racing_for_the_single_slot_leave_one(mongo_db):
    """protects=PROH-86-14 by construction; fails_when=a second insert succeeds instead of raising AlreadyMarked."""
    await golive_test_org.mark(mongo_db, "t1", "One", OWNER, NOW)
    with pytest.raises(golive_test_org.AlreadyMarked) as raised:
        await golive_test_org.mark(mongo_db, "t2", "Two", OWNER, NOW)
    assert raised.value.current["tenantId"] == "t1" and raised.value.current["tenantName"] == "One"
    assert await mongo_db[GOLIVE_TEST_ORG].count_documents({}) == 1
    current = await golive_test_org.current(mongo_db)
    assert current["tenantId"] == "t1" and "_id" not in current


async def test_an_audit_failure_is_logged_and_never_undoes_the_mark(named, audit, caplog):
    """protects=D-23 audit; fails_when=a failing ledger turns a stored mark into an error or passes silently."""
    audit.side_effect = RuntimeError("ledger offline")
    with caplog.at_level(logging.ERROR):
        resp = await _mark(named)
    assert resp.status_code == 201
    assert await named.db[GOLIVE_TEST_ORG].count_documents({}) == 1
    assert any("test organization" in r.getMessage() and "ledger offline" in r.getMessage() for r in caplog.records)


# ------------------------------------------------------------------ clearing

async def test_clearing_works_only_while_the_organizations_shadow_flag_is_on(named, audit):
    """protects=PROH-86-14 / T-86-14-03; fails_when=the mark is cleared while the organization is out of shadow."""
    assert (await _mark(named)).status_code == 201
    await named.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
    refused = await _clear(named)
    assert refused.status_code == 409
    assert refused.json()["detail"] == f"Turn shadow mode back on for {NAME} first."
    assert await named.db[GOLIVE_TEST_ORG].count_documents({}) == 1
    assert _events(audit, "autonomous_ops.golive_test_org_cleared") == []

    await named.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": True}})
    done = await _clear(named)
    assert done.status_code == 200 and done.json()["testOrganization"] is None
    assert await named.db[GOLIVE_TEST_ORG].count_documents({}) == 0
    events = _events(audit, "autonomous_ops.golive_test_org_cleared")
    assert len(events) == 1 and events[0].args[1] == "platform-admin" and events[0].kwargs["organization"] == "t1"


async def test_clearing_an_organization_that_is_not_marked_changes_nothing(named, audit):
    """fails_when=naming another organization, or clearing with no mark, removes or reports the mark."""
    await seed_tenant(named.db, "t2", shadow=True, name="Second Org")
    assert (await _clear(named)).status_code == 404
    assert (await _mark(named)).status_code == 201
    assert (await _clear(named, "t2")).status_code == 404
    assert await named.db[GOLIVE_TEST_ORG].count_documents({}) == 1
    assert _events(audit, "autonomous_ops.golive_test_org_cleared") == []


async def test_clearing_is_refused_when_the_shadow_flag_cannot_be_read(named, audit, monkeypatch):
    """protects=PROH-86-14 / T-86-14-03 fail closed; fails_when=a failed read of the tenant or its settings reads
    as shadow on and the mark of a lifted organization is cleared."""
    for collection in ("tenants", "autonomy_settings"):
        assert (await _mark(named)).status_code == 201
        before = await _stored_mark(named.db)
        with monkeypatch.context() as patch:
            _read_fails(patch, collection)
            refused = await _clear(named)
        assert refused.status_code == 409, collection
        assert refused.json()["detail"] == f"Shadow mode for {NAME} couldn't be confirmed, so the test mark stays."
        assert await _stored_mark(named.db) == before, collection
        assert _events(audit, "autonomous_ops.golive_test_org_cleared") == []
        await named.db[GOLIVE_TEST_ORG].delete_many({})


async def test_clearing_is_refused_when_the_stored_shadow_flag_is_not_a_boolean(named, audit):
    """protects=T-86-14-03; fails_when=a stored "false" (not understood, read as the default) lets the clear through."""
    assert (await _mark(named)).status_code == 201
    before = await _stored_mark(named.db)
    await named.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": "false"}})
    refused = await _clear(named)
    assert refused.status_code == 409
    assert refused.json()["detail"] == f"Shadow mode for {NAME} couldn't be confirmed, so the test mark stays."
    assert await _stored_mark(named.db) == before
    assert _events(audit, "autonomous_ops.golive_test_org_cleared") == []


async def test_a_lift_that_lands_during_the_clear_puts_the_mark_back(named, audit, monkeypatch):
    """protects=PROH-86-14 race; fails_when=the shadow flag went off between the check and the delete and the
    mark stays removed, is put back changed, or the clear is audited."""
    assert (await _mark(named)).status_code == 201
    before = await _stored_mark(named.db)
    real_clear = golive_test_org.clear

    async def clear_then_lift(db, tenant_id):
        removed = await real_clear(db, tenant_id)
        await db.autonomy_settings.update_one({"tenantId": tenant_id}, {"$set": {"shadow": False}})
        return removed

    monkeypatch.setattr(golive_test_org, "clear", clear_then_lift)
    refused = await _clear(named)
    assert refused.status_code == 409
    assert refused.json()["detail"] == f"Turn shadow mode back on for {NAME} first."
    assert await _stored_mark(named.db) == before
    assert await _own_flag(named.db) is False
    assert _events(audit, "autonomous_ops.golive_test_org_cleared") == []


async def test_a_flag_that_cannot_be_read_after_the_clear_puts_the_mark_back(named, audit, monkeypatch):
    """protects=T-86-14-03; fails_when=a failing re-read after the delete leaves the mark removed or answers 503."""
    assert (await _mark(named)).status_code == 201
    before = await _stored_mark(named.db)
    real_load, calls = ao_settings.load, []

    async def load_once(db, tenant_id):
        calls.append(tenant_id)
        if len(calls) > 1:
            raise RuntimeError("database is down")
        return await real_load(db, tenant_id)

    monkeypatch.setattr(ao_settings, "load", load_once)
    refused = await _clear(named)
    assert len(calls) == 2
    assert refused.status_code == 409
    assert refused.json()["detail"] == f"Shadow mode for {NAME} couldn't be confirmed, so the test mark stays."
    assert await _stored_mark(named.db) == before
    assert _events(audit, "autonomous_ops.golive_test_org_cleared") == []


async def test_restoring_a_mark_keeps_it_identical_and_never_replaces_anothers(mongo_db, caplog):
    """protects=PROH-86-14 single slot; fails_when=a restored mark differs, or a mark made in between is replaced
    or restored silently."""
    await golive_test_org.mark(mongo_db, "t1", "One", OWNER, NOW)
    before = await _stored_mark(mongo_db)
    mark = await golive_test_org.current(mongo_db)
    assert await golive_test_org.clear(mongo_db, "t1") is True
    assert await golive_test_org.restore(mongo_db, mark) is True
    assert await _stored_mark(mongo_db) == before

    await golive_test_org.clear(mongo_db, "t1")
    await golive_test_org.mark(mongo_db, "t2", "Two", OWNER, NOW)
    with caplog.at_level(logging.ERROR):
        assert await golive_test_org.restore(mongo_db, mark) is False
    assert (await golive_test_org.current(mongo_db))["tenantId"] == "t2"
    assert await mongo_db[GOLIVE_TEST_ORG].count_documents({}) == 1
    assert any("test organization" in r.getMessage() for r in caplog.records)


# ------------------------------------------------------------------ the gate

async def test_the_test_organization_lifts_with_no_checks_and_no_records_others_do_not(named, audit, clock):
    """protects=PROH-86-04 exemption and its limit; fails_when=a customer organization skips the gate, or the
    test organization is still blocked, or the lift is not audited as a test-organization lift."""
    await seed_tenant(named.db, "t2", shadow=True, name="Second Org")
    assert (await _mark(named)).status_code == 201
    other = await named.call("PUT", f"{PLAT}/tenants/t2/shadow", role="super_admin", json={"shadow": False})
    assert other.status_code == 409
    assert other.json()["reasons"] == [{"code": "checks_missing", "recorded": 0}, {"code": "no_shadow_records"}]
    assert await _own_flag(named.db, "t2") is True

    audit.reset_mock()
    lifted = await _lift(named)
    assert lifted.status_code == 200 and await _own_flag(named.db) is False
    events = _events(audit, "autonomous_ops.shadow_lifted")
    assert len(events) == 1 and events[0].args[1] == "t1"
    assert events[0].kwargs["testOrganization"] is True and events[0].kwargs["checksRecorded"] == 0


async def test_the_exemption_skips_the_days_but_not_the_ordinary_lift_evidence_for_others(named, audit, clock):
    """fails_when=a normal lift is audited as a test-organization lift, or a short observation blocks the test one."""
    await seed_tenant(named.db, "t2", shadow=True, name="Second Org")
    await _put_checks(named.db, when=NOW - timedelta(days=1))
    await _put_shadow_row(named.db, "t1", NOW - timedelta(days=1))
    await _put_shadow_row(named.db, "t2", NOW - timedelta(days=9))
    assert (await _mark(named)).status_code == 201
    assert (await _lift(named)).status_code == 200                          # one day observed, still lifts
    plain = await named.call("PUT", f"{PLAT}/tenants/t2/shadow", role="super_admin", json={"shadow": False})
    assert plain.status_code == 200
    lifts = {c.args[1]: c.kwargs["testOrganization"] for c in _events(audit, "autonomous_ops.shadow_lifted")}
    assert lifts == {"t1": True, "t2": False}


async def test_after_the_mark_is_cleared_the_organization_is_gated_again(named, clock):
    """protects=PROH-86-04; fails_when=the exemption outlives the mark."""
    assert (await _mark(named)).status_code == 201
    assert (await _clear(named)).status_code == 200
    resp = await _lift(named)
    assert resp.status_code == 409 and resp.json()["reasons"][0]["code"] == "checks_missing"


async def test_an_unreadable_mark_exempts_nobody(named, monkeypatch, clock):
    """protects=T-86-14-04 fail closed; fails_when=a failed read of the mark lets the organization through."""
    assert (await _mark(named)).status_code == 201
    monkeypatch.setattr(golive_test_org, "current", AsyncMock(side_effect=RuntimeError("database is down")))
    resp = await _lift(named)
    assert resp.status_code == 409
    assert resp.json()["reasons"] == [{"code": "checks_missing", "recorded": 0}, {"code": "no_shadow_records"}]
    assert await _own_flag(named.db) is True
    overview = (await named.call("GET", GOLIVE, role="super_admin")).json()
    assert overview["testOrganization"] is None
    assert not any(o["testOrganization"] for o in overview["organizations"])


async def test_an_unreadable_observation_does_not_block_the_test_organization(named, monkeypatch, clock):
    """protects=D-23; fails_when=a failed shadow-records read blocks the exempt organization but not by design."""
    assert (await _mark(named)).status_code == 201
    monkeypatch.setattr(_golive(), "observation", AsyncMock(side_effect=RuntimeError("down")))
    assert await _golive().lift_blockers(named.db, "t1", NOW) == []
    assert await _golive().lift_blockers(named.db, "t2", NOW) == [{"code": "checks_missing", "recorded": 0},
                                                                  {"code": "unreadable"}]


async def test_a_test_organization_lift_is_undone_when_the_mark_vanishes_during_it(named, audit, clock, monkeypatch):
    """protects=PROH-86-14 race / T-86-14-03; fails_when=a clear that lands between the gate and the write leaves a
    lifted organization with no mark, or the undone lift is audited."""
    assert (await _mark(named)).status_code == 201
    audit.reset_mock()
    real_set = ao_settings.set_shadow

    async def write_then_unmark(db, tenant_id, shadow, *, actor):
        out = await real_set(db, tenant_id, shadow, actor=actor)
        if shadow is False:
            await db[GOLIVE_TEST_ORG].delete_many({})
        return out

    monkeypatch.setattr(ao_settings, "set_shadow", write_then_unmark)
    resp = await _lift(named)
    assert resp.status_code == 409
    body = resp.json()
    assert body["reasons"] == [{"code": "checks_missing", "recorded": 0}, {"code": "no_shadow_records"}]
    assert body["detail"] == _golive().blocker_sentence(body["reasons"])
    assert await _own_flag(named.db) is True
    assert _events(audit, "autonomous_ops.shadow_lifted") == []


async def test_a_lift_that_passed_the_full_gate_is_not_checked_again(named, audit, clock, monkeypatch):
    """protects=PROH-86-04; fails_when=an ordinary lift re-runs the gate or is undone by the test organization's
    mark changing, or a healthy test-organization lift or clear changes."""
    await seed_tenant(named.db, "t2", shadow=True, name="Second Org")
    await _put_checks(named.db, when=NOW - timedelta(days=9))
    await _put_shadow_row(named.db, "t2", NOW - timedelta(days=9))
    assert (await _mark(named)).status_code == 201
    real_set, real_gate, gate_calls = ao_settings.set_shadow, _golive().lift_decision, []

    async def counted_gate(db, tenant_id, now):
        gate_calls.append(tenant_id)
        return await real_gate(db, tenant_id, now)

    async def write_then_unmark(db, tenant_id, shadow, *, actor):
        out = await real_set(db, tenant_id, shadow, actor=actor)
        await db[GOLIVE_TEST_ORG].delete_many({})
        return out

    monkeypatch.setattr(_golive(), "lift_decision", counted_gate)
    with monkeypatch.context() as patch:
        patch.setattr(ao_settings, "set_shadow", write_then_unmark)
        plain = await named.call("PUT", f"{PLAT}/tenants/t2/shadow", role="super_admin", json={"shadow": False})
    assert plain.status_code == 200 and await _own_flag(named.db, "t2") is False
    assert gate_calls == ["t2"]
    assert len(_events(audit, "autonomous_ops.shadow_lifted")) == 1

    await golive_test_org.mark(named.db, "t1", NAME, OWNER, NOW)
    assert (await _lift(named)).status_code == 200 and await _own_flag(named.db) is False
    await named.call("PUT", SHADOW, role="super_admin", json={"shadow": True})
    assert (await _clear(named)).status_code == 200
    assert await named.db[GOLIVE_TEST_ORG].count_documents({}) == 0
    assert len(_events(audit, "autonomous_ops.golive_test_org_cleared")) == 1


# ------------------------------------------------------------------ the overview

async def test_the_overview_shows_the_mark_and_flags_only_that_row(named, clock):
    """protects=D-23 card data; fails_when=testOrganization is missing, on the wrong row, or canLift ignores the flag."""
    await seed_tenant(named.db, "t2", shadow=True, name="Second Org")
    none = (await named.call("GET", GOLIVE, role="super_admin")).json()
    assert none["testOrganization"] is None and all(o["testOrganization"] is False for o in none["organizations"])

    assert (await _mark(named)).status_code == 201
    body = (await named.call("GET", GOLIVE, role="super_admin")).json()
    top = body["testOrganization"]
    assert top["id"] == "t1" and top["name"] == NAME and top["markedBy"]["username"] == OWNER["username"]
    assert top["markedAt"]
    rows = {o["id"]: o for o in body["organizations"]}
    assert rows["t1"]["testOrganization"] is True and rows["t2"]["testOrganization"] is False
    assert rows["t1"]["canLift"] is True and rows["t1"]["reasons"] == []
    assert rows["t2"]["canLift"] is False

    await named.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
    off = {o["id"]: o for o in (await named.call("GET", GOLIVE, role="super_admin")).json()["organizations"]}
    assert off["t1"]["canLift"] is False and off["t1"]["testOrganization"] is True


# ------------------------------------------------------------------ who may call

async def test_only_the_platform_owner_in_a_session_can_mark_or_clear(named, audit):
    """protects=T-86-14-01; fails_when=Platform Support, a tenant admin or an API key marks or clears."""
    refused = [("platform_support", {}), ("platform_billing", {}), ("tenant_admin", {}), ("security_analyst", {}),
               ("super_admin", {"auth": "api_key", "scopes": ALL_SCOPES})]
    for role, extra in refused:
        post = await named.call("POST", TEST_ORG, role=role, json={"tenantId": "t1", "confirmName": NAME}, **extra)
        assert post.status_code == 403, (role, extra)
        assert (await named.call("DELETE", f"{TEST_ORG}?tenantId=t1", role=role, **extra)).status_code == 403, (role, extra)
    assert await named.db[GOLIVE_TEST_ORG].count_documents({}) == 0
    assert (await _mark(named)).status_code == 201
    for role, extra in refused:
        assert (await named.call("DELETE", f"{TEST_ORG}?tenantId=t1", role=role, **extra)).status_code == 403, (role, extra)
    assert await named.db[GOLIVE_TEST_ORG].count_documents({}) == 1


def test_the_test_organization_module_never_names_the_evidence_collection():
    """protects=86-07 append-only rule; fails_when=the module names the evidence collection or its constant."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "autonomous_ops", "reporting", "golive_test_org.py")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    assert "autonomy_golive_checks" not in source and "GOLIVE_CHECKS" not in source
