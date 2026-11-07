"""Staged patch rollouts, plan 84-04, task 3: the legacy staged-deployment revert is fenced (research C8, T-84-13).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=PROH-84-07a / T-84-13: the old staged-deployment revert wrote ungated rollback_patches
instructions straight into agent_instructions (no stop, no window, no approval, no ledger); it now writes nothing,
whether a person asks for it on the route or a failed stage asks for it automatically; fails_when=any document
reaches agent_instructions or rollback_jobs from the legacy revert, the route answers anything but 409 with a
pointer to Rollouts, or a failed stage raises instead of staying failed; no_claim=the Patching screen text and a
real agent.
"""
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import deployment_endpoints
import deployment_service
from deployment_service import DeploymentStage, LegacyRevertRetired, PatchDeploymentService
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

DETAIL = ("This old staged deployment can't revert patches. Use Rollouts on the Patching screen: "
          "a rollout halts on failure and reverts where supported.")


async def seed(db, *, tenant="t1", deployment_id="deploy-staged-1", success=True):
    """A staged deployment whose test stage patched one computer that has an agent."""
    await db.agents.insert_one({"id": "a1", "tenantId": tenant, "hostname": "h1", "assetId": "asset-1"})
    await db.staged_deployments.insert_one({
        "id": deployment_id, "type": "staged_deployment", "tenant_id": tenant, "patch_ids": ["KB1"],
        "status": "in_progress", "current_stage": DeploymentStage.TEST,
        "config": {"rollback_on_failure": True, "failure_threshold": 0.10},
        "stages": [{"stage": DeploymentStage.TEST, "status": "in_progress", "asset_ids": ["asset-1"], "asset_count": 1,
                    "success_count": 0, "failure_count": 0,
                    "test_results": [{"asset_id": "asset-1", "success": success}] if success else []}]})
    return deployment_id


async def nothing_written(db):
    assert await db.agent_instructions.count_documents({}) == 0
    assert await db.rollback_jobs.count_documents({}) == 0


async def test_trigger_rollback_refuses_and_writes_no_instruction(mongo_db):
    """fails_when=the retired revert still queues a rollback_patches instruction for the agent."""
    deployment_id = await seed(mongo_db)
    with pytest.raises(LegacyRevertRetired):
        await PatchDeploymentService(mongo_db).trigger_rollback(deployment_id, "operator asked")
    await nothing_written(mongo_db)
    assert (await mongo_db.staged_deployments.find_one({"id": deployment_id}))["status"] == "in_progress"


async def test_a_failed_stage_stays_failed_and_asks_for_no_revert(mongo_db):
    """The automatic path (rollback_on_failure) used to call the revert; it must neither raise nor write."""
    deployment_id = await seed(mongo_db, success=False)
    stage = await PatchDeploymentService(mongo_db).update_stage_progress(
        deployment_id, DeploymentStage.TEST, "asset-1", False)
    assert stage["status"] == deployment_service.StageStatus.FAILED
    saved = await mongo_db.staged_deployments.find_one({"id": deployment_id})
    assert saved["status"] == "failed" and saved["stages"][0]["failure_count"] == 1
    await nothing_written(mongo_db)


async def test_the_route_answers_409_with_a_pointer_to_rollouts(mongo_db, monkeypatch):
    deployment_id = await seed(mongo_db)
    monkeypatch.setattr(deployment_endpoints, "get_database", lambda: mongo_db)
    monkeypatch.setattr(deployment_endpoints, "get_tenant_id", lambda: "t1")
    with pytest.raises(HTTPException) as caught:
        await deployment_endpoints.rollback_deployment(deployment_id, {"reason": "x"},
                                                       current_user=type("U", (), {"username": "alice"})())
    assert caught.value.status_code == 409 and caught.value.detail == DETAIL
    await nothing_written(mongo_db)


async def test_the_read_routes_and_the_screen_keep_working(mongo_db, monkeypatch):
    """The fence removes only the revert: the deployment can still be read."""
    deployment_id = await seed(mongo_db)
    found = await PatchDeploymentService(mongo_db).get_deployment(deployment_id)
    assert found["id"] == deployment_id and found["patch_ids"] == ["KB1"]


# ── WR-10 (plan 84-24): the manual per-job Rollback route refuses a rollout's own jobs ──────────────────────

import patch_core_endpoints  # noqa: E402

ROLLOUT_JOB_DETAIL = "This job belongs to a rollout. Revert it from Rollouts on the Patching screen."


def operator(tenant="t1", role="Tenant Admin"):
    return type("U", (), {"username": "alice", "role": role, "tenant_id": tenant})()


async def seed_job(db, *, tenant="t1", job_id="job-1", rollout_id=None, job_type="Patch Deployment"):
    """A finished job whose one agent reported KB5034441 installed."""
    await db.agents.insert_one({"id": "a1", "tenantId": tenant, "hostname": "h1", "status": "online"})
    job = patch_core_endpoints.new_patch_job(job_id, tenant, ["KB5034441"], [], ["a1"], "bob", "Immediate", None,
                                             "2026-11-07T00:00:00+00:00", "Completed")
    job["agentResults"] = {"a1": {"status": "Completed", "results": [{"patch_id": "KB5034441", "status": "success"}]}}
    job["type"] = job_type
    if rollout_id:
        job["rolloutId"] = rollout_id
    await db.patch_deployment_jobs.insert_one(job)
    return job_id


async def roll_back(db, monkeypatch, job_id, user=None):
    monkeypatch.setattr(patch_core_endpoints, "get_database", lambda: db)
    return await patch_core_endpoints.rollback_patch_job(job_id, current_user=user or operator())


async def test_a_rollout_install_job_is_refused_with_409_and_queues_nothing(mongo_db, monkeypatch):
    """fails_when=the manual route queues a rollback for a job that carries rolloutId (WR-10, T-84-68)."""
    job_id = await seed_job(mongo_db, rollout_id="ro-1")
    with pytest.raises(HTTPException) as caught:
        await roll_back(mongo_db, monkeypatch, job_id)
    assert caught.value.status_code == 409 and caught.value.detail == ROLLOUT_JOB_DETAIL
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.patch_deployment_jobs.count_documents({}) == 1


async def test_a_rollout_revert_job_is_refused_with_409_and_queues_nothing(mongo_db, monkeypatch):
    job_id = await seed_job(mongo_db, rollout_id="ro-1", job_type=patch_core_endpoints.ROLLBACK_JOB_TYPE)
    with pytest.raises(HTTPException) as caught:
        await roll_back(mongo_db, monkeypatch, job_id)
    assert caught.value.status_code == 409 and caught.value.detail == ROLLOUT_JOB_DETAIL
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.patch_deployment_jobs.count_documents({}) == 1


async def test_an_ordinary_job_still_rolls_back(mongo_db, monkeypatch):
    """Manual patching is unchanged: a finished job with no rolloutId queues its rollback_patches instruction."""
    job_id = await seed_job(mongo_db)
    out = await roll_back(mongo_db, monkeypatch, job_id)
    assert out["success"] is True and out["job"]["rollbackOf"] == job_id
    (instruction,) = [d async for d in mongo_db.agent_instructions.find({})]
    assert instruction["instruction"] == "rollback_patches" and instruction["agent_id"] == "a1"
    assert instruction["payload"]["patch_ids"] == ["KB5034441"]


async def test_another_tenants_rollout_job_answers_with_the_existing_denial(mongo_db, monkeypatch):
    """The tenant check stays first, so a caller from another tenant learns nothing about rolloutId."""
    job_id = await seed_job(mongo_db, tenant="t2", rollout_id="ro-1")
    with pytest.raises(HTTPException) as caught:
        await roll_back(mongo_db, monkeypatch, job_id, user=operator(tenant="t1"))
    assert caught.value.status_code == 404 and caught.value.detail == "Patch deployment job not found"
    assert await mongo_db.agent_instructions.count_documents({}) == 0
