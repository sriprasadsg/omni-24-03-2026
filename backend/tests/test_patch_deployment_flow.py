"""
OS patch deployment, end to end on the platform side: what /api/patches/deploy and
/api/patches/apply-os-patches queue, how agents' results finish a job, and how the
scheduler releases scheduled jobs.

Before this, a deployment of CVE records (the whole patch catalog) or to assets with
no agent still produced a job, and a progress animation marked every immediate job
"Completed" a few seconds later whatever the agents did. A small in-memory store
stands in for MongoDB because these flows need state across several calls.
"""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from auth_types import TokenData
from authentication_service import get_current_user


def _match(doc, flt):
    for k, v in (flt or {}).items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and "$lte" in v:
            if doc.get(k) is None or doc.get(k) > v["$lte"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, length=None):
        return list(self._docs)


class _Col:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in docs or []]

    def find(self, flt=None, projection=None):
        return _Cursor([dict(d) for d in self.docs if _match(d, flt)])

    async def find_one(self, flt=None, projection=None, **kw):
        return next((dict(d) for d in self.docs if _match(d, flt)), None)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def insert_many(self, docs, ordered=True):
        self.docs.extend(dict(d) for d in docs)

    def _apply(self, doc, update):
        for key, val in update.get("$set", {}).items():
            target, *path = key.split(".")
            if path:
                doc.setdefault(target, {})[path[0]] = val
            else:
                doc[target] = val
        for key, val in update.get("$push", {}).items():
            doc.setdefault(key, []).extend(val["$each"] if isinstance(val, dict) and "$each" in val else [val])

    async def update_one(self, flt, update):
        for d in self.docs:
            if _match(d, flt):
                self._apply(d, update)
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()

    async def update_many(self, flt, update):
        for d in self.docs:
            if _match(d, flt):
                self._apply(d, update)


class _DB:
    def __init__(self, **cols):
        for name in ("patches", "agents", "patch_deployment_jobs", "software_deployment_jobs",
                     "agent_instructions", "assets"):
            setattr(self, name, _Col(cols.get(name)))


AGENTS = [
    {"id": "agent-win", "tenantId": "t1", "hostname": "WIN1", "assetId": "asset-WIN1", "status": "Online"},
    {"id": "agent-lin", "tenantId": "t1", "hostname": "lin1", "status": "Offline"},
    {"id": "agent-gone", "tenantId": "t1", "hostname": "OLD1", "status": "Uninstalled"},
    {"id": "agent-other", "tenantId": "t2", "hostname": "WIN1", "status": "Online"},
]
CVE_PATCH = {"id": "CVE-2026-40079", "kb_number": None, "package_name": None, "name": "CVE-2026-40079"}


def _client(db, user):
    import patch_endpoints as mod
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app, db


def _post(db, user, path, body):
    app, _ = _client(db, user)
    with patch("patch_core_endpoints.get_database", return_value=db), \
         patch("patch_software_endpoints.get_database", return_value=db):
        with TestClient(app) as c:
            return c.post(path, json=body)


# ── which ids are installable ────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("kb5034441", "KB5034441"), ("openssl", "openssl"), ("libc6:amd64", "libc6:amd64"),
    ("CVE-2026-40079", None), ("CVE-2026-1", None), ("KB12", None), ("openssl; reboot", None),
    ("-o x", None), ("a b", None), ("", None), (None, None),
])
def test_installable_patch_id(raw, expected):
    from patch_core_endpoints import installable_patch_id
    assert installable_patch_id(raw) == expected


# ── /api/patches/deploy ──────────────────────────────────────────────────────

def test_deploying_only_cve_records_is_refused(admin_user):
    db = _DB(patches=[CVE_PATCH], agents=AGENTS)
    resp = _post(db, admin_user, "/api/patches/deploy",
                 {"patch_ids": ["CVE-2026-40079"], "asset_ids": ["asset-WIN1"], "deployment_type": "Immediate"})
    assert resp.status_code == 400
    assert "installable" in resp.text
    assert db.patch_deployment_jobs.docs == [] and db.agent_instructions.docs == []


def test_deploying_to_assets_without_an_agent_is_refused(admin_user):
    db = _DB(agents=AGENTS)
    for assets in (["asset-NOPE"], ["asset-OLD1"]):  # unknown, and an uninstalled agent
        resp = _post(db, admin_user, "/api/patches/deploy",
                     {"patch_ids": ["KB5034441"], "asset_ids": assets, "deployment_type": "Immediate"})
        assert resp.status_code == 400, assets
    assert db.patch_deployment_jobs.docs == []


def test_deploy_queues_installable_ids_on_the_callers_own_agents(admin_user):
    db = _DB(patches=[CVE_PATCH], agents=AGENTS)
    resp = _post(db, admin_user, "/api/patches/deploy", {
        "patch_ids": ["CVE-2026-40079", "kb5034441"], "asset_ids": ["asset-WIN1", "lin1"],
        "deployment_type": "Immediate"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    job = db.patch_deployment_jobs.docs[0]
    assert job["id"] == body["job_id"] == body["job"]["id"]
    assert job["patchIds"] == ["KB5034441"]
    assert job["skippedPatchIds"] == ["CVE-2026-40079"]
    # "asset-WIN1" resolves to t1's WIN1, never to tenant t2's agent with the same hostname.
    assert sorted(job["dispatchedAgents"]) == ["agent-lin", "agent-win"]
    assert job["status"] == "In Progress" and job["progress"] == 0
    instrs = db.agent_instructions.docs
    assert {i["agent_id"] for i in instrs} == {"agent-win", "agent-lin"}
    assert all(i["tenantId"] == "t1" and i["status"] == "pending" for i in instrs)
    assert all(i["payload"] == {"patch_ids": ["KB5034441"], "job_id": job["id"]} for i in instrs)


def test_scheduled_deploy_needs_a_time_and_holds_its_instructions(admin_user):
    db = _DB(agents=AGENTS)
    resp = _post(db, admin_user, "/api/patches/deploy",
                 {"patch_ids": ["openssl"], "asset_ids": ["lin1"], "deployment_type": "Scheduled"})
    assert resp.status_code == 400
    resp = _post(db, admin_user, "/api/patches/deploy", {
        "patch_ids": ["openssl"], "asset_ids": ["lin1"], "deployment_type": "Scheduled",
        "schedule_time": "2026-10-13T02:00:00+00:00"})
    assert resp.status_code == 200
    assert db.patch_deployment_jobs.docs[0]["status"] == "Scheduled"
    assert db.agent_instructions.docs[0]["status"] == "scheduled"


# ── /api/patches/apply-os-patches ────────────────────────────────────────────

def test_apply_os_patches_refuses_ids_that_are_not_installable(admin_user):
    db = _DB(agents=AGENTS)
    resp = _post(db, admin_user, "/api/patches/apply-os-patches",
                 {"agent_id": "agent-lin", "patch_ids": ["openssl", "CVE-2026-40079"]})
    assert resp.status_code == 400
    assert db.agent_instructions.docs == []


def test_apply_os_patches_creates_a_job_the_agent_can_report_to(admin_user):
    db = _DB(agents=AGENTS)
    resp = _post(db, admin_user, "/api/patches/apply-os-patches",
                 {"agent_id": "agent-win", "patch_ids": ["KB5034441"]})
    assert resp.status_code == 200, resp.text
    job = db.patch_deployment_jobs.docs[0]
    assert job["id"] == resp.json()["job_id"]
    assert job["dispatchedAgents"] == ["agent-win"]
    assert db.agent_instructions.docs[0]["job_id"] == job["id"]


# ── agents finish the job ────────────────────────────────────────────────────

def _result_app(db, agent_id):
    import deployment_result_endpoints as mod
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod._get_caller] = lambda: TokenData(username=agent_id, role="agent", tenant_id="t1")
    return app


def _report(db, agent_id, job_id, body):
    with patch("deployment_result_endpoints.get_database", return_value=db):
        with TestClient(_result_app(db, agent_id)) as c:
            return c.post(f"/api/deployments/{job_id}/result", json=body)


def _job_for(db, agents):
    from patch_core_endpoints import new_patch_job
    job = new_patch_job("job-9", "t1", ["KB5034441"], [], agents, "admin", "Immediate", None,
                        "2026-10-12T00:00:00+00:00", "In Progress")
    db.patch_deployment_jobs.docs.append(job)
    return job


def test_job_completes_only_when_every_dispatched_agent_has_reported():
    db = _DB()
    _job_for(db, ["agent-win", "agent-lin"])
    ok = {"status": "completed", "successful": 1, "failed": 0, "total": 1,
          "results": [{"patch_id": "KB5034441", "status": "success", "reboot_required": True}]}
    assert _report(db, "agent-win", "job-9", ok).json()["recorded"] == "In Progress"
    job = db.patch_deployment_jobs.docs[0]
    assert job["status"] == "In Progress" and job["progress"] == 50

    bad = {"status": "failed", "successful": 0, "failed": 1, "total": 1,
           "results": [{"patch_id": "KB5034441", "status": "failed", "message": "0x80240022"}]}
    assert _report(db, "agent-lin", "job-9", bad).json()["recorded"] == "Partially Completed"
    job = db.patch_deployment_jobs.docs[0]
    assert job["progress"] == 100 and job["rebootRequired"] is True
    assert set(job["agentResults"]) == {"agent-win", "agent-lin"}
    assert any("0x80240022" in e["message"] for e in job["statusLog"])


def test_an_agent_cannot_report_on_a_job_it_was_not_sent():
    db = _DB()
    _job_for(db, ["agent-win"])
    resp = _report(db, "agent-other", "job-9", {"status": "completed", "results": []})
    assert resp.status_code == 403
    assert db.patch_deployment_jobs.docs[0]["agentResults"] == {}


def test_an_agent_rejecting_the_instruction_fails_its_share_of_the_job():
    """An agent build without install_patches answers through the generic
    instruction-result endpoint; that must end the job instead of leaving it running."""
    import agent_tasks_endpoints as mod
    from agent_auth import verify_agent_key, CALLER_AGENT_KEY
    from patch_core_endpoints import patch_instruction
    db = _DB()
    job = _job_for(db, ["agent-win"])
    db.agent_instructions.docs.append(patch_instruction(job["id"], AGENTS[0], ["KB5034441"], "now"))
    task_id = db.agent_instructions.docs[0]["id"]
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[verify_agent_key] = lambda: {"id": "t1", CALLER_AGENT_KEY: "agent-win"}
    with patch("agent_tasks_endpoints.get_database", return_value=db), \
         patch("deployment_result_endpoints.get_database", return_value=db):
        with TestClient(app) as c:
            resp = c.post("/api/agents/WIN1/instructions/result", json={
                "task_id": task_id, "status": "error",
                "result": {"status": "error", "error": "Agent does not support instruction 'install_patches'"}})
    assert resp.status_code == 200
    job = db.patch_deployment_jobs.docs[0]
    assert job["status"] == "Failed" and job["progress"] == 100
    assert "does not support" in job["agentResults"]["agent-win"]["error"]


# ── the scheduler releases due jobs ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_releases_a_due_jobs_instructions():
    import scheduler
    from patch_core_endpoints import new_patch_job, patch_instruction
    db = _DB()
    db.patch_deployment_jobs.docs.append(new_patch_job(
        "job-s", "t1", ["openssl"], [], ["agent-lin"], "admin", "Scheduled",
        "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", "Scheduled"))
    db.agent_instructions.docs.append(patch_instruction("job-s", AGENTS[1], ["openssl"], "now",
                                                        "2026-01-01T00:00:00+00:00"))
    with patch.object(scheduler, "get_database", return_value=db), \
         patch.object(scheduler, "acquire_lock", AsyncMock(return_value="tok")), \
         patch.object(scheduler, "release_lock", AsyncMock()):
        await scheduler.process_scheduled_deployments()
    assert db.patch_deployment_jobs.docs[0]["status"] == "In Progress"
    assert db.agent_instructions.docs[0]["status"] == "pending"


# ── what the OS Patches tab offers ───────────────────────────────────────────

def test_pending_patch_ids_reads_both_agent_formats():
    from patch_software_endpoints import pending_patch_ids
    rust_windows = {"meta": {"system_patching": {"pending_updates": [
        {"title": "2026-10 Cumulative Update", "kb": "5034441", "severity": "Critical"},
        {"title": "Defender definitions", "id": "KB2267602"},
        {"title": "No KB at all"}]}}}
    ids, details = pending_patch_ids(rust_windows)
    assert ids == ["KB5034441", "KB2267602"]
    assert details[0] == {"id": "KB5034441", "title": "2026-10 Cumulative Update", "severity": "Critical"}

    python_linux = {"meta": {"os_patches": {"items": ["openssl", "openssl", "bad name"]},
                             "system_patching": {"pending_updates": [{"id": "curl", "package": "curl"}]}}}
    assert pending_patch_ids(python_linux)[0] == ["curl", "openssl"]


# ── rolling a finished job back ──────────────────────────────────────────────

def test_rollback_targets_only_what_each_agent_installed(admin_user):
    db = _DB(agents=AGENTS)
    job = _job_for(db, ["agent-win", "agent-lin"])
    job.update({"status": "Partially Completed", "agentResults": {
        "agent-win": {"status": "Completed", "results": [{"patch_id": "KB5034441", "status": "success"}]},
        "agent-lin": {"status": "Failed", "results": [{"patch_id": "openssl", "status": "failed"}]},
    }})
    resp = _post(db, admin_user, "/api/patches/deployment-jobs/job-9/rollback", {})
    assert resp.status_code == 200, resp.text
    rb = db.patch_deployment_jobs.docs[-1]
    assert rb["type"] == "Patch Rollback" and rb["rollbackOf"] == "job-9"
    assert rb["dispatchedAgents"] == ["agent-win"]
    (instr,) = db.agent_instructions.docs
    assert instr["instruction"] == "rollback_patches" and instr["type"] == "os_patch_rollback"
    assert instr["payload"] == {"patch_ids": ["KB5034441"], "job_id": rb["id"]}


def test_rollback_refuses_running_jobs_and_jobs_that_installed_nothing(admin_user):
    db = _DB(agents=AGENTS)
    job = _job_for(db, ["agent-lin"])
    assert _post(db, admin_user, "/api/patches/deployment-jobs/job-9/rollback", {}).status_code == 409
    job.update({"status": "Failed", "agentResults": {
        "agent-lin": {"status": "Failed", "results": [{"patch_id": "openssl", "status": "failed"}]}}})
    assert _post(db, admin_user, "/api/patches/deployment-jobs/job-9/rollback", {}).status_code == 400
    assert db.agent_instructions.docs == []


def test_rollback_of_another_tenants_job_is_not_found(admin_user):
    db = _DB(agents=AGENTS)
    job = _job_for(db, ["agent-other"])
    job.update({"tenantId": "t2", "status": "Completed"})
    assert _post(db, admin_user, "/api/patches/deployment-jobs/job-9/rollback", {}).status_code == 404


def test_a_super_admin_job_cannot_span_tenants(super_admin_user):
    db = _DB(agents=AGENTS)
    resp = _post(db, super_admin_user, "/api/patches/deploy", {
        "patch_ids": ["KB5034441"], "asset_ids": ["agent-win", "agent-other"], "deployment_type": "Immediate"})
    assert resp.status_code == 400
    assert "one tenant" in resp.text
    resp = _post(db, super_admin_user, "/api/patches/deploy", {
        "patch_ids": ["KB5034441"], "asset_ids": ["agent-other"], "deployment_type": "Immediate"})
    assert resp.status_code == 200
    # Filed under the agent's tenant, where the agent polls and reports.
    assert db.patch_deployment_jobs.docs[0]["tenantId"] == "t2"
    assert db.agent_instructions.docs[0]["tenantId"] == "t2"
