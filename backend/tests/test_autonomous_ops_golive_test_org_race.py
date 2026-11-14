"""The window between the lift gate's read of the test-organization mark and the write (Phase 86, plan 86-14,
T-86-14-03, D-23).

Real MongoDB through the throwaway database of tests/_mongo_test_db.py; the routers are mounted through the
Phase 81 HTTP harness (the 86-07 and 86-14 fixtures are reused). The clear of the mark lands at one exact
point: right after the FIRST read of the mark in the lift request, which is the read the gate decides on.

Value: protects=PROH-86-04 / PROH-86-14 / T-86-14-03: one clear and one lift of the go-live test organization
end marked-and-lifted, unmarked-and-in-shadow or marked-and-in-shadow, never lifted-and-unmarked; fails_when=a
clear that lands after the gate has passed the test organization by its exemption (and before the post-write
check) leaves it lifted with no mark, the undone lift is audited, a healthy exemption lift changes, or a lift
of a customer organization is undone or audited as an exemption; no_claim=real parallel requests (the ordering
is forced at one point) and the Going live card.
"""
import os
import sys
from datetime import timedelta
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops.reporting import GOLIVE_TEST_ORG, golive_test_org
from tests._autonomous_ops_http import _env, api  # noqa: F401  (fixtures)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant
from tests.test_autonomous_ops_golive import (  # noqa: F401  (fixtures and helpers of the 86-07 suite)
    NOW, OWNER, PLAT, _golive, _lift, _own_flag, _put_checks, _put_shadow_row, audit, clock, gapi)
from tests.test_autonomous_ops_golive_test_org import NAME, _clear, _events, _mark, named  # noqa: F401

NOT_MET = [{"code": "checks_missing", "recorded": 0}, {"code": "no_shadow_records"}]


async def _noop(db):
    """The clear that never comes: the mark stays."""


def _after_first_mark_read(monkeypatch, then):
    """The mark read runs as usual; right after its FIRST call (the gate's read) ``then(db)`` is awaited once,
    and the gate still gets what it read. Every later read is the real one."""
    real, fired = golive_test_org.current, []

    async def current(db):
        mark = await real(db)
        if not fired:
            fired.append(True)
            await then(db)
        return mark

    monkeypatch.setattr(golive_test_org, "current", current)


async def test_a_clear_that_lands_right_after_the_gates_mark_read_does_not_leave_the_lift_unmarked(
        named, audit, clock, monkeypatch):
    """protects=T-86-14-03; fails_when=the mark is removed after the gate passed the organization by its exemption
    and the lift stays written: lifted with no mark, audited as a lift with no exemption and no checks."""
    assert (await _mark(named)).status_code == 201
    audit.reset_mock()
    _after_first_mark_read(monkeypatch, lambda db: db[GOLIVE_TEST_ORG].delete_many({}))
    resp = await _lift(named)
    assert resp.status_code == 409
    body = resp.json()
    assert body["reasons"] == NOT_MET and body["detail"] == _golive().blocker_sentence(NOT_MET)
    assert await _own_flag(named.db) is True
    assert await named.db[GOLIVE_TEST_ORG].count_documents({}) == 0
    assert _events(audit, "autonomous_ops.shadow_lifted") == []


async def test_a_real_clear_between_the_gates_read_and_the_write_ends_unmarked_and_in_shadow(
        named, audit, clock, monkeypatch):
    """protects=T-86-14-03; fails_when=the clear route (which sees shadow mode still on, so it passes) and the
    lift both succeed and the organization is lifted with no mark."""
    assert (await _mark(named)).status_code == 201
    audit.reset_mock()
    cleared = []

    async def clear_route(db):
        cleared.append(await _clear(named))

    _after_first_mark_read(monkeypatch, clear_route)
    resp = await _lift(named)
    assert len(cleared) == 1 and cleared[0].status_code == 200
    assert resp.status_code == 409 and resp.json()["reasons"] == NOT_MET
    assert await _own_flag(named.db) is True
    assert await named.db[GOLIVE_TEST_ORG].count_documents({}) == 0
    assert _events(audit, "autonomous_ops.shadow_lifted") == []
    assert len(_events(audit, "autonomous_ops.golive_test_org_cleared")) == 1


async def test_a_mark_that_cannot_be_read_after_the_gate_undoes_the_lift(named, audit, clock, monkeypatch):
    """protects=T-86-14-03 fail closed; fails_when=a failing mark read after the gate's own read leaves the
    organization lifted, or audits the undone lift."""
    assert (await _mark(named)).status_code == 201
    audit.reset_mock()
    real, calls = golive_test_org.current, []

    async def current(db):
        calls.append(True)
        if len(calls) > 1:
            raise RuntimeError("database is down")
        return await real(db)

    monkeypatch.setattr(golive_test_org, "current", current)
    resp = await _lift(named)
    assert resp.status_code == 409 and resp.json()["reasons"] == NOT_MET
    assert await _own_flag(named.db) is True
    assert _events(audit, "autonomous_ops.shadow_lifted") == []


async def test_a_lift_by_exemption_whose_mark_stays_still_succeeds_and_is_audited_once(
        named, audit, clock, monkeypatch):
    """protects=D-23; fails_when=a healthy lift of the test organization is refused, is undone, leaves the mark
    changed, or is not audited once with the exemption."""
    assert (await _mark(named)).status_code == 201
    before = await named.db[GOLIVE_TEST_ORG].find_one({})
    audit.reset_mock()
    _after_first_mark_read(monkeypatch, _noop)
    resp = await _lift(named)
    assert resp.status_code == 200 and await _own_flag(named.db) is False
    assert await named.db[GOLIVE_TEST_ORG].find_one({}) == before
    events = _events(audit, "autonomous_ops.shadow_lifted")
    assert len(events) == 1 and events[0].args[1] == "t1"
    assert events[0].kwargs["testOrganization"] is True and events[0].kwargs["checksRecorded"] == 0


async def test_a_customer_organization_that_passed_the_full_gate_is_not_undone_by_a_clear(
        named, audit, clock, monkeypatch):
    """protects=PROH-86-04; fails_when=a customer organization lifted on all five checks and seven days is undone,
    or audited as the test organization, because the mark of another organization vanished."""
    await seed_tenant(named.db, "t2", shadow=True, name="Second Org")
    await _put_checks(named.db, when=NOW - timedelta(days=9))
    await _put_shadow_row(named.db, "t2", NOW - timedelta(days=9))
    assert (await _mark(named)).status_code == 201
    audit.reset_mock()
    _after_first_mark_read(monkeypatch, lambda db: db[GOLIVE_TEST_ORG].delete_many({}))
    resp = await named.call("PUT", f"{PLAT}/tenants/t2/shadow", role="super_admin", json={"shadow": False})
    assert resp.status_code == 200 and await _own_flag(named.db, "t2") is False
    events = _events(audit, "autonomous_ops.shadow_lifted")
    assert len(events) == 1 and events[0].args[1] == "t2"
    assert events[0].kwargs["testOrganization"] is False and events[0].kwargs["checksRecorded"] == 5


# ------------------------------------------------------------------ the decision the gate hands the route

async def test_the_gate_reports_the_exemption_from_the_one_mark_read_it_decided_on(mongo_db, monkeypatch):
    """protects=T-86-14-03; fails_when=the exemption is missing from the decision, names another organization,
    outlives an unreadable mark, or the decision reads the mark twice (two reads can disagree)."""
    golive = _golive()
    await golive_test_org.mark(mongo_db, "t1", NAME, OWNER, NOW)
    assert await golive.lift_decision(mongo_db, "t1", NOW) == ([], True)
    assert await golive.lift_decision(mongo_db, "t2", NOW) == (NOT_MET, False)
    assert await golive.lift_blockers(mongo_db, "t1", NOW) == []
    assert await golive.lift_blockers(mongo_db, "t2", NOW) == NOT_MET

    real, reads = golive_test_org.current, []

    async def counted(db):
        reads.append(True)
        return await real(db)

    monkeypatch.setattr(golive_test_org, "current", counted)
    await golive.lift_decision(mongo_db, "t1", NOW)
    assert len(reads) == 1

    monkeypatch.setattr(golive_test_org, "current", AsyncMock(side_effect=RuntimeError("database is down")))
    assert await golive.lift_decision(mongo_db, "t1", NOW) == (NOT_MET, False)
    monkeypatch.setattr(golive_test_org, "current", real)
    await golive_test_org.clear(mongo_db, "t1")
    assert await golive.lift_decision(mongo_db, "t1", NOW) == (NOT_MET, False)


async def test_the_exemption_is_reported_for_the_marked_organization_even_when_the_full_gate_would_pass(mongo_db):
    """protects=T-86-14-03; fails_when=an organization the mark names is reported as not exempt only because it
    also has the checks and the days, or a customer organization with the full evidence is reported as exempt."""
    golive = _golive()
    await _put_checks(mongo_db, when=NOW - timedelta(days=9))
    await _put_shadow_row(mongo_db, "t1", NOW - timedelta(days=9))
    await _put_shadow_row(mongo_db, "t2", NOW - timedelta(days=9))
    await golive_test_org.mark(mongo_db, "t1", NAME, OWNER, NOW)
    assert await golive.lift_decision(mongo_db, "t1", NOW) == ([], True)
    assert await golive.lift_decision(mongo_db, "t2", NOW) == ([], False)
