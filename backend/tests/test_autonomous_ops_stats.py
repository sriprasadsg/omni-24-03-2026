"""Autonomous Ops statistics and time saved (Phase 86, plan 86-01, ACTV-05, ACTV-07, D-05..D-08, D-19).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the per-rule counts, the simulation column kept apart from the real ones, the fixed
minutes-per-kind estimate, the period edges, and the tenant boundary of GET /api/autonomous-ops/statistics;
fails_when=a simulation or control row is counted as a real decision, an undone action adds minutes, a
period edge moves, one tenant sees another's numbers, or the minutes table misses a registered command;
no_claim=the Statistics card rendering (autonomousOpsStats.test.tsx) and the export and digest, which
read this module in later plans.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rbac_utils
from api_key_auth import get_current_user_or_api_key
from auth_types import TokenData
from autonomous_ops import ledger, messages, protected, registry
from autonomous_ops.reporting import DEFAULT_WINDOW, MINUTES_PER_KIND, stats
from catalogue_mounts import mount_dependencies
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

PLATFORM = "platform-admin"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


class StatsApi:
    """The reporting router behind its catalogue guard; the caller's identity is chosen per request."""

    def __init__(self, db, monkeypatch):
        import autonomous_ops_endpoints
        import autonomous_ops_reporting_endpoints as reporting
        self.user = None
        monkeypatch.setattr(autonomous_ops_endpoints, "get_database", lambda: db)
        monkeypatch.setattr(reporting, "get_database", lambda: db)
        monkeypatch.setattr(rbac_utils, "get_database", lambda: db)
        self.app = FastAPI()
        self.app.include_router(reporting.router,
                                dependencies=mount_dependencies("autonomous_ops_reporting_endpoints", "router"))
        self.app.dependency_overrides[get_current_user_or_api_key] = lambda: self.user

    async def get(self, path, *, role="tenant_admin", tenant="t1"):
        platform = role in ("super_admin", "platform_support", "platform_billing")
        self.user = TokenData(username=f"{role}@example.test", role=role,
                              tenant_id=PLATFORM if platform else tenant, scopes=None, auth_source="session")
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_tenant(mongo_db, "t2", shadow=False)
    return mongo_db, StatsApi(mongo_db, monkeypatch)


async def seed_row(db, tenant, command, state, *, rule=None, kind="security", approver=None, when=None):
    """One decision row with only the fields the statistics read."""
    row = {"id": "AO-" + uuid.uuid4().hex, "tenantId": tenant, "kind": kind, "command": command, "state": state,
           "reason": {"ruleId": rule or f"sweep:{command}"}, "approval": {"approver": approver},
           "createdAt": when or datetime.now(timezone.utc) - timedelta(days=1)}
    await db.autonomy_actions.insert_one(row)
    return row


# ================================================================== task 1: the tracer

async def test_the_route_counts_this_tenants_ledger_with_the_estimate_labelled(world):
    db, api = world
    await seed_row(db, "t1", "isolate_host", "executed")
    await seed_row(db, "t1", "isolate_host", "verified")
    await seed_row(db, "t1", "block_ip", "undone")
    await seed_row(db, "t1", "block_ip", "shadow")
    await seed_row(db, "t1", "isolate_host", "recorded", kind="control")
    await seed_row(db, "t1", "isolate_host", "recorded", kind="platform_health")
    await seed_row(db, "t2", "isolate_host", "executed")
    got = await api.get("/api/autonomous-ops/statistics")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["days"] == 30 and body["tenantId"] == "t1"
    assert body["totals"]["fired"] == 3 and body["totals"]["done"] == 2
    assert body["totals"]["undone"] == 1 and body["totals"]["wouldHaveDone"] == 1
    assert body["timeSaved"]["minutes"] == 30 and body["timeSaved"]["estimate"] is True


async def test_a_period_outside_seven_thirty_ninety_is_rejected(world):
    _, api = world
    assert (await api.get("/api/autonomous-ops/statistics?days=14")).status_code == 422
    assert (await api.get("/api/autonomous-ops/statistics?days=7")).status_code == 200


def test_the_default_period_is_thirty_days():
    assert DEFAULT_WINDOW == 30


def test_minutes_format_in_plain_words():
    assert stats.format_minutes(0) == "0 min"
    assert stats.format_minutes(45) == "About 45 min"
    assert stats.format_minutes(338) == "About 5 h 40 min"
    assert stats.format_minutes(120) == "About 2 h"


def test_minutes_per_kind_is_read_only_and_names_the_isolation_value():
    assert MINUTES_PER_KIND["isolate_host"] == 15
    with pytest.raises(TypeError):
        MINUTES_PER_KIND["isolate_host"] = 1   # type: ignore[index]
    assert registry.ACTIONS  # the full completeness check follows in task 2


# ================================================================== task 2: the full matrix

NOW = datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc)   # whole milliseconds: BSON stores no finer


def _group(rule, state, n=1, *, cmd="isolate_host", approved=False):
    return {"rule": rule, "cmd": cmd, "state": state, "approved": approved, "n": n}


def _rule(folded, rule_id):
    return next(r for r in folded["rules"] if r["id"] == rule_id)


def test_an_approved_then_executed_row_counts_fired_approved_and_done():
    got = _rule(stats.fold([_group("r", "executed", approved=True)]), "r")
    assert (got["fired"], got["approved"], got["done"]) == (1, 1, 1)


def test_an_approved_then_undone_row_counts_approved_and_undone():
    got = _rule(stats.fold([_group("r", "undone", approved=True), _group("r", "rolled_back")]), "r")
    assert (got["fired"], got["approved"], got["undone"]) == (2, 1, 2)


def test_a_denied_row_counts_denied_not_approved_although_the_approver_is_recorded():
    got = _rule(stats.fold([_group("r", "denied", approved=True)]), "r")
    assert (got["fired"], got["denied"], got["approved"]) == (1, 1, 0)


def test_expired_cancelled_and_refused_rows_count_refused_and_failed_counts_failed():
    folded = stats.fold([_group("r", "expired"), _group("r", "cancelled_by_stop"), _group("r", "refused"),
                         _group("r", "failed")])
    got = _rule(folded, "r")
    assert (got["refused"], got["failed"], got["fired"]) == (3, 1, 4)
    assert folded["totals"]["refused"] == 3 and folded["totals"]["denied"] == 0


def test_an_awaiting_and_a_suggested_row_count_fired_only():
    got = _rule(stats.fold([_group("r", "awaiting_approval"), _group("r", "suggested")]), "r")
    assert got["fired"] == 2
    assert all(got[c] == 0 for c in ("done", "approved", "denied", "undone", "failed", "refused", "wouldHaveDone"))


def test_a_shadow_row_adds_only_to_would_have_done():
    folded = stats.fold([_group("r", "shadow", 4), _group("r", "executed")])
    got = _rule(folded, "r")
    assert (got["wouldHaveDone"], got["fired"], got["done"]) == (4, 1, 1)
    assert folded["totals"]["wouldHaveDone"] == 4 and folded["totals"]["fired"] == 1


def test_an_unknown_rule_id_reads_as_itself_and_a_missing_one_groups_as_unknown():
    folded = stats.fold([_group("custom:x", "executed"), _group("gate:unknown", "refused")])
    assert _rule(folded, "custom:x")["name"] == "custom:x"
    assert _rule(folded, "gate:unknown")["name"] == "Automatic decision (unknown)"


def test_a_known_rule_reads_its_plain_name():
    from autonomous_ops.reporting import rule_names
    assert _rule(stats.fold([_group("sweep:isolate_host", "executed")]), "sweep:isolate_host")["name"] \
        == rule_names.RULE_NAMES["sweep:isolate_host"] != "sweep:isolate_host"


def test_every_rule_id_the_product_writes_has_a_plain_name():
    from autonomous_ops.reporting import rule_names
    written = ("sweep:block_ip", "sweep:single_signal", "sweep:quarantine_file", "sweep:isolate_host",
               "sweep:kill_process", "sweep:restart_service", "sweep:suggest_vulnerability",
               "sweep:suggest_file_change", "rollout:install", "rollout:canary_install", "rollout:reboot",
               "rollout:revert_reboot", "service_desk:answer", "service_desk:handoff")
    for rule_id in written:
        assert rule_names.rule_name(rule_id) != rule_id, rule_id


def test_equal_fired_counts_come_back_ordered_by_name_then_id():
    groups = [_group("sweep:single_signal", "executed"), _group("sweep:block_ip", "executed"),
              _group("zzz:a", "executed"), _group("aaa:z", "executed"), _group("sweep:kill_process", "executed", 2)]
    first = [r["id"] for r in stats.fold(groups)["rules"]]
    assert first[0] == "sweep:kill_process"
    assert [r["id"] for r in stats.fold(list(reversed(groups)))["rules"]] == first
    rest = [(r["name"], r["id"]) for r in stats.fold(groups)["rules"][1:]]
    assert rest == sorted(rest)


def test_time_saved_counts_only_executed_and_verified_rows_by_kind():
    saved = stats.time_saved([_group("r", "verified", cmd="rotate_key"), _group("r", "executed", 2, cmd="isolate_host"),
                              _group("r", "undone", 5, cmd="isolate_host"), _group("r", "shadow", 9, cmd="block_ip"),
                              _group("r", "awaiting_approval", 3, cmd="reboot_host")])
    assert saved["minutes"] == 20 + 30 and saved["estimate"] is True
    assert saved["minutes"] == sum(k["subtotal"] for k in saved["perKind"])
    assert [k["kind"] for k in saved["perKind"]] == list(MINUTES_PER_KIND)
    by_kind = {k["kind"]: k for k in saved["perKind"]}
    assert by_kind["block_ip"]["counted"] == 0 and by_kind["rotate_key"]["subtotal"] == 20


def test_a_handoff_counts_done_and_adds_no_minutes_and_an_empty_ledger_reads_zero():
    folded = stats.fold([_group("service_desk:handoff", "executed", 2, cmd="ticket_handoff")])
    assert _rule(folded, "service_desk:handoff")["done"] == 2
    assert stats.time_saved([_group("service_desk:handoff", "executed", 2, cmd="ticket_handoff")])["minutes"] == 0
    assert stats.fold([]) == {"rules": [], "totals": {c: 0 for c in (
        "fired", "done", "approved", "denied", "undone", "failed", "refused", "wouldHaveDone")}}
    assert stats.time_saved([])["minutes"] == 0


def test_the_minutes_table_covers_every_registered_command_plus_the_hand_off():
    assert set(MINUTES_PER_KIND) == set(registry.ACTIONS) | {"ticket_handoff"}
    assert {k: MINUTES_PER_KIND[k] for k in ("isolate_host", "quarantine_file", "restore_file")} == {
        "isolate_host": 15, "quarantine_file": 15, "restore_file": 15}
    assert MINUTES_PER_KIND["rotate_key"] == 20 and MINUTES_PER_KIND["rollback_ransomware"] == 30
    assert MINUTES_PER_KIND["ticket_answer"] == 8
    assert all(MINUTES_PER_KIND[k] == 0 for k in registry.ACTIONS
               if registry.ACTIONS[k].cls in ("undo_only", "probe"))


def test_minutes_round_to_five_from_an_hour():
    assert stats.format_minutes(59) == "About 59 min"
    assert stats.format_minutes(62) == "About 1 h"
    assert stats.format_minutes(1) == "About 1 min"


async def test_a_row_exactly_at_the_period_edge_counts_and_one_microsecond_earlier_does_not(world):
    db, api = world
    for days in (7, 30, 90):
        edge = NOW - timedelta(days=days)
        await seed_row(db, "t1", "isolate_host", "executed", rule=f"edge:{days}", when=edge)
        await seed_row(db, "t1", "isolate_host", "executed", rule=f"early:{days}", when=edge - timedelta(microseconds=1))
    caller = await _caller("tenant_admin", "t1")
    for days in (7, 30, 90):
        payload = await stats.statistics_payload(db, caller, "t1", days, now=NOW)
        ids = {r["id"] for r in payload["rules"]}
        assert f"edge:{days}" in ids and f"early:{days}" not in ids, days


async def test_all_time_has_no_lower_bound(world):
    db, _ = world
    await seed_row(db, "t1", "isolate_host", "executed", when=NOW - timedelta(days=900))
    assert sum(g["n"] for g in await stats.compute(db, "t1", days=None, now=NOW)) == 1
    assert await stats.compute(db, "t1", days=90, now=NOW) == []


async def test_a_tenant_with_no_rows_answers_zero_everywhere(world):
    _, api = world
    body = (await api.get("/api/autonomous-ops/statistics")).json()
    assert body["rules"] == [] and set(body["totals"].values()) == {0}
    assert body["timeSaved"]["minutes"] == 0 and body["timeSaved"]["estimate"] is True
    assert [k["kind"] for k in body["timeSaved"]["perKind"]] == list(MINUTES_PER_KIND)


async def test_another_tenants_rows_never_change_the_numbers(world):
    db, api = world
    await seed_row(db, "t2", "isolate_host", "executed")
    await seed_row(db, "t2", "block_ip", "shadow")
    body = (await api.get("/api/autonomous-ops/statistics")).json()
    assert body["rules"] == [] and body["timeSaved"]["minutes"] == 0
    other = (await api.get("/api/autonomous-ops/statistics?tenantId=t2", role="super_admin")).json()
    assert other["totals"]["done"] == 1 and other["totals"]["wouldHaveDone"] == 1


async def test_a_tenant_admin_naming_another_tenant_is_refused(world):
    _, api = world
    assert (await api.get("/api/autonomous-ops/statistics?tenantId=t2")).status_code == 403


async def test_platform_staff_must_name_a_tenant_and_the_platform_organization_answers_409(world):
    _, api = world
    assert (await api.get("/api/autonomous-ops/statistics", role="super_admin")).status_code == 400
    got = await api.get("/api/autonomous-ops/statistics?tenantId=platform-admin", role="super_admin")
    assert got.status_code == 409 and got.json()["detail"] == messages.API_DETAIL["platform_tenant"]
    assert (await api.get("/api/autonomous-ops/statistics", tenant="platform-admin")).status_code == 409


async def test_can_export_needs_export_reports_and_view_autonomous_ops(world):
    _, api = world
    assert (await api.get("/api/autonomous-ops/statistics")).json()["canExport"] is True
    assert (await api.get("/api/autonomous-ops/statistics", role="analyst")).json()["canExport"] is False
    support = await api.get("/api/autonomous-ops/statistics?tenantId=t1", role="platform_support")
    assert support.status_code == 200 and support.json()["canExport"] is False


async def test_shadow_only_follows_the_tenants_shadow_flag(world):
    db, api = world
    assert (await api.get("/api/autonomous-ops/statistics")).json()["shadowOnly"] is False
    await seed_tenant(db, "t1", shadow=True)
    assert (await api.get("/api/autonomous-ops/statistics")).json()["shadowOnly"] is True


async def _caller(role, tenant):
    from autonomous_ops import views
    return await views.build_caller(TokenData(username=f"{role}@example.test", role=role, tenant_id=tenant,
                                              scopes=None, auth_source="session"))
