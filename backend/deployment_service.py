"""
Patch Deployment Service - Staged Rollout & Approval Workflow
Handles test environments, phased deployment, and rollback capabilities
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
from maintenance_service import get_maintenance_service


class DeploymentStage(str, Enum):
    """Deployment stage enumeration"""
    TEST = "test"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class StageStatus(str, Enum):
    """Stage deployment status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    AWAITING_APPROVAL = "awaiting_approval"


class ApprovalStatus(str, Enum):
    """Approval status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PatchDeploymentService:
    """Manages staged patch deployment with approval workflows"""
    
    def __init__(self, db):
        self.db = db
    
    async def create_staged_deployment(
        self,
        patch_ids: List[str],
        asset_ids: List[str],
        tenant_id: str,
        created_by: str,
        deployment_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a multi-stage patch deployment job
        
        Stages:
        1. Test (5% of assets or test environment)
        2. Dev (additional 10%)
        3. Staging (additional 20%)
        4. Production (remaining 65%)
        
        Each stage requires approval before proceeding
        """
        
        # Check Maintenance Window
        m_service = get_maintenance_service(self.db)
        is_in_window = await m_service.is_in_maintenance_window(tenant_id)
        
        enforce = (deployment_config or {}).get("enforce_maintenance_window", True)
        if not is_in_window and enforce:
            raise ValueError("Deployment attempted outside of an active maintenance window.")

        # Default configuration
        config = {
            "stage_percentages": {
                DeploymentStage.TEST: 0.05,
                DeploymentStage.DEV: 0.10,
                DeploymentStage.STAGING: 0.20,
                DeploymentStage.PRODUCTION: 0.65
            },
            "auto_progress": False,  # Require manual approval between stages
            "rollback_on_failure": True,
            "health_check_enabled": True,
            "failure_threshold": 0.10  # Rollback if >10% fail
        }
        
        if deployment_config:
            config.update(deployment_config)
        
        # Categorize assets by environment
        assets = await self.db.assets.find(
            {"id": {"$in": asset_ids}},
            {"_id": 0}
        ).to_list(length=None)
        
        # Separate test environment assets
        test_assets = [a for a in assets if a.get("environment") == "test"]
        non_test_assets = [a for a in assets if a.get("environment") != "test"]
        
        # Create stage asset allocation
        total_non_test = len(non_test_assets)
        stage_allocation = {
            DeploymentStage.TEST: test_assets if test_assets else non_test_assets[:max(1, int(total_non_test * 0.05))],
            DeploymentStage.DEV: non_test_assets[:int(total_non_test * 0.15)],  # Cumulative 15%
            DeploymentStage.STAGING: non_test_assets[:int(total_non_test * 0.35)],  # Cumulative 35%
            DeploymentStage.PRODUCTION: non_test_assets  # All assets
        }
        
        # Create deployment job
        deployment_id = f"deploy-staged-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        deployment_job = {
            "id": deployment_id,
            "type": "staged_deployment",
            "tenant_id": tenant_id,
            "patch_ids": patch_ids,
            "all_asset_ids": asset_ids,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "in_progress",
            "current_stage": DeploymentStage.TEST,
            "config": config,
            "stages": []
        }
        
        # Create stage definitions
        for stage in [DeploymentStage.TEST, DeploymentStage.DEV, DeploymentStage.STAGING, DeploymentStage.PRODUCTION]:
            stage_assets = [a["id"] for a in stage_allocation[stage]]
            
            stage_def = {
                "stage": stage,
                "status": StageStatus.PENDING if stage != DeploymentStage.TEST else StageStatus.IN_PROGRESS,
                "asset_ids": stage_assets,
                "asset_count": len(stage_assets),
                "started_at": datetime.now(timezone.utc).isoformat() if stage == DeploymentStage.TEST else None,
                "completed_at": None,
                "success_count": 0,
                "failure_count": 0,
                "approval_required": True,
                "approval_status": ApprovalStatus.PENDING if stage != DeploymentStage.TEST else None,
                "approved_by": None,
                "approved_at": None,
                "test_results": []
            }
            
            deployment_job["stages"].append(stage_def)
        
        # Save to database
        await self.db.staged_deployments.insert_one(deployment_job)
        
        return deployment_job
    
    async def get_deployment(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """Get deployment job by ID"""
        return await self.db.staged_deployments.find_one({"id": deployment_id}, {"_id": 0})
    
    async def update_stage_progress(
        self,
        deployment_id: str,
        stage: DeploymentStage,
        asset_id: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update progress for a specific asset in a stage
        Checks if stage should be marked complete
        Triggers auto-rollback if failure threshold exceeded
        """
        deployment = await self.get_deployment(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")
        
        # Find the stage
        stage_idx = next((i for i, s in enumerate(deployment["stages"]) if s["stage"] == stage), None)
        if stage_idx is None:
            raise ValueError(f"Stage {stage} not found in deployment")
        
        stage_data = deployment["stages"][stage_idx]
        
        # Update counts
        if success:
            stage_data["success_count"] += 1
        else:
            stage_data["failure_count"] += 1
        
        # Add test result
        stage_data["test_results"].append({
            "asset_id": asset_id,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {}
        })
        
        total_processed = stage_data["success_count"] + stage_data["failure_count"]
        total_assets = stage_data["asset_count"]
        
        # Check if stage is complete
        if total_processed >= total_assets:
            stage_data["status"] = StageStatus.COMPLETED
            stage_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            
            # Calculate success rate
            success_rate = stage_data["success_count"] / total_assets if total_assets > 0 else 0
            
            # Check if rollback needed
            if success_rate < (1 - deployment["config"]["failure_threshold"]):
                stage_data["status"] = StageStatus.FAILED
                deployment["status"] = "failed"
                
                if deployment["config"]["rollback_on_failure"]:
                    await self.trigger_rollback(deployment_id, f"Stage {stage} failed - success rate {success_rate:.1%}")
        
        # Update in database
        await self.db.staged_deployments.update_one(
            {"id": deployment_id},
            {"$set": {
                f"stages.{stage_idx}": stage_data,
                "status": deployment["status"]
            }}
        )
        
        return stage_data
    
    async def request_approval(
        self,
        deployment_id: str,
        stage: DeploymentStage,
        approvers: List[str]
    ) -> Dict[str, Any]:
        """
        Create an approval request for proceeding to next stage
        """
        approval_id = f"approval-{deployment_id}-{stage}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        approval_request = {
            "id": approval_id,
            "deployment_id": deployment_id,
            "stage": stage,
            "status": ApprovalStatus.PENDING,
            "approvers": approvers,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc).timestamp() + (24 * 3600)),  # 24 hours
            "approved_by": None,
            "approved_at": None,
            "rejection_reason": None
        }
        
        await self.db.deployment_approvals.insert_one(approval_request)
        
        # Update stage status
        deployment = await self.get_deployment(deployment_id)
        stage_idx = next((i for i, s in enumerate(deployment["stages"]) if s["stage"] == stage), None)
        
        if stage_idx is not None:
            await self.db.staged_deployments.update_one(
                {"id": deployment_id},
                {"$set": {
                    f"stages.{stage_idx}.status": StageStatus.AWAITING_APPROVAL,
                    f"stages.{stage_idx}.approval_id": approval_id
                }}
            )
        
        return approval_request
    
    async def approve_stage(
        self,
        approval_id: str,
        approved_by: str,
        comments: Optional[str] = None
    ) -> Dict[str, Any]:
        """Approve a stage and progress to next stage"""
        approval = await self.db.deployment_approvals.find_one({"id": approval_id}, {"_id": 0})
        
        if not approval:
            raise ValueError(f"Approval {approval_id} not found")
        
        if approval["status"] != ApprovalStatus.PENDING:
            raise ValueError(f"Approval already {approval['status']}")
        
        # Check if expired
        if datetime.now(timezone.utc).timestamp() > approval["expires_at"]:
            approval["status"] = ApprovalStatus.EXPIRED
            await self.db.deployment_approvals.update_one(
                {"id": approval_id},
                {"$set": {"status": ApprovalStatus.EXPIRED}}
            )
            raise ValueError("Approval has expired")
        
        # Update approval
        approval["status"] = ApprovalStatus.APPROVED
        approval["approved_by"] = approved_by
        approval["approved_at"] = datetime.now(timezone.utc).isoformat()
        approval["comments"] = comments
        
        await self.db.deployment_approvals.update_one(
            {"id": approval_id},
            {"$set": approval}
        )
        
        # Progress deployment to next stage
        deployment_id = approval["deployment_id"]
        current_stage = approval["stage"]
        
        await self.progress_to_next_stage(deployment_id, current_stage)
        
        return approval
    
    async def reject_stage(
        self,
        approval_id: str,
        rejected_by: str,
        reason: str
    ) -> Dict[str, Any]:
        """Reject a stage approval and halt deployment"""
        approval = await self.db.deployment_approvals.find_one({"id": approval_id}, {"_id": 0})
        
        if not approval:
            raise ValueError(f"Approval {approval_id} not found")
        
        approval["status"] = ApprovalStatus.REJECTED
        approval["approved_by"] = rejected_by
        approval["approved_at"] = datetime.now(timezone.utc).isoformat()
        approval["rejection_reason"] = reason
        
        await self.db.deployment_approvals.update_one(
            {"id": approval_id},
            {"$set": approval}
        )
        
        # Halt deployment
        deployment_id = approval["deployment_id"]
        await self.db.staged_deployments.update_one(
            {"id": deployment_id},
            {"$set": {"status": "rejected"}}
        )
        
        return approval
    
    async def progress_to_next_stage(
        self,
        deployment_id: str,
        current_stage: DeploymentStage
    ) -> Dict[str, Any]:
        """Progress deployment to next stage"""
        deployment = await self.get_deployment(deployment_id)
        
        stage_order = [DeploymentStage.TEST, DeploymentStage.DEV, DeploymentStage.STAGING, DeploymentStage.PRODUCTION]
        current_idx = stage_order.index(current_stage)
        
        if current_idx >= len(stage_order) - 1:
            # Final stage completed
            await self.db.staged_deployments.update_one(
                {"id": deployment_id},
                {"$set": {"status": "completed"}}
            )
            return deployment
        
        next_stage = stage_order[current_idx + 1]
        next_stage_idx = current_idx + 1
        
        # Update next stage to in_progress
        await self.db.staged_deployments.update_one(
            {"id": deployment_id},
            {"$set": {
                f"stages.{next_stage_idx}.status": StageStatus.IN_PROGRESS,
                f"stages.{next_stage_idx}.started_at": datetime.now(timezone.utc).isoformat(),
                "current_stage": next_stage
            }}
        )
        
        return await self.get_deployment(deployment_id)
    
    async def trigger_rollback(
        self,
        deployment_id: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        Trigger rollback of deployment
        Creates rollback tasks for all successfully patched assets
        """
        deployment = await self.get_deployment(deployment_id)
        
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")
        
        # Collect all successfully patched assets
        rolled_back_assets = []
        for stage in deployment["stages"]:
            for result in stage.get("test_results", []):
                if result["success"]:
                    rolled_back_assets.append(result["asset_id"])
        
        # Create rollback job
        rollback_id = f"rollback-{deployment_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        rollback_job = {
            "id": rollback_id,
            "deployment_id": deployment_id,
            "asset_ids": rolled_back_assets,
            "patch_ids": deployment["patch_ids"],
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "in_progress",
            "tenant_id": deployment["tenant_id"]
        }
        
        await self.db.rollback_jobs.insert_one(rollback_job)
        
        # Queue instructions for agents
        for asset_id in rolled_back_assets:
            # Find agent for this asset
            agent = await self.db.agents.find_one({"assetId": asset_id})
            if agent:
                instruction_id = f"instr-rollback-{uuid.uuid4()}"
                instruction = {
                    "id": instruction_id,
                    "agent_id": agent["id"],
                    "type": "rollback_patches",
                    "instruction": f"Rollback patches: {', '.join(deployment['patch_ids'])}",
                    "patches": deployment["patch_ids"],
                    "job_id": rollback_id,
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await self.db.agent_instructions.insert_one(instruction)
                print(f"[Rollback] Queued instruction {instruction_id} for agent {agent['id']}")

        # Update deployment status
        await self.db.staged_deployments.update_one(
            {"id": deployment_id},
            {"$set": {
                "status": "rolled_back",
                "rollback_id": rollback_id,
                "rollback_reason": reason,
                "rolled_back_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return rollback_job


def get_deployment_service(db):
    """Get deployment service instance"""
    return PatchDeploymentService(db)
