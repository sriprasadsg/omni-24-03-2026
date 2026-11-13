"""Go-live checks and the shadow lift gate (Phase 86, plan 86-07, GATE-09, D-14..D-16, D-20, D-21).

Real MongoDB through the throwaway database of tests/_mongo_test_db.py; the platform router is mounted
through the Phase 81 HTTP harness with the identity replaced by a dependency override.

Value: protects=PROH-86-04 / PROH-86-07: no organization leaves shadow mode before five go-live checks are
recorded and seven whole days of shadow records exist, the gate is enforced by the route itself, a lift and a
restore are audited, and the evidence is never updated or deleted; fails_when=a lift passes with a missing
check, a short or unreadable observation, a restore is gated, or evidence changes after it is recorded;
no_claim=the Going live card (86-12) and a real browser session.
"""
import ast
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_ledger
from tests._autonomous_ops_http import _env, api  # noqa: F401  (fixtures)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant
from tests.test_autonomous_ops_structural import _backend_sources

PLAT = "/api/platform/autonomous-ops"
SHADOW = f"{PLAT}/tenants/t1/shadow"
CHECK_IDS = ("firewall_round_trip", "reboot_gate", "watchdog_stop_start", "alert_delivery", "live_stop_drill")
NOW = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
OWNER = {"username": "root@example.test", "display": "Root Owner", "tier": "platform"}


def _golive():
    from autonomous_ops.reporting import golive
    return golive


@pytest.fixture(autouse=True)
def audit(monkeypatch):
    """Every test sees the audit ledger as a recording stub: nothing reaches a real ledger."""
    stub = AsyncMock(return_value={})
    monkeypatch.setattr(audit_ledger, "event", stub)
    return stub


@pytest.fixture
def clock(monkeypatch):
    """Pins the module clock seam the lift gate reads."""
    monkeypatch.setattr(_golive(), "clock", lambda: NOW)
    return NOW


async def _put_checks(db, ids=CHECK_IDS, *, when=None):
    """Stored check records, written straight to the collection (the shape D-14 fixes)."""
    for check_id in ids:
        await db.autonomy_golive_checks.insert_one({
            "id": f"GL-{uuid.uuid4().hex}", "checkId": check_id, "note": "Seeded for the test",
            "recordedBy": {"username": OWNER["username"], "display": OWNER["display"]},
            "recordedAt": when or datetime.now(timezone.utc)})


async def _put_shadow_row(db, tenant, created, **extra):
    await db.autonomy_actions.insert_one({"id": f"AO-{uuid.uuid4().hex}", "tenantId": tenant, "kind": "action",
                                          "state": "shadow", "createdAt": created, **extra})


async def _own_flag(db, tenant="t1"):
    return (await db.autonomy_settings.find_one({"tenantId": tenant}))["shadow"]


async def _lift(api, **kwargs):
    return await api.call("PUT", SHADOW, role="super_admin", username=OWNER["username"],
                          json={"shadow": False}, **kwargs)


# ------------------------------------------------------------------ the gate in PUT /tenants/{id}/shadow

async def test_lift_is_refused_with_nothing_recorded(api, audit):
    """protects=T-86-15; fails_when=a lift passes with no checks and no shadow records, or changes the flag."""
    resp = await _lift(api)
    assert resp.status_code == 409
    body = resp.json()
    assert body["reasons"] == [{"code": "checks_missing", "recorded": 0}, {"code": "no_shadow_records"}]
    assert isinstance(body["detail"], str) and "Record all 5 go-live checks first (0 of 5 recorded)." in body["detail"]
    assert "No shadow records yet. Needs 7 days." in body["detail"]
    assert await _own_flag(api.db) is True
    audit.assert_not_awaited()


async def test_four_distinct_checks_are_not_five_even_when_one_is_recorded_twice(api):
    """protects=D-15; fails_when=a repeated record counts as a fifth check."""
    await _put_checks(api.db, CHECK_IDS[:4] + ("reboot_gate",))
    await _put_shadow_row(api.db, "t1", datetime.now(timezone.utc) - timedelta(days=9))
    resp = await _lift(api)
    assert resp.status_code == 409
    assert resp.json()["reasons"] == [{"code": "checks_missing", "recorded": 4}]
    assert await _own_flag(api.db) is True


async def test_seven_days_to_the_second_and_one_second_short(api, audit, clock):
    """protects=D-16 / D-20; fails_when=the boundary moves: 6 days 23:59:59 passes or exactly 7 days is refused."""
    await _put_checks(api.db, when=NOW - timedelta(days=1))
    await _put_shadow_row(api.db, "t1", NOW - timedelta(days=7) + timedelta(seconds=1))
    short = await _lift(api)
    assert short.status_code == 409
    assert short.json()["reasons"] == [{"code": "days_short", "days": 6}]
    assert "Needs 7 days of shadow records. 6 days so far." in short.json()["detail"]
    assert await _own_flag(api.db) is True
    audit.assert_not_awaited()

    await api.db.autonomy_actions.delete_many({"tenantId": "t1"})
    await _put_shadow_row(api.db, "t1", NOW - timedelta(days=7))
    await _put_shadow_row(api.db, "t1", NOW - timedelta(days=2))
    done = await _lift(api)
    assert done.status_code == 200
    assert await _own_flag(api.db) is False
    audit.assert_awaited_once()
    args, kwargs = audit.await_args
    assert args == ("autonomous_ops.shadow_lifted", "t1")
    assert kwargs["organization"] == "t1" and kwargs["shadow"] is False
    assert kwargs["daysObserved"] == 7 and kwargs["wouldHaveDone"] == 2 and kwargs["checksRecorded"] == 5
    assert kwargs["actor"]["email"] == OWNER["username"] and kwargs["actor"]["role"] == "super_admin"


async def test_an_unreadable_observation_fails_closed(api, monkeypatch, clock):
    """protects=D-15 fail closed; fails_when=a read error lets the lift through."""
    await _put_checks(api.db)
    await _put_shadow_row(api.db, "t1", NOW - timedelta(days=30))
    monkeypatch.setattr(_golive(), "observation", AsyncMock(side_effect=RuntimeError("database is down")))
    resp = await _lift(api)
    assert resp.status_code == 409
    assert resp.json()["reasons"] == [{"code": "unreadable"}]
    assert "couldn't be read" in resp.json()["detail"]
    assert await _own_flag(api.db) is True


async def test_restore_is_never_gated_and_lifting_a_lifted_organization_skips_the_gate(api, audit, monkeypatch):
    """protects=D-15 / D-21; fails_when=turning shadow back on is refused, or a no-op lift consults the gate."""
    await api.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
    gate = AsyncMock(side_effect=AssertionError("the gate must not run"))
    monkeypatch.setattr(_golive(), "lift_blockers", gate)
    again = await _lift(api)
    assert again.status_code == 200 and await _own_flag(api.db) is False
    gate.assert_not_awaited()

    restored = await api.call("PUT", SHADOW, role="super_admin", username=OWNER["username"], json={"shadow": True})
    assert restored.status_code == 200 and await _own_flag(api.db) is True
    gate.assert_not_awaited()
    restored_calls = [c for c in audit.await_args_list if c.args[0] == "autonomous_ops.shadow_restored"]
    assert len(restored_calls) == 1
    assert restored_calls[0].args[1] == "t1" and restored_calls[0].kwargs["shadow"] is True
    assert "daysObserved" not in restored_calls[0].kwargs


async def test_the_deployment_wide_switch_does_not_change_the_gate(api, monkeypatch, clock):
    """protects=UI-SPEC R10; fails_when=the master switch blocks an organization's own lift that is otherwise allowed."""
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "true")
    refused = await _lift(api)
    assert refused.status_code == 409
    assert refused.json()["reasons"][0]["code"] == "checks_missing"
    await _put_checks(api.db)
    await _put_shadow_row(api.db, "t1", NOW - timedelta(days=8))
    assert (await _lift(api)).status_code == 200
    assert await _own_flag(api.db) is False


async def test_a_lift_and_a_restore_add_no_row_to_the_activity_list(api, clock):
    """protects=D-21; fails_when=a control row appears for a lift or a restore."""
    await _put_checks(api.db)
    await _put_shadow_row(api.db, "t1", NOW - timedelta(days=8))
    assert (await _lift(api)).status_code == 200
    assert (await api.call("PUT", SHADOW, role="super_admin", json={"shadow": True})).status_code == 200
    assert await api.db.autonomy_actions.count_documents({"tenantId": "t1", "kind": "control"}) == 0
    assert await api.db.autonomy_actions.count_documents({"tenantId": "t1"}) == 1


async def test_the_audit_failure_does_not_undo_a_lift(api, audit, clock):
    """protects=D-21; fails_when=a failing audit write turns a completed lift into an error."""
    await _put_checks(api.db)
    await _put_shadow_row(api.db, "t1", NOW - timedelta(days=8))
    audit.side_effect = RuntimeError("ledger offline")
    assert (await _lift(api)).status_code == 200
    assert await _own_flag(api.db) is False


# ------------------------------------------------------------------ records, observation and sentences

async def test_recording_a_check_again_keeps_both_and_the_latest_wins(mongo_db):
    """protects=PROH-86-07; fails_when=a second record replaces the first or the older one is returned."""
    golive = _golive()
    first = await golive.record_check(mongo_db, "reboot_gate", "  First reboot test passed  ", OWNER, NOW)
    second = await golive.record_check(mongo_db, "reboot_gate", "Second reboot test passed", OWNER,
                                       NOW + timedelta(hours=1))
    assert first["id"].startswith("GL-") and first["note"] == "First reboot test passed"
    assert first["recordedBy"] == {"username": OWNER["username"], "display": OWNER["display"]}
    assert "_id" not in first and first["id"] != second["id"]
    assert await mongo_db.autonomy_golive_checks.count_documents({"checkId": "reboot_gate"}) == 2
    latest = await golive.latest_checks(mongo_db)
    assert [item["id"] for item in latest] == list(CHECK_IDS)
    reboot = next(item for item in latest if item["id"] == "reboot_gate")
    assert reboot["recorded"] is True and reboot["note"] == "Second reboot test passed"
    never = next(item for item in latest if item["id"] == "alert_delivery")
    assert never["recorded"] is False and never["recordedAt"] is None and never["note"] is None


async def test_record_check_validates_its_input(mongo_db):
    """protects=T-86-18; fails_when=an unknown check id or an out-of-range note is stored."""
    golive = _golive()
    for check_id, note in (("other", "A long enough note"), ("reboot_gate", "too short"),
                           ("reboot_gate", "   padded    "), ("reboot_gate", "x" * 501)):
        with pytest.raises(ValueError):
            await golive.record_check(mongo_db, check_id, note, OWNER, NOW)
    assert await mongo_db.autonomy_golive_checks.count_documents({}) == 0
    assert (await golive.record_check(mongo_db, "reboot_gate", "x" * 500, OWNER, NOW))["note"] == "x" * 500


async def test_observation_counts_whole_days_from_the_first_shadow_record(mongo_db):
    """protects=D-16; fails_when=the days are rounded, counted from the wrong row or include other states."""
    golive = _golive()
    empty = await golive.observation(mongo_db, "t1", NOW)
    assert empty["daysObserved"] is None and empty["wouldHaveDone"] == 0 and empty["first"] is None
    await _put_shadow_row(mongo_db, "t1", NOW - timedelta(days=6, hours=23))
    await _put_shadow_row(mongo_db, "t1", NOW - timedelta(days=1))
    await _put_shadow_row(mongo_db, "t2", NOW - timedelta(days=40))
    await mongo_db.autonomy_actions.insert_one({"id": "AO-x", "tenantId": "t1", "kind": "action", "state": "executed",
                                                "createdAt": NOW - timedelta(days=50)})
    obs = await golive.observation(mongo_db, "t1", NOW)
    assert obs["daysObserved"] == 6 and obs["wouldHaveDone"] == 2
    assert (await golive.observation(mongo_db, "t1", NOW + timedelta(hours=1)))["daysObserved"] == 7


def test_the_sentences_read_plainly():
    """protects=UI-SPEC copy; fails_when=a reason has no sentence or the singular day is wrong."""
    golive = _golive()
    assert golive.blocker_sentence([{"code": "days_short", "days": 1}]) == "Needs 7 days of shadow records. 1 day so far."
    assert golive.blocker_sentence([{"code": "days_short", "days": 0}]) == "Needs 7 days of shadow records. 0 days so far."
    assert golive.blocker_sentence([{"code": "unreadable"}]) == "Shadow records couldn't be read, so lifting is blocked."
    both = golive.blocker_sentence([{"code": "checks_missing", "recorded": 3}, {"code": "no_shadow_records"}])
    assert both == "Record all 5 go-live checks first (3 of 5 recorded). No shadow records yet. Needs 7 days."


def test_the_evidence_collection_is_protected_from_retention():
    """protects=T-86-16; fails_when=a retention path may delete the evidence."""
    from autonomous_ops import PROTECTED_COLLECTIONS
    assert "autonomy_golive_checks" in PROTECTED_COLLECTIONS


# ------------------------------------------------------------------ the platform routes

GOLIVE = f"{PLAT}/golive"
ALL_SCOPES = ["view:autonomous_ops", "manage:autonomous_ops", "control:autonomous_ops",
              "control:platform_autonomous_ops"]


@pytest.fixture
async def gapi(api, monkeypatch):
    """The Phase 81 harness with the go-live router mounted beside the platform router."""
    import autonomous_ops_golive_endpoints as golive_endpoints
    monkeypatch.setattr(golive_endpoints, "get_database", lambda: api.db)
    api.app.include_router(golive_endpoints.router)
    return api


async def test_the_overview_lists_the_checks_and_every_ticked_organization(gapi, clock):
    """protects=D-14 / D-16 card data; fails_when=a check or an organization is missing, the order is wrong,
    the platform organization or an unticked tenant is listed, or a lift is offered too early."""
    await seed_tenant(gapi.db, "t0", name="Alpha")
    await seed_tenant(gapi.db, "t3", ticked=False, name="Hidden")
    await seed_tenant(gapi.db, "platform-admin", name="Platform")
    await _put_checks(gapi.db, CHECK_IDS[:2], when=NOW - timedelta(days=1))
    await _put_shadow_row(gapi.db, "t1", NOW - timedelta(days=8))
    early = (await gapi.call("GET", GOLIVE, role="super_admin")).json()
    assert [c["id"] for c in early["checks"]] == list(CHECK_IDS) and early["recordedCount"] == 2
    assert [o["id"] for o in early["organizations"]] == ["t0", "t1", "t2"]          # sorted by name, Alpha first
    assert early["masterShadow"] is False and not any(o["canLift"] for o in early["organizations"])
    t1 = early["organizations"][1]
    assert t1["daysObserved"] == 8 and t1["wouldHaveDone"] == 1 and t1["shadow"] is True and t1["name"] == "T1"
    assert t1["reasons"] == [{"code": "checks_missing", "recorded": 2}]

    await _put_checks(gapi.db, CHECK_IDS[2:], when=NOW)
    ready = {o["id"]: o for o in (await gapi.call("GET", GOLIVE, role="super_admin")).json()["organizations"]}
    assert ready["t1"]["canLift"] is True and ready["t1"]["reasons"] == []
    assert ready["t2"]["canLift"] is False and ready["t2"]["reasons"] == [{"code": "no_shadow_records"}]
    assert ready["t2"]["daysObserved"] is None and ready["t2"]["wouldHaveDone"] == 0


async def test_an_organization_whose_records_cannot_be_read_cannot_be_lifted(gapi, monkeypatch, clock):
    """protects=D-15 fail closed on the card; fails_when=a read error shows a day count or offers a lift."""
    await _put_checks(gapi.db)
    monkeypatch.setattr(_golive(), "observation", AsyncMock(side_effect=RuntimeError("down")))
    body = (await gapi.call("GET", GOLIVE, role="super_admin")).json()
    for org in body["organizations"]:
        assert org["daysObserved"] is None and org["canLift"] is False and org["reasons"] == [{"code": "unreadable"}]


async def test_recording_a_check_stores_it_and_audits_it(gapi, audit):
    """protects=D-14 / T-86-16; fails_when=the record is missing, shaped differently or not audited."""
    note = "Test alert reached the channel at 14:02"
    resp = await gapi.call("POST", f"{GOLIVE}/checks/alert_delivery", role="super_admin",
                           username=OWNER["username"], json={"note": f"  {note}  "})
    assert resp.status_code == 201
    body = resp.json()
    assert body["checkId"] == "alert_delivery" and body["note"] == note and body["id"].startswith("GL-")
    assert body["recordedBy"]["username"] == OWNER["username"] and body["recordedAt"]
    stored = await gapi.db.autonomy_golive_checks.find_one({"id": body["id"]})
    assert stored["checkId"] == "alert_delivery" and stored["note"] == note
    audit.assert_awaited_once()
    args, kwargs = audit.await_args
    assert args == ("autonomous_ops.golive_check_recorded", "platform-admin")
    assert kwargs["checkId"] == "alert_delivery" and kwargs["note"] == note
    again = await gapi.call("POST", f"{GOLIVE}/checks/alert_delivery", role="super_admin",
                            json={"note": "Second delivery test, also fine"})
    assert again.status_code == 201
    assert await gapi.db.autonomy_golive_checks.count_documents({"checkId": "alert_delivery"}) == 2
    overview = (await gapi.call("GET", GOLIVE, role="super_admin")).json()
    assert next(c for c in overview["checks"] if c["id"] == "alert_delivery")["note"] == "Second delivery test, also fine"


async def test_a_bad_check_id_or_note_is_refused(gapi, audit):
    """protects=T-86-18; fails_when=an unknown id, a short, padded-short or overlong note is stored."""
    path = f"{GOLIVE}/checks/reboot_gate"
    assert (await gapi.call("POST", f"{GOLIVE}/checks/other", role="super_admin",
                            json={"note": "A long enough note"})).status_code == 422
    for note in ("123456789", "   123456789   ", "x" * 501, "", None):
        assert (await gapi.call("POST", path, role="super_admin", json={"note": note})).status_code == 422, note
    assert (await gapi.call("POST", path, role="super_admin", json={})).status_code == 422
    assert (await gapi.call("POST", path, role="super_admin", json={"note": "x" * 500})).status_code == 201
    assert await gapi.db.autonomy_golive_checks.count_documents({}) == 1
    audit.assert_awaited_once()


async def test_only_the_platform_owner_in_a_session_reaches_the_golive_routes(gapi):
    """protects=T-86-17; fails_when=Platform Support, a tenant admin or an API key reads or records."""
    note = {"note": "A long enough note"}
    refused = [("platform_support", {}), ("platform_billing", {}), ("tenant_admin", {}), ("security_analyst", {}),
               ("super_admin", {"auth": "api_key", "scopes": ALL_SCOPES})]
    for role, extra in refused:
        assert (await gapi.call("GET", GOLIVE, role=role, **extra)).status_code == 403, (role, extra)
        assert (await gapi.call("POST", f"{GOLIVE}/checks/reboot_gate", role=role, json=note, **extra)
               ).status_code == 403, (role, extra)
    assert await gapi.db.autonomy_golive_checks.count_documents({}) == 0
    assert (await gapi.call("GET", GOLIVE, role="super_admin")).status_code == 200


# ------------------------------------------------------------------ structural: append-only evidence

COLLECTION = "autonomy_golive_checks"
CONSTANT = "GOLIVE_CHECKS"
GOLIVE_PATH = "autonomous_ops/reporting/golive.py"
ALLOWED_NAMING = frozenset({GOLIVE_PATH, "autonomous_ops/reporting/__init__.py", "autonomous_ops/__init__.py",
                            "migrations/035_activity_reporting.py"})
MUTATORS = frozenset({"update_one", "update_many", "replace_one", "delete_one", "delete_many",
                      "find_one_and_update", "find_one_and_replace", "find_one_and_delete", "bulk_write",
                      "drop", "rename"})


def _tree(source):
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _docstrings(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def names_the_collection(source):
    """True when code (not a comment or a docstring) names the collection or its constant."""
    if COLLECTION not in source and CONSTANT not in source:
        return False
    tree = _tree(source)
    if tree is None:
        return True                                   # a file that does not parse is scanned textually
    skip = _docstrings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in skip and COLLECTION in node.value:
                return True
        elif isinstance(node, ast.Attribute) and node.attr in (COLLECTION, CONSTANT):
            return True
        elif isinstance(node, ast.Name) and node.id == CONSTANT:
            return True
        elif isinstance(node, (ast.Import, ast.ImportFrom)) and any(
                CONSTANT in (a.name, a.asname) for a in node.names):
            return True
    return False


def uses_the_accessor(source):
    """True when code reaches golive's _checks accessor."""
    if "_checks" not in source:
        return False
    tree = _tree(source)
    if tree is None:
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "_checks":
            owner = node.value
            if (isinstance(owner, ast.Name) and owner.id == "golive") or (
                    isinstance(owner, ast.Attribute) and owner.attr == "golive"):
                return True
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == "golive" and any(
                a.name == "_checks" for a in node.names):
            return True
    return False


def naming_rule(path, source):
    problems = []
    if path not in ALLOWED_NAMING and names_the_collection(source):
        problems.append("names the go-live collection")
    if path != GOLIVE_PATH and uses_the_accessor(source):
        problems.append("uses the go-live accessor")
    return problems


def mutation_rule(path, source):
    """Methods called by a module of the allowed set that change or remove stored documents."""
    if path not in ALLOWED_NAMING:
        return []
    tree = _tree(source)
    if tree is None:
        return ["does not parse"]
    return sorted({n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute) and n.func.attr in MUTATORS})


@pytest.fixture(scope="module")
def backend_sources():
    found = dict(_backend_sources())
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), GOLIVE_PATH),
              encoding="utf-8") as handle:
        found[GOLIVE_PATH] = handle.read()            # read from disk: it may not be tracked yet
    assert len(found) > 200 and "autonomous_ops/reporting/__init__.py" in found and "autonomous_ops/__init__.py" in found
    return found


def test_only_the_allowed_modules_name_the_evidence_collection(backend_sources):
    """protects=PROH-86-07 / T-86-16; fails_when=another module names the collection or its constant, or
    reaches golive's accessor."""
    offenders = {path: naming_rule(path, src) for path, src in backend_sources.items() if naming_rule(path, src)}
    assert offenders == {}


def test_no_module_of_the_allowed_set_updates_or_deletes(backend_sources):
    """protects=PROH-86-07; fails_when=an allowed module calls an update, replace, delete, bulk-write, drop or
    rename method on any receiver (a local alias of the collection included)."""
    in_set = {path: mutation_rule(path, backend_sources[path]) for path in ALLOWED_NAMING if path in backend_sources}
    assert GOLIVE_PATH in in_set and "autonomous_ops/__init__.py" in in_set
    assert {path: found for path, found in in_set.items() if found} == {}


def test_the_naming_rule_has_controls():
    """fails_when=the rule stops flagging a violation or starts flagging a legitimate mention."""
    index = 'async def f(db):\n    return await raw(db)["autonomy_golive_checks"].find({})\n'
    assert naming_rule("somewhere/else.py", index) == ["names the go-live collection"]
    delete = "from autonomous_ops.reporting import golive\nasync def f(db):\n    await golive._checks(db).delete_many({})\n"
    assert naming_rule("somewhere/else.py", delete) == ["uses the go-live accessor"]
    imported = "from autonomous_ops.reporting.golive import _checks\n"
    assert naming_rule("somewhere/else.py", imported) == ["uses the go-live accessor"]
    constant = "from autonomous_ops.reporting import GOLIVE_CHECKS as C\n"
    assert naming_rule("somewhere/else.py", constant) == ["names the go-live collection"]
    docstring_only = '"""Mentions autonomy_golive_checks and GOLIVE_CHECKS only here."""\n\ndef f():\n    """And here: autonomy_golive_checks."""\n    return 1\n'
    assert naming_rule("somewhere/else.py", docstring_only) == []
    migration = ('"""Indexes for autonomy_golive_checks."""\nfrom autonomous_ops.reporting import golive\n\n'
                 "# the collection autonomy_golive_checks is indexed by golive\n"
                 "async def run(db):\n    await golive.ensure_indexes(db)\n")
    assert naming_rule("migrations/035_activity_reporting.py", migration) == []
    assert mutation_rule("migrations/035_activity_reporting.py", migration) == []


def test_the_mutation_rule_has_controls():
    """fails_when=an allowed module can update or delete evidence through an alias without being caught."""
    alias = ("from . import GOLIVE_CHECKS\n\ndef _checks(db):\n    return db[GOLIVE_CHECKS]\n\n"
             "async def edit(db):\n    c = _checks(db)\n    await c.update_one({}, {'$set': {'note': 'x'}})\n")
    assert mutation_rule(GOLIVE_PATH, alias) == ["update_one"]
    many = "async def f(db):\n    await db.x.delete_many({})\n    await db.y.drop()\n    await db.z.rename('q')\n"
    assert mutation_rule("autonomous_ops/__init__.py", many) == ["delete_many", "drop", "rename"]
    reads = "async def f(db):\n    await db.x.insert_one({})\n    await db.x.create_index('a')\n    await db.x.find_one({})\n"
    assert mutation_rule(GOLIVE_PATH, reads) == []
    assert mutation_rule("somewhere/else.py", many) == []
