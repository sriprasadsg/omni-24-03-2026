"""Staged patch rollouts, plan 84-09 tasks 2 and 3: the /api/patch-rollouts routes.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; the router is mounted
as in production (behind the Patching catalogue guard) and the caller's identity is replaced by a dependency
override, so the real permission checks run.

Value: protects=PTCH-01 / PTCH-04 / PTCH-05 / PTCH-07 / PROH-84-01: only a person with manage:patches in a signed-in
session starts a rollout or saves rings, a person reads only their own organization's rollouts and suggestions,
a vulnerability suggestion becomes a draft without storing anything, and two Starts at once give one rollout;
fails_when=a viewer, an API key or another organization gets past a check, a draft writes a document, a static
path is read as a rollout id, or a refused Start leaves a claim; no_claim=the screens (84-14, 84-17, 84-18).
"""
import asyncio
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
from autonomous_ops import PLATFORM_TENANT_ID, ledger, protected
from autonomous_ops.rollout import store
from catalogue_mounts import mount_dependencies
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import seed_group, seed_rings, seed_rollout_agent, seed_rollout_tenant, seed_window

BOOT = 1_700_000_000
TOKENS = ("reboot_host", "patch_reversible_check")
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
RINGS = [{"key": "canary", "name": "Canary", "groupIds": ["G1"], "soakHours": 1},
         {"key": "pilot", "name": "Pilot", "groupIds": ["G2"], "soakHours": 1},
         {"key": "rest", "name": "Everyone else", "groupIds": [], "soakHours": 1}]
BASE = "/api/patch-rollouts"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


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
        self.app.dependency_overrides[get_current_user] = lambda: self.user       # the Patching guard's own sign-in

    async def call(self, method, path, *, role="tenant_admin", tenant="t1", auth="session", scopes=None, json=None):
        self.user = TokenData(username=f"{role}@example.test", role=role, tenant_id=tenant, scopes=scopes,
                              auth_source="api_key" if auth == "api_key" else "session")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver") as c:
            return await c.request(method, path, json=json)

    async def twice(self, method, path, json):
        """Two identical requests at the same moment."""
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver") as c:
            self.user = TokenData(username="a@example.test", role="tenant_admin", tenant_id="t1")
            return await asyncio.gather(c.request(method, path, json=json), c.request(method, path, json=json))


async def put_agent(db, agent_id, *, platform="Linux", pending=("openssl",), tenant="t1", group=None, seen=NOW):
    await seed_rollout_agent(db, tenant, agent_id, hostname=f"host-{agent_id}", platform=platform, tokens=TOKENS,
                             pending=list(pending), boot_time=BOOT, last_seen=seen)
    if group:
        await db.agent_group_members.replace_one({"group_id": group, "agent_id": agent_id},
                                                 {"group_id": group, "agent_id": agent_id, "tenantId": tenant},
                                                 upsert=True)


@pytest.fixture
async def api(mongo_db, monkeypatch):
    await ledger.ensure_indexes(mongo_db)
    await store.ensure_indexes(mongo_db)
    for tenant in ("t1", "t2"):
        await seed_rollout_tenant(mongo_db, tenant)
    for group in ("G1", "G2"):
        await seed_group(mongo_db, "t1", group, [])
    await mongo_db.agent_groups.update_one({"id": "G1"}, {"$set": {"name": "Canary"}})
    await seed_rings(mongo_db, "t1", RINGS)
    await seed_window(mongo_db, "t1", start=(NOW - timedelta(hours=1)).strftime("%H:%M"),
                      end=(NOW + timedelta(hours=3)).strftime("%H:%M"))
    return Api(mongo_db, monkeypatch)


async def counts(db):
    return [await getattr(db, name).count_documents({}) for name in
            ("patch_rollouts", "patch_rollout_hosts", "autonomy_actions")]


# ---------------------------------------------------------------- static paths and the window

async def test_static_paths_resolve_before_the_rollout_id(api):
    """protects=route order; fails_when=window, pending-patches, rings or draft is read as a rollout id."""
    window = await api.call("GET", f"{BASE}/window")
    assert window.status_code == 200 and window.json()["state"] == "open"
    pending = await api.call("GET", f"{BASE}/pending-patches")
    assert pending.status_code == 200 and "items" in pending.json()
    rings = await api.call("GET", f"{BASE}/rings")
    assert rings.status_code == 200 and "rings" in rings.json()
    draft = await api.call("GET", f"{BASE}/draft?suggestion=nope")
    assert draft.status_code == 404 and draft.json()["detail"] != "Rollout not found."
    unknown = await api.call("GET", f"{BASE}/nope")
    assert unknown.status_code == 404 and unknown.json()["detail"] == "Rollout not found."


async def test_the_window_route_says_open_closed_or_none(api):
    opened = (await api.call("GET", f"{BASE}/window")).json()
    assert opened["text"].startswith("Closes at ") and opened["text"].endswith("(UTC).")
    await api.db.maintenance_windows.update_many({"tenantId": "t1"}, {"$set": {
        "startTime": (NOW + timedelta(hours=2)).strftime("%H:%M"), "endTime": (NOW + timedelta(hours=3)).strftime("%H:%M")}})
    closed = (await api.call("GET", f"{BASE}/window")).json()
    assert closed["state"] == "closed" and closed["text"].startswith("Next window opens ")
    await api.db.maintenance_windows.delete_many({"tenantId": "t1"})
    none = (await api.call("GET", f"{BASE}/window")).json()
    assert none == {"state": "none", "text": "Add a maintenance window first.", "closesAt": None,
                    "nextOpensAt": None, "timeZone": "UTC"}


# ---------------------------------------------------------------- the patch picker

async def test_pending_patches_list_what_an_eligible_computer_waits_for_with_a_computer_count(api):
    db = api.db
    await put_agent(db, "a1", pending=("openssl", "curl"))
    await put_agent(db, "a2", pending=("openssl",))
    await put_agent(db, "w1", platform="Windows 11", pending=("KB5001",))
    await put_agent(db, "m1", platform="macOS", pending=("safari",))                  # not a Windows or Linux computer
    await put_agent(db, "z9", pending=("zlib",), tenant="t2")                         # another organization
    got = (await api.call("GET", f"{BASE}/pending-patches")).json()
    assert got["total"] == 3 and (got["offset"], got["limit"]) == (0, 50)
    assert got["items"] == [{"patchId": "openssl", "title": "openssl", "os": "linux", "computers": 2},
                            {"patchId": "curl", "title": "curl", "os": "linux", "computers": 1},
                            {"patchId": "KB5001", "title": "KB5001", "os": "windows", "computers": 1}]


async def test_pending_patches_search_matches_the_id_or_the_title_and_pages_by_fifty(api):
    db = api.db
    await put_agent(db, "a1", pending=[f"pkg{i:02d}" for i in range(55)])
    first = (await api.call("GET", f"{BASE}/pending-patches")).json()
    second = (await api.call("GET", f"{BASE}/pending-patches?offset=50")).json()
    assert first["total"] == 55 and len(first["items"]) == 50 and len(second["items"]) == 5
    hit = (await api.call("GET", f"{BASE}/pending-patches?search=PKG07")).json()
    assert [i["patchId"] for i in hit["items"]] == ["pkg07"] and hit["total"] == 1
    await db.agents.update_one({"id": "a1"}, {"$set": {"meta.system_patching.pending_updates": [
        {"id": "pkg00", "title": "Security update for the Kernel"}]}})
    by_title = (await api.call("GET", f"{BASE}/pending-patches?search=kernel")).json()
    assert [i["patchId"] for i in by_title["items"]] == ["pkg00"]


# ---------------------------------------------------------------- the draft from a suggestion (D-11)

async def suggestion(db, row_id="s1", tenant="t1", agent="a1", items=None):
    items = items if items is not None else [{"cve": "CVE-2026-1", "package": "openssl"},
                                             {"cve": "CVE-2026-2", "package": "curl"}]
    await db.autonomy_actions.insert_one({
        "id": row_id, "tenantId": tenant, "kind": "security", "state": "suggested", "targets": [agent],
        "reason": {"ruleId": "sweep:suggest_vulnerability", "inputs": {"suggestionOnly": True, "suggestion": {
            "kind": "vulnerability", "count": len(items), "severity": "High", "items": items}}},
        "createdAt": NOW})


async def test_a_draft_keeps_the_patches_still_pending_on_the_host_and_stores_nothing(api):
    """protects=PROH-84-01 / D-11; fails_when=the draft writes a rollout, a claim or a ledger row, or keeps a patch
    that is no longer pending."""
    await put_agent(api.db, "a1", pending=("openssl",))
    await suggestion(api.db)
    before = await counts(api.db)
    got = await api.call("GET", f"{BASE}/draft?suggestion=s1")
    assert got.status_code == 200
    assert got.json() == {"name": "Patches for vulnerabilities on host-a1", "patchIds": ["openssl"],
                          "removedCount": 1, "host": "host-a1", "cves": ["CVE-2026-1", "CVE-2026-2"]}
    assert await counts(api.db) == before


async def test_a_draft_for_one_cve_is_named_after_it(api):
    await put_agent(api.db, "a1", pending=("openssl",))
    await suggestion(api.db, items=[{"cve": "CVE-2026-9", "package": "openssl"}])
    got = (await api.call("GET", f"{BASE}/draft?suggestion=s1")).json()
    assert got["name"] == "Patches for CVE-2026-9 on host-a1" and got["removedCount"] == 0


async def test_a_suggestion_of_another_organization_or_another_kind_is_not_found(api):
    await put_agent(api.db, "x1", pending=("openssl",), tenant="t2")
    await suggestion(api.db, "theirs", tenant="t2", agent="x1")
    await api.db.autonomy_actions.insert_one({"id": "files", "tenantId": "t1", "targets": ["a1"], "reason": {
        "ruleId": "sweep:suggest_file_change", "inputs": {"suggestion": {"kind": "file_change", "items": []}}}})
    assert (await api.call("GET", f"{BASE}/draft?suggestion=theirs")).status_code == 404
    assert (await api.call("GET", f"{BASE}/draft?suggestion=files")).status_code == 404


# ---------------------------------------------------------------- rings

async def test_rings_read_with_the_groups_a_person_can_pick(api):
    await put_agent(api.db, "a1", group="G1")
    got = (await api.call("GET", f"{BASE}/rings")).json()
    assert got["readable"] is True
    assert [r["key"] for r in got["rings"]] == ["canary", "pilot", "rest"]
    assert got["rings"][0] == {"key": "canary", "name": "Canary", "groupIds": ["G1"], "soakHours": 1,
                               "failPct": 10, "minSample": 10}
    by_id = {g["id"]: g for g in got["groups"]}
    assert by_id["G1"] == {"id": "G1", "name": "Canary", "computers": 1, "ring": "Canary"}
    assert by_id["G2"]["ring"] == "Pilot" and by_id["G2"]["computers"] == 0


async def test_rings_save_and_read_back_and_a_bad_value_answers_the_sentence(api):
    body = {"rings": [{"name": "Canary", "groupIds": ["G1"], "soakHours": 2},
                      {"name": "Everyone", "groupIds": [], "soakHours": 12, "failPct": 5, "minSample": 4}]}
    saved = await api.call("PUT", f"{BASE}/rings", json=body)
    assert saved.status_code == 200
    assert [(r["name"], r["soakHours"]) for r in saved.json()["rings"]] == [("Canary", 2), ("Everyone", 12)]
    assert (await api.call("GET", f"{BASE}/rings")).json()["rings"][1]["failPct"] == 5
    bad = await api.call("PUT", f"{BASE}/rings", json={"rings": [{"name": "Canary", "groupIds": ["G1"], "soakHours": 0},
                                                                  {"name": "R", "groupIds": []}]})
    assert bad.status_code == 422 and bad.json()["detail"] == "Enter hours between 1 and 168."
    lonely = await api.call("PUT", f"{BASE}/rings", json={"rings": [{"name": "Canary", "groupIds": []},
                                                                      {"name": "R", "groupIds": []}]})
    assert lonely.status_code == 422 and lonely.json()["detail"] == "Pick at least one group for the Canary ring."
    foreign = await api.call("PUT", f"{BASE}/rings", json={"rings": [{"name": "Canary", "groupIds": ["nope"]},
                                                                       {"name": "R", "groupIds": []}]})
    assert foreign.status_code == 422


# ---------------------------------------------------------------- Start body

async def test_the_start_body_is_checked_and_extra_fields_are_ignored(api):
    await put_agent(api.db, "a1", group="G1")
    for body in ({"name": "", "patchIds": ["openssl"]}, {"name": "x" * 61, "patchIds": ["openssl"]},
                 {"name": "ok", "patchIds": []}, {"name": "ok", "patchIds": ["p"] * 201},
                 {"name": "ok", "patchIds": [5]}, {"patchIds": ["openssl"]}):
        assert (await api.call("POST", BASE, json=body)).status_code == 422
    made = await api.call("POST", BASE, json={"name": " Nov ", "patchIds": ["openssl"], "shadow": True, "x": 1})
    assert made.status_code == 201 and made.json()["name"] == "Nov"
