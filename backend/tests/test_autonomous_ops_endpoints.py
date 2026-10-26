"""Autonomous Ops HTTP routes (Phase 81, plan 81-09): status and activity reads, stop and resume,
level and maximum level, shadow lift, never-touch, approve/deny/undo, and the permission split.

Real MongoDB through the throwaway database of tests/_mongo_test_db.py (skips without a server);
requests go through the real routers with the catalogue mount guard, the identity replaced by a
dependency override. The permission matrix runs on the full mounted app through
``probe_real_app`` (no database: a reachable route answers 200 or 503, a refused one 403).

Value: protects=the screen's two read routes serve display-ready rows for exactly the roles D-06
names, every write route enforces the D-05/D-06/D-10/D-11 split, API keys can press a stop but never
resume, approve, deny, undo or change a setting, and platform staff names stay private from tenants;
fails_when=a role reaches a route it should not, an API key resumes or approves, a tenant reads
another tenant, a simulation reads as done, or a page walk skips or repeats a row;
no_claim=the screen (81-07/81-10) and a real browser session.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import autonomous_ops_endpoints as endpoints
from api_key_auth import get_current_user_or_api_key
from auth_types import TokenData
from autonomous_ops import ledger, messages, protected
from catalogue_mounts import mount_dependencies
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests._route_walk import probe_real_app
from tests.autonomy_support import seed_agent, seed_platform_stop, seed_tenant

PLATFORM = "platform-admin"
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)   # long before any row recorded by the code under test


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("AUTONOMOUS_REMEDIATION_DRY_RUN", raising=False)
    protected.cache_clear()


class Api:
    """The tenant router mounted with its catalogue guard; the caller's identity is per request."""

    def __init__(self, db, monkeypatch):
        self.db = db
        self.user = None
        monkeypatch.setattr(endpoints, "get_database", lambda: db)
        self.app = FastAPI()
        self.app.include_router(endpoints.router,
                                dependencies=mount_dependencies("autonomous_ops_endpoints", "router"))
        self.app.dependency_overrides[get_current_user_or_api_key] = lambda: self.user

    async def call(self, method, path, *, role="tenant_admin", tenant="t1", username=None, auth="session",
                   scopes=None, json=None):
        platform = role in ("super_admin", "platform_support", "platform_billing")
        self.user = TokenData(username=username or f"{role}@example.test", role=role,
                              tenant_id=PLATFORM if platform else tenant, scopes=scopes,
                              auth_source="api_key" if auth == "api_key" else "session")
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, json=json)


@pytest.fixture
async def api(mongo_db, monkeypatch):
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=True)
    await seed_tenant(mongo_db, "t2", shadow=True)
    return Api(mongo_db, monkeypatch)


async def _row(db, row_id, tenant, state, *, created, command="block_ip", target="203.0.113.7",
               targets=("a1",), **extra):
    doc = {"id": row_id, "tenantId": tenant, "kind": "action", "origin": "playbook", "dispatcher": "instruction",
           "command": command, "actions": [command], "targets": list(targets), "target": target, "params": {},
           "state": state, "level": "undoable_auto", "shadow": state == "shadow",
           "reason": {"ruleId": "playbook:contain-ip", "inputs": {}}, "reasonCode": "class_auto",
           "reasonText": "This action is allowed to run on its own within the limits you set.",
           "approval": {"requiredBy": None, "expiresAt": None, "approver": None, "decidedAt": None},
           "undo": {"available": True, "action": "unblock_ip", "params": {}, "undoneAt": None, "undoneBy": None},
           "createdAt": created, "updatedAt": created, "finishedAt": created}
    doc.update(extra)
    await db.autonomy_actions.insert_one(doc)


async def _seed_rows(db):
    await seed_agent(db, "t1", "a1", hostname="web-01")
    await _row(db, "AO-done", "t1", "executed", created=NOW - timedelta(minutes=3))
    await _row(db, "AO-shadow", "t1", "shadow", created=NOW - timedelta(minutes=2), wouldHave="allow_auto",
               reasonText=None)
    await ledger.record_control(db, "t1", "stop_pressed", scope="tenant",
                                actor={"username": "alice", "display": "Alice", "tier": "tenant"}, reason="Maintenance")
    await _row(db, "AO-other", "t2", "executed", created=NOW, targets=("b1",), target="198.51.100.9")


# ------------------------------------------------------------------ status

async def test_tracer_analyst_reads_status_and_display_ready_rows(api):
    """protects=an analyst opens status and activity and reads labelled rows with the simulation
    spelled as not done; fails_when=a raw command name, a missing label or another tenant's row shows."""
    await _seed_rows(api.db)
    status = await api.call("GET", "/api/autonomous-ops/status", role="analyst")
    assert status.status_code == 200
    body = status.json()
    assert set(body) == {"tenantId", "tenantName", "scope", "platformTenant", "eligible", "levelReadable", "level",
                         "maxLevel", "previousLevel", "shadow", "stop", "canStop", "canResume",
                         "canStopPlatform", "canResumePlatform"}
    assert body["tenantId"] == "t1" and body["scope"] == "tenant" and body["tenantName"] == "T1"
    assert body["eligible"] is True and body["levelReadable"] is True and body["platformTenant"] is False
    assert body["level"] == "undoable_auto" and body["maxLevel"] == "undoable_auto"
    assert body["previousLevel"] is None
    assert body["shadow"] == {"effective": True, "source": "tenant"}
    assert body["stop"]["platform"] is None
    assert body["stop"]["tenant"] is None
    assert (body["canStop"], body["canResume"], body["canStopPlatform"], body["canResumePlatform"]) == (False,) * 4

    page = await api.call("GET", "/api/autonomous-ops/actions", role="analyst")
    assert page.status_code == 200
    data = page.json()
    assert set(data) == {"items", "nextCursor", "counts", "total"}
    assert [i["id"] for i in data["items"]][1:] == ["AO-shadow", "AO-done"]
    control, shadow, done = data["items"]
    assert control["bucket"] == "control" and control["controlEvent"] == "stop_pressed"
    assert control["actionLabel"] == messages.CONTROL_LABELS["stop_pressed"]
    assert control["reasonText"] == "Maintenance"
    assert done["bucket"] == "done" and done["state"] == "executed"
    assert done["actionLabel"] == messages.ACTION_LABELS["block_ip"] and done["classLine"] == "Automatic"
    assert done["host"] == "web-01" and done["target"] == "203.0.113.7" and done["ruleId"] == "playbook:contain-ip"
    assert done["controlEvent"] is None and done["createdAt"].startswith("2026-01-01T11:57:00")
    assert shadow["bucket"] == "simulation" and shadow["state"] == "shadow"
    assert shadow["resultText"].startswith("Nothing was done. This is what would have happened:")
    assert "AO-other" not in [i["id"] for i in data["items"]]
    assert data["counts"] == {"pending": 0, "done": 1, "undone": 0, "failed": 0, "refused": 0, "suggested": 0,
                              "simulation": 1}
    assert data["total"] == 3


async def test_bucket_filters_and_counts(api):
    """protects=a state bucket returns only its rows and the simulation bucket only simulations;
    fails_when=a shadow row appears under done or a control row under a state bucket."""
    await _seed_rows(api.db)
    await _row(api.db, "AO-fail", "t1", "failed", created=NOW - timedelta(minutes=1))
    for bucket, expected in (("done", ["AO-done"]), ("simulation", ["AO-shadow"]), ("failed", ["AO-fail"]),
                             ("pending", []), ("undone", [])):
        got = (await api.call("GET", f"/api/autonomous-ops/actions?bucket={bucket}", role="analyst")).json()
        assert [i["id"] for i in got["items"]] == expected, bucket
        assert got["counts"]["done"] == 1 and got["counts"]["simulation"] == 1 and got["counts"]["failed"] == 1
        assert got["total"] == len(expected), bucket
    bad = await api.call("GET", "/api/autonomous-ops/actions?bucket=nonsense", role="analyst")
    assert bad.status_code == 422


async def test_paging_walks_each_row_once_newest_first_with_shared_created_at(api):
    """protects=nextCursor walks every row exactly once in createdAt then id descending order, also
    when rows share a createdAt; fails_when=a gap or a duplicate at a page edge."""
    for n in range(7):
        await _row(api.db, f"AO-{n:02d}", "t1", "executed", created=NOW - timedelta(minutes=n // 3))
    await ledger.record_control(api.db, "t1", "stop_cleared", scope="tenant",
                                actor={"username": "alice", "display": "Alice", "tier": "tenant"}, reason="done")
    seen, cursor, pages = [], None, 0
    while True:
        suffix = f"&cursor={cursor}" if cursor else ""
        got = (await api.call("GET", f"/api/autonomous-ops/actions?limit=2{suffix}", role="analyst")).json()
        pages += 1
        if cursor is None:
            assert got["total"] == 8 and got["counts"]["done"] == 7
        else:
            assert "counts" not in got and "total" not in got       # first page only
        seen += [i["id"] for i in got["items"]]
        cursor = got["nextCursor"]
        if not cursor:
            break
    assert pages == 4 and len(seen) == 8 and len(set(seen)) == 8
    stamps = []
    for item_id in seen:
        row = await api.db.autonomy_actions.find_one({"id": item_id})
        stamps.append((row["createdAt"], item_id))
    assert stamps == sorted(stamps, reverse=True)


async def test_control_row_and_action_row_with_the_same_created_at_both_appear(api):
    """protects=adjacent rows at one instant are both listed under All, id descending, each in one
    bucket; fails_when=the control row hides the action row or the order flips between calls."""
    await _row(api.db, "AO-aaa", "t1", "executed", created=NOW)
    await api.db.autonomy_actions.insert_one({
        "id": "AO-zzz", "tenantId": "t1", "kind": "control", "state": "recorded", "scope": "tenant",
        "controlEvent": "stop_pressed", "actor": {"username": "alice", "display": "Alice", "tier": "tenant"},
        "reasonText": None, "reason": {"ruleId": "control:stop_pressed", "inputs": {}}, "createdAt": NOW,
        "updatedAt": NOW, "finishedAt": NOW})
    got = (await api.call("GET", "/api/autonomous-ops/actions", role="analyst")).json()
    assert [(i["id"], i["bucket"]) for i in got["items"]] == [("AO-zzz", "control"), ("AO-aaa", "done")]


# ------------------------------------------------------------------ tenant boundary and platform staff

async def test_tenant_role_cannot_read_another_tenant_but_may_name_its_own(api):
    """protects=T-81-37; fails_when=a tenant admin passes another tenant's id and reads it."""
    await _seed_rows(api.db)
    assert (await api.call("GET", "/api/autonomous-ops/status?tenantId=t2", role="tenant_admin")).status_code == 403
    assert (await api.call("GET", "/api/autonomous-ops/actions?tenantId=t2", role="analyst")).status_code == 403
    own = await api.call("GET", "/api/autonomous-ops/status?tenantId=t1", role="tenant_admin")
    assert own.status_code == 200 and own.json()["tenantId"] == "t1"


async def test_platform_support_reads_any_tenant_only_with_an_explicit_tenant_id(api):
    """protects=D-08 read side; fails_when=support reads without naming a tenant or sees the wrong one."""
    await _seed_rows(api.db)
    assert (await api.call("GET", "/api/autonomous-ops/status", role="platform_support")).status_code == 400
    got = await api.call("GET", "/api/autonomous-ops/actions?tenantId=t2", role="platform_support")
    assert got.status_code == 200 and [i["id"] for i in got.json()["items"]] == ["AO-other"]
    status = await api.call("GET", "/api/autonomous-ops/status?tenantId=t2", role="platform_support")
    assert status.json()["tenantId"] == "t2" and status.json()["canStop"] is False
    assert (await api.call("GET", "/api/autonomous-ops/status?tenantId=nope", role="platform_support")).status_code == 404
    assert (await api.call("GET", "/api/autonomous-ops/status?tenantId=t1", role="platform_billing")).status_code == 403


async def test_super_admin_reads_a_tenant_and_the_platform_tenant_reads_off(api):
    """protects=the owner names the tenant; the platform organization is never eligible (D-04)."""
    assert (await api.call("GET", "/api/autonomous-ops/status", role="super_admin")).status_code == 400
    got = await api.call("GET", "/api/autonomous-ops/status?tenantId=t1", role="super_admin")
    assert got.status_code == 200 and got.json()["canStop"] is True and got.json()["canStopPlatform"] is True
    plat = await api.call("GET", f"/api/autonomous-ops/status?tenantId={PLATFORM}", role="super_admin")
    body = plat.json()
    assert plat.status_code == 200 and body["platformTenant"] is True
    assert body["level"] == "off" and body["maxLevel"] == "off" and body["canStop"] is False


async def test_platform_stop_name_is_private_from_tenants_and_visible_to_platform_staff(api):
    """protects=D-25 / PROH-81-11 for the status stop and the control rows; fails_when=a tenant viewer
    receives the platform person's name or a tenant-scope name is masked."""
    await seed_platform_stop(api.db, active=True, by="Root Admin")
    await ledger.record_control(api.db, PLATFORM, "platform_stop_pressed", scope="platform",
                                actor={"username": "root", "display": "Root Admin", "tier": "platform"}, reason="Incident")
    await ledger.record_control(api.db, "t1", "stop_pressed", scope="tenant",
                                actor={"username": "alice", "display": "Alice", "tier": "tenant"}, reason=None)
    for role, expected in (("tenant_admin", "Platform administrator"), ("analyst", "Platform administrator"),
                           ("super_admin", "Root Admin"), ("platform_support", "Root Admin")):
        path = "/api/autonomous-ops/status" + ("?tenantId=t1" if role.startswith(("super", "platform")) else "")
        stop = (await api.call("GET", path, role=role)).json()["stop"]
        assert stop["platform"]["by"] == expected, role
        assert stop["platform"]["scope"] == "platform" and stop["platform"]["reason"] is None
    listed = (await api.call("GET", "/api/autonomous-ops/actions", role="tenant_admin")).json()["items"]
    by_event = {i["controlEvent"]: i for i in listed}
    assert "platform_stop_pressed" in by_event, "a tenant's list includes the platform-scope control rows"
    assert by_event["platform_stop_pressed"]["by"] == "Platform administrator"
    assert by_event["stop_pressed"]["by"] == "Alice"
    staff = (await api.call("GET", "/api/autonomous-ops/actions?tenantId=t1", role="platform_support")).json()["items"]
    assert {i["controlEvent"]: i for i in staff}["platform_stop_pressed"]["by"] == "Root Admin"
    assert "Root Admin" not in (await api.call("GET", "/api/autonomous-ops/actions", role="tenant_admin")).text
    assert "Root Admin" not in (await api.call("GET", "/api/autonomous-ops/status", role="tenant_admin")).text


async def test_status_flags_follow_the_caller_and_the_stop(api):
    """protects=canStop/canResume are decided on the server; fails_when=an analyst can stop, a key can
    resume, or a manage holder can resume a Super Admin stop."""
    await api.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {
        "active": True, "scope": "tenant", "pressedBy": {"username": "alice", "display": "Alice"},
        "pressedByTier": "tenant", "pressedAt": NOW, "reason": "Maintenance"}}})
    flags = {}
    for role in ("tenant_admin", "security_analyst", "analyst"):
        body = (await api.call("GET", "/api/autonomous-ops/status", role=role)).json()
        flags[role] = (body["canStop"], body["canResume"])
    assert flags == {"tenant_admin": (True, True), "security_analyst": (True, False), "analyst": (False, False)}
    key = (await api.call("GET", "/api/autonomous-ops/status", role="tenant_admin", auth="api_key",
                          scopes=["view:autonomous_ops", "control:autonomous_ops"])).json()
    assert key["canStop"] is True and key["canResume"] is False
    await api.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop.pressedByTier": "platform"}})
    body = (await api.call("GET", "/api/autonomous-ops/status", role="tenant_admin")).json()
    assert body["canResume"] is False
    body = (await api.call("GET", "/api/autonomous-ops/status?tenantId=t1", role="super_admin")).json()
    assert body["canResume"] is True and body["stop"]["tenant"]["by"] == "Alice"


async def test_shadow_source_is_deployment_when_the_master_is_on(api, monkeypatch):
    """protects=the status says where shadow mode comes from; fails_when=the source is wrong."""
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "true")
    assert (await api.call("GET", "/api/autonomous-ops/status")).json()["shadow"] == {"effective": True,
                                                                                    "source": "deployment"}
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    await api.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
    assert (await api.call("GET", "/api/autonomous-ops/status")).json()["shadow"] == {"effective": False,
                                                                                    "source": None}


# ------------------------------------------------------------------ the mounted app (no database)

def _case(path, role, *, method="GET", auth="session_capable", tenant=None, scopes=None, features=None):
    platform = role in ("super_admin", "platform_support", "platform_billing")
    case = {"method": method, "path": path, "role": role, "auth": auth, "scopes": scopes,
            "tenant_id": PLATFORM if platform else (tenant or "t1")}
    if features is not None:
        case["tenant_features"] = features
    return case


def test_read_routes_are_open_to_exactly_the_roles_d06_names():
    """protects=GATE-13 read side on the full app; fails_when=viewer, user, itam_admin or platform
    billing reach the screen, or an approver role does not."""
    reads = ["/api/autonomous-ops/status", "/api/autonomous-ops/actions"]
    allowed_roles = ("analyst", "security_analyst", "incident_responder", "tenant_admin")
    for path in reads:
        got = probe_real_app([_case(path, role) for role in allowed_roles])
        assert all(code in (200, 503) for code in got), (path, dict(zip(allowed_roles, got)))
        staff = probe_real_app([_case(path + "?tenantId=t1", "super_admin"),
                                _case(path + "?tenantId=t1", "platform_support")])
        assert all(code in (200, 503) for code in staff), (path, staff)
        key = probe_real_app([_case(path, "tenant_admin", auth="api_key", scopes=["view:autonomous_ops"])])
        assert key[0] in (200, 503), (path, key)
        denied_roles = ("viewer", "user", "itam_admin", "platform_billing")
        denied = probe_real_app([_case(path, role) for role in denied_roles])
        assert denied == [403] * len(denied_roles), (path, dict(zip(denied_roles, denied)))
        off = probe_real_app([_case(path, "tenant_admin", features=["view:overview"])])
        assert off == [403], path
        wrong_scope = probe_real_app([_case(path, "tenant_admin", auth="api_key", scopes=["view:agents"])])
        assert wrong_scope == [403], path
