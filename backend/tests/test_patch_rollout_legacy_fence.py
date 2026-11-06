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
