"""Staged patch rollouts, plan 84-16: Resume, Cancel, completion with not-reached computers, and closing.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. Rollouts, hosts and
install rows are written straight into the collections the controller owns; Resume and Cancel are the real
lifecycle functions and the real routes (behind the Patching catalogue guard, the caller replaced by a dependency
override so the real permission checks run); time is frozen by passing ``now``.

Value: protects=PTCH-01 / PTCH-04 / PTCH-07 / D-16 / D-18 / PROH-84-07 / T-84-48..50: a halted rollout continues
only through a green health check on current data with a recorded reason, never by skipping a failed computer;
Cancel ends it and frees the computers; a rollout that finished keeps the computers it never reached for a week,
offers them the install as an approval (never on its own) and then closes; fails_when=a red check lets the
rollout continue, a failed computer is removed or counted as passed, Resume or Cancel works on a running rollout,
during a revert (Resume), for an API key or a viewer, or leaves no control row and audit event, a cancel keeps a
claim, a returning computer is installed without an approval, or a closed rollout still holds a computer;
no_claim=a real agent, the screens (84-18) or the live database.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import patch_rollout_endpoints as endpoints
import rbac_utils
from api_key_auth import get_current_user_or_api_key
from auth_types import TokenData
from authentication_service import get_current_user
from autonomous_ops import ledger, protected
from autonomous_ops.rollout import controller, lifecycle, messages as rm, store
from catalogue_mounts import mount_dependencies
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import seed_rollout_agent, seed_rollout_tenant, seed_window

T = "t1"
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
BOOT = 1_700_000_000
ACTOR = {"id": "ann@example.test", "name": "Ann", "username": "ann@example.test", "display": "Ann"}
TOKENS = ("patch_reversible_check", "patch_revert_by_job", "reboot_host")
BASE = "/api/patch-rollouts"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


def hhmm(moment):
    return moment.strftime("%H:%M")


async def world(db, *, status="halted", ring=1, code="no_data:inventory", rings=3, window=True):
    """A tenant, an open window and a rollout halted at ``ring`` (soak over, checks otherwise unreported)."""
    await ledger.ensure_indexes(db)
    await store.ensure_indexes(db)
    await seed_rollout_tenant(db, T, shadow=False)
    await seed_rollout_tenant(db, "t2", shadow=False)
    if window:
        await seed_window(db, T, start=hhmm(NOW - timedelta(hours=1)), end=hhmm(NOW + timedelta(hours=3)))
    names = ["Canary", "Pilot", "Everyone else"][:rings]
    ring_docs = [{"index": i, "key": n.lower(), "name": n, "groupIds": [], "soakHours": 1, "failPct": 10,
                  "minSample": 10, "isCanary": i == 0,
                  "state": "passed" if i < ring else "halted" if i == ring else "not_started",
                  "soakEndsAt": NOW - timedelta(hours=1)} for i, n in enumerate(names)]
    doc = {"id": "r1", "tenantId": T, "name": "Nov", "patchIds": ["openssl"], "patchesByOs": {"linux": ["openssl"]},
           "status": status, "shadow": False, "currentRing": ring, "rings": ring_docs, "leftOut": [],
           "createdAt": NOW - timedelta(hours=9), "createdBy": ACTOR}
    if status == "halted":
        doc.update({"haltedAt": NOW - timedelta(minutes=30),
                    "haltReason": {"code": code, "ring": ring, "host": None, "at": NOW - timedelta(minutes=30),
                                   "text": rm.HALT_REASON[code]}})
    await db.patch_rollouts.insert_one(doc)


async def add(db, agent, *, ring=1, state="installed", scanned=True, os_name="linux", active=True, **extra):
    """A computer of the rollout. An installed one has reported its install two hours ago and (``scanned``) has
    sent a scan since that no longer lists the patch."""
    await seed_rollout_agent(db, T, agent, hostname=f"host-{agent}", platform="Linux", tokens=TOKENS,
                             pending=[] if scanned else ["openssl"], boot_time=BOOT, last_seen=NOW,
                             scan_at=NOW - timedelta(minutes=30))
    doc = {"tenantId": T, "rolloutId": "r1", "agentId": agent, "ring": ring, "state": state, "os": os_name,
           "hostname": f"host-{agent}", "patchIds": ["openssl"], "installedIds": ["openssl"], "active": active,
           "waitReason": None, "installReportedAt": NOW - timedelta(hours=2)}
    doc.update(extra)
    await db.patch_rollout_hosts.insert_one(doc)


async def rollout(db):
    return store.normalise(await db.patch_rollouts.find_one({"id": "r1"}))


async def host(db, agent):
    return await db.patch_rollout_hosts.find_one({"tenantId": T, "agentId": agent}, {"_id": 0})


async def controls(db, event):
    return [r async for r in db.autonomy_actions.find({"tenantId": T, "kind": "control", "controlEvent": event}, {"_id": 0})]


async def audits(db, event):
    return [e async for e in db.audit_logs.find({"tenantId": T, "action": f"autonomous_ops.{event}"})]


# ---------------------------------------------------------------- Task 1: Resume

async def test_resume_on_a_green_check_passes_the_ring_and_goes_on_with_one_record(mongo_db):
    """protects=D-16; fails_when=a green check does not continue, the next ring is not current, or the typed reason
    and the person are not recorded once in the activity list and once in the audit log."""
    db = mongo_db
    await world(db)
    await add(db, "h1")

    out = await lifecycle.resume(db, T, "r1", actor=ACTOR, reason="  Scan was delayed  ", now=NOW)

    assert out["status"] == "resumed"
    got = await rollout(db)
    assert got["status"] == "running" and got["currentRing"] == 2 and "haltReason" not in got
    assert [r["state"] for r in got["rings"]][:2] == ["passed", "passed"] and got["rings"][1]["passedAt"]
    assert got["resumeLog"][0]["reason"] == "Scan was delayed" and got["resumeLog"][0]["outcome"] == "resumed"
    found = await controls(db, "rollout_resumed")
    assert len(found) == 1 and found[0]["actor"]["display"] == "Ann" and "Scan was delayed" in found[0]["reasonText"]
    assert len(await audits(db, "rollout_resumed")) == 1
    assert await db.patch_rollout_hosts.count_documents({"tenantId": T, "active": True}) == 1      # claims kept


async def test_resume_of_the_last_ring_completes_the_rollout_and_frees_the_computers(mongo_db):
    db = mongo_db
    await world(db, ring=2)
    await add(db, "h1", ring=2)
    out = await lifecycle.resume(db, T, "r1", actor=ACTOR, reason="Fixed", now=NOW)
    assert out["status"] == "resumed"
    got = await rollout(db)
    assert got["status"] == "completed" and got["rings"][2]["state"] == "passed"
    assert await db.patch_rollout_hosts.count_documents({"tenantId": T, "active": True}) == 0


async def test_resume_on_a_red_check_keeps_the_rollout_halted_with_the_new_reason_and_skips_nothing(mongo_db):
    """protects=PROH-84-07 / T-84-48; fails_when=a failed computer is removed, excluded or counted as passed, or the
    rollout moves on."""
    db = mongo_db
    await world(db)
    await add(db, "h1", state="failed", failureMessage="no")
    await add(db, "h2")

    out = await lifecycle.resume(db, T, "r1", actor=ACTOR, reason="Looked at it", now=NOW)

    assert out["status"] == "still_halted"
    assert out["reason"] == rm.fill(rm.HALT_REASON["host_failed"], host="host-h1")
    got = await rollout(db)
    assert got["status"] == "halted" and got["currentRing"] == 1 and got["rings"][1]["state"] == "halted"
    assert got["haltReason"]["code"] == "host_failed" and got["haltReason"]["text"] == out["reason"]
    assert got["rings"][1]["healthCounts"] == {"reported": 2, "failed": 1}
    failed = await host(db, "h1")
    assert failed["state"] == "failed" and failed["active"] is True and failed["ring"] == 1
    assert await db.patch_rollout_hosts.count_documents({"tenantId": T}) == 2
    assert got["resumeLog"][0]["outcome"] == "still_halted"
    assert len(await controls(db, "rollout_resume_checked")) == 1 and not await controls(db, "rollout_resumed")


async def test_a_computer_that_is_still_waiting_for_data_does_not_let_the_ring_pass(mongo_db):
    """fails_when=missing data counts as green: the scan is older than the install."""
    db = mongo_db
    await world(db)
    await add(db, "h1", scanned=False)                         # the scan still lists the patch: a failure, not a pass
    out = await lifecycle.resume(db, T, "r1", actor=ACTOR, reason="Again", now=NOW)
    assert out["status"] == "still_halted" and (await rollout(db))["status"] == "halted"


async def test_resume_is_refused_while_a_revert_runs_and_when_the_rollout_is_not_halted(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "h1", state="reverting")
    with pytest.raises(lifecycle.RevertRunning):
        await lifecycle.resume(db, T, "r1", actor=ACTOR, reason="Now", now=NOW)
    got = await rollout(db)
    assert got["status"] == "halted" and "resumeLog" not in got and not await controls(db, "rollout_resumed")
    await db.patch_rollouts.update_one({"id": "r1"}, {"$set": {"status": "running"}})
    with pytest.raises(lifecycle.NotHalted):
        await lifecycle.resume(db, T, "r1", actor=ACTOR, reason="Now", now=NOW)
    with pytest.raises(lifecycle.NotHalted):
        await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)


async def test_resume_needs_a_real_reason_and_another_organizations_rollout_is_not_found(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "h1")
    for bad in ("", "   ", "\n\t", "x" * 501, None):
        with pytest.raises(lifecycle.ReasonRequired):
            await lifecycle.resume(db, T, "r1", actor=ACTOR, reason=bad, now=NOW)
    assert (await rollout(db))["status"] == "halted"
    with pytest.raises(lifecycle.RolloutNotFound):
        await lifecycle.resume(db, "t2", "r1", actor=ACTOR, reason="Fine", now=NOW)
    with pytest.raises(lifecycle.RolloutNotFound):
        await lifecycle.cancel(db, "t2", "r1", actor=ACTOR, now=NOW)
    out = await lifecycle.resume(db, T, "r1", actor=ACTOR, reason="x" * 500, now=NOW)
    assert out["status"] == "resumed"


async def test_two_resumes_at_once_continue_the_rollout_once(mongo_db):
    import asyncio
    db = mongo_db
    await world(db)
    await add(db, "h1")
    results = await asyncio.gather(*[lifecycle.resume(db, T, "r1", actor=ACTOR, reason="Go", now=NOW)
                                     for _ in range(2)], return_exceptions=True)
    assert sorted(type(r).__name__ for r in results) == ["NotHalted", "dict"]
    assert (await rollout(db))["currentRing"] == 2 and len(await controls(db, "rollout_resumed")) == 1


# ---------------------------------------------------------------- Task 1: Cancel

async def test_cancel_ends_the_rollout_frees_every_claim_closes_open_rows_and_leaves_a_revert_alone(mongo_db):
    """protects=D-16 / PTCH-07; fails_when=a claim stays, an open card stays approvable, a revert is touched or a
    patched computer loses its patch."""
    db = mongo_db
    await world(db)
    await add(db, "h1", state="reverting", revertJobId="j1")
    await add(db, "h2")
    await add(db, "h3", ring=2, state="waiting")
    for action_id, state, extra in (("AO-open", "awaiting_approval", {}), ("AO-undo", "undone", {"undo": {"available": True}})):
        await ledger.create_intent(db, {
            "id": action_id, "tenantId": T, "kind": "patching", "origin": "rollout", "dispatcher": "patch_rollout",
            "state": state, "command": "install_patches", "actions": ["install_patches"], "targets": ["h3"],
            "params": {}, "steps": [], "reasonText": "A row.", "reasonCode": "playbook_raised",
            "reason": {"ruleId": "rollout:install", "inputs": {"rolloutId": "r1", "ring": 2, "line": "install"}},
            "approval": {"expiresAt": NOW + timedelta(hours=5)}, **extra})

    out = await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)

    assert out["status"] == "cancelled"
    got = await rollout(db)
    assert got["status"] == "cancelled" and got["cancelledAt"] and got["revertOpen"] is True
    assert [r["state"] for r in got["rings"]] == ["passed", "cancelled", "cancelled"]
    assert await db.patch_rollout_hosts.count_documents({"tenantId": T, "active": True}) == 0
    assert (await host(db, "h1"))["state"] == "reverting" and (await host(db, "h2"))["state"] == "installed"
    opened = await db.autonomy_actions.find_one({"id": "AO-open"})
    assert opened["state"] == "expired" and opened["reasonCode"] == "rollout_closed"
    assert (await db.autonomy_actions.find_one({"id": "AO-undo"}))["state"] == "undone"
    found = await controls(db, "rollout_cancelled")
    assert len(found) == 1 and found[0]["actor"]["display"] == "Ann"
    assert len(await audits(db, "rollout_cancelled")) == 1
    with pytest.raises(lifecycle.NotHalted):                   # a second cancel finds nothing to cancel
        await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)


async def test_cancel_with_no_revert_running_marks_no_revert_open(mongo_db):
    db = mongo_db
    await world(db)
    await add(db, "h2")
    await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)
    assert (await rollout(db))["revertOpen"] is False


async def test_a_cancelled_rollouts_revert_is_still_settled_by_the_controller(mongo_db):
    """fails_when=a revert that was left to finish never reaches Reverted because the controller no longer visits the
    cancelled rollout."""
    from tests.test_patch_rollout_revert import add as add_installed, answer, halt, host_doc, world as revert_world
    db = mongo_db
    await revert_world(db)
    await add_installed(db, "l1")
    await halt(db)
    assert (await host_doc(db, "l1"))["state"] == "reverting"
    await lifecycle.cancel(db, T, "r1", actor=ACTOR, now=NOW)
    await answer(db, "l1", _success_revert("openssl"))
    await controller.tick(db, now=NOW + timedelta(minutes=1))
    assert (await host_doc(db, "l1"))["state"] == "reverted"
    assert (await rollout(db))["revertOpen"] is False
    await controller.tick(db, now=NOW + timedelta(minutes=2))
    assert (await host_doc(db, "l1"))["state"] == "reverted"


def _success_revert(patch_id):
    return {"status": "completed", "successful": 1, "failed": 0, "total": 1,
            "results": [{"patch_id": patch_id, "status": "success", "reboot_required": False}]}


# ---------------------------------------------------------------- Task 1: the routes

class Api:
    """The router behind its catalogue guard; the caller's identity is chosen per request."""

    def __init__(self, db, monkeypatch):
        self.db = db
        self.user = None
        monkeypatch.setattr(endpoints, "get_database", lambda: db)
        monkeypatch.setattr(rbac_utils, "get_database", lambda: db)
        self.app = FastAPI()
        self.app.include_router(endpoints.router, dependencies=mount_dependencies("patch_rollout_endpoints", "router"))
        self.app.dependency_overrides[get_current_user_or_api_key] = lambda: self.user
        self.app.dependency_overrides[get_current_user] = lambda: self.user

    async def call(self, method, path, *, role="tenant_admin", tenant=T, auth="session", scopes=None, json=None):
        self.user = TokenData(username=f"{role}@example.test", role=role, tenant_id=tenant, scopes=scopes,
                              auth_source="api_key" if auth == "api_key" else "session")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver") as c:
            return await c.request(method, path, json=json)


@pytest.fixture
async def api(mongo_db, monkeypatch):
    await world(mongo_db)
    await add(mongo_db, "h1")
    return Api(mongo_db, monkeypatch)


async def test_the_resume_route_continues_on_a_green_check_and_names_the_person(api):
    got = await api.call("POST", f"{BASE}/r1/resume", json={"reason": "Scan was delayed"})
    assert got.status_code == 200, got.text
    assert got.json()["status"] == "resumed" and got.json()["ring"] == "Pilot"
    assert (await rollout(api.db))["currentRing"] == 2
    found = await controls(api.db, "rollout_resumed")
    assert found[0]["actor"]["username"] == "tenant_admin@example.test"


async def test_the_resume_route_answers_still_halted_with_the_new_reason(api):
    await api.db.patch_rollout_hosts.update_one({"agentId": "h1"}, {"$set": {"state": "failed"}})
    got = await api.call("POST", f"{BASE}/r1/resume", json={"reason": "Tried"})
    assert got.status_code == 200
    assert got.json() == {"status": "still_halted", "reason": rm.fill(rm.HALT_REASON["host_failed"], host="host-h1"),
                          "ring": "Pilot"}


async def test_the_routes_map_each_refusal_to_its_status_and_sentence(api):
    db = api.db
    assert (await api.call("POST", f"{BASE}/r1/resume", json={"reason": "   "})).status_code == 422
    assert (await api.call("POST", f"{BASE}/r1/resume", json={"reason": "   "})).json()["detail"] == rm.API_DETAIL["reason_required"]
    assert (await api.call("POST", f"{BASE}/r1/resume", json={})).status_code == 422
    assert (await api.call("POST", f"{BASE}/nope/resume", json={"reason": "x"})).status_code == 404
    assert (await api.call("POST", f"{BASE}/r1/resume", tenant="t2", json={"reason": "x"})).status_code == 404
    assert (await api.call("POST", f"{BASE}/r1/cancel", tenant="t2")).status_code == 404
    await db.patch_rollout_hosts.update_one({"agentId": "h1"}, {"$set": {"state": "reverting"}})
    busy = await api.call("POST", f"{BASE}/r1/resume", json={"reason": "x"})
    assert busy.status_code == 409 and busy.json()["detail"] == rm.API_DETAIL["revert_running"]
    await db.patch_rollouts.update_one({"id": "r1"}, {"$set": {"status": "running"}})
    for path, body in (("resume", {"reason": "x"}), ("cancel", None)):
        refused = await api.call("POST", f"{BASE}/r1/{path}", json=body)
        assert refused.status_code == 409 and refused.json()["detail"] == rm.API_DETAIL["not_halted"]


async def test_the_cancel_route_ends_a_halted_rollout(api):
    got = await api.call("POST", f"{BASE}/r1/cancel")
    assert got.status_code == 200 and got.json()["status"] == "cancelled"
    assert (await rollout(api.db))["status"] == "cancelled"


async def test_a_viewer_an_api_key_and_platform_support_cannot_resume_or_cancel(api):
    """protects=T-84-50; fails_when=anything but a signed-in person with manage:patches reaches the lifecycle."""
    scopes = ["view:patching", "manage:patches"]
    for role, kwargs in (("user", {}), ("tenant_admin", {"auth": "api_key", "scopes": scopes})):
        assert (await api.call("POST", f"{BASE}/r1/resume", role=role, json={"reason": "x"}, **kwargs)).status_code == 403
        assert (await api.call("POST", f"{BASE}/r1/cancel", role=role, **kwargs)).status_code == 403
    got = await rollout(api.db)
    assert got["status"] == "halted" and "resumeLog" not in got
    assert not await controls(api.db, "rollout_resumed") and not await controls(api.db, "rollout_cancelled")
