"""
Policy Engine Service - Automated Patch Deployment Rules
Handles policy-based automation, scheduling, and conditional deployment
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import aiohttp
import json


class PolicyTrigger(str, Enum):
    """Policy trigger types"""
    SEVERITY = "severity"
    CVSS_SCORE = "cvss_score"
    EPSS_SCORE = "epss_score"
    AGE = "age"
    ASSET_GROUP = "asset_group"
    COMPLIANCE_SLA = "compliance_sla"
    SCHEDULE = "schedule"


class PolicyAction(str, Enum):
    """Policy actions"""
    AUTO_DEPLOY = "auto_deploy"
    AUTO_DEPLOY_STAGED = "auto_deploy_staged"
    REQUEST_APPROVAL = "request_approval"
    NOTIFY_ONLY = "notify_only"
    QUARANTINE = "quarantine"


class PatchPolicyEngine:
    """Automated policy-based patch deployment engine"""
    
    def __init__(self, db):
        self.db = db
    
    async def create_policy(
        self,
        name: str,
        tenant_id: str,
        conditions: Dict[str, Any],
        actions: List[Dict[str, Any]],
        enabled: bool = True,
        priority: int = 0
    ) -> Dict[str, Any]:
        """
        Create a new patch policy
        
        Example conditions:
        {
            "severity": ["Critical", "High"],
            "cvss_score": {"min": 7.0},
            "epss_score": {"min": 0.5},
            "asset_groups": ["production_servers"],
            "max_age_days": 7
        }
        
        Example actions:
        [
            {
                "type": "auto_deploy_staged",
                "config": {
                    "test_first": true,
                    "require_approval": false,
                    "schedule": "maintenance_window"
                }
            },
            {
                "type": "notify_only",
                "config": {
                    "recipients": ["security@company.com"],
                    "channels": ["email", "slack"]
                }
            }
        ]
        """
        policy_id = f"policy-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        policy = {
            "id": policy_id,
            "name": name,
            "tenant_id": tenant_id,
            "conditions": conditions,
            "actions": actions,
            "enabled": enabled,
            "priority": priority,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "execution_count": 0,
            "last_executed": None
        }
        
        await self.db.patch_policies.insert_one(policy)
        return policy
    
    async def evaluate_patch_against_policies(
        self,
        patch: Dict[str, Any],
        tenant_id: str
    ) -> List[Dict[str, Any]]:
        """
        Evaluate a patch against all active policies
        Returns list of matching policies with their actions
        """
        # Get all enabled policies for tenant, sorted by priority
        policies = await self.db.patch_policies.find(
            {"tenant_id": tenant_id, "enabled": True},
            {"_id": 0}
        ).sort("priority", -1).to_list(length=None)
        
        matching_policies = []
        
        for policy in policies:
            if await self._matches_conditions(patch, policy["conditions"]):
                matching_policies.append(policy)
        
        return matching_policies
    
    async def _matches_conditions(
        self,
        patch: Dict[str, Any],
        conditions: Dict[str, Any]
    ) -> bool:
        """Check if patch matches policy conditions"""
        
        # Severity check
        if "severity" in conditions:
            if patch.get("severity") not in conditions["severity"]:
                return False
        
        # CVSS score check
        if "cvss_score" in conditions:
            cvss = patch.get("cvss_score", 0)
            if "min" in conditions["cvss_score"] and cvss < conditions["cvss_score"]["min"]:
                return False
            if "max" in conditions["cvss_score"] and cvss > conditions["cvss_score"]["max"]:
                return False
        
        # EPSS score check
        if "epss_score" in conditions:
            epss = patch.get("epss_score", 0)
            if "min" in conditions["epss_score"] and epss < conditions["epss_score"]["min"]:
                return False
            if "max" in conditions["epss_score"] and epss > conditions["epss_score"]["max"]:
                return False
        
        # Priority score check
        if "priority_score" in conditions:
            priority = patch.get("priority_score", 0)
            if "min" in conditions["priority_score"] and priority < conditions["priority_score"]["min"]:
                return False
        
        # Patch age check
        if "max_age_days" in conditions:
            if patch.get("createdAt"):
                created = datetime.fromisoformat(patch["createdAt"])
                age_days = (datetime.now(timezone.utc) - created).days
                if age_days > conditions["max_age_days"]:
                    return False
        
        # Asset group check
        if "asset_groups" in conditions:
            # Get assets for this patch
            patch_asset_ids = set(patch.get("affectedAssets", []))
            
            # Check if any assets match the required groups
            for group in conditions["asset_groups"]:
                assets = await self.db.assets.find(
                    {"group": group, "id": {"$in": list(patch_asset_ids)}},
                    {"_id": 0, "id": 1}
                ).to_list(length=None)
                
                if not assets:
                    return False
        
        # Compliance SLA check
        if "compliance_framework" in conditions:
            framework = conditions["compliance_framework"]
            sla_hours = patch.get("sla_hours")
            
            if sla_hours:
                created = datetime.fromisoformat(patch.get("createdAt", datetime.now(timezone.utc).isoformat()))
                deadline = created + timedelta(hours=sla_hours)
                
                # Check if approaching SLA
                time_remaining = (deadline - datetime.now(timezone.utc)).total_seconds() / 3600
                
                if "sla_threshold_hours" in conditions:
                    if time_remaining > conditions["sla_threshold_hours"]:
                        return False
        
        return True
    
    async def execute_policy_actions(
        self,
        patch: Dict[str, Any],
        policy: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Execute all actions defined in a policy
        Returns list of execution results
        """
        results = []
        
        for action in policy["actions"]:
            try:
                result = await self._execute_action(patch, action, policy["tenant_id"])
                results.append({
                    "action": action["type"],
                    "success": True,
                    "result": result
                })
            except Exception as e:
                results.append({
                    "action": action["type"],
                    "success": False,
                    "error": str(e)
                })
        
        # Update policy execution stats
        await self.db.patch_policies.update_one(
            {"id": policy["id"]},
            {
                "$set": {"last_executed": datetime.now(timezone.utc).isoformat()},
                "$inc": {"execution_count": 1}
            }
        )
        
        return results
    
    async def _execute_action(
        self,
        patch: Dict[str, Any],
        action: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Execute a single policy action"""
        
        action_type = action["type"]
        config = action.get("config", {})
        
        if action_type == PolicyAction.AUTO_DEPLOY:
            # Immediate auto-deployment
            return await self._auto_deploy_patch(patch, config, tenant_id)
        
        elif action_type == PolicyAction.AUTO_DEPLOY_STAGED:
            # Staged auto-deployment
            return await self._auto_deploy_staged(patch, config, tenant_id)
        
        elif action_type == PolicyAction.REQUEST_APPROVAL:
            # Create approval request
            return await self._request_manual_approval(patch, config, tenant_id)
        
        elif action_type == PolicyAction.NOTIFY_ONLY:
            # Send notifications
            return await self._send_notifications(patch, config, tenant_id)
        
        elif action_type == PolicyAction.QUARANTINE:
            # Mark patch for manual review
            return await self._quarantine_patch(patch, config, tenant_id)
        
        else:
            raise ValueError(f"Unknown action type: {action_type}")
    
    async def _auto_deploy_patch(
        self,
        patch: Dict[str, Any],
        config: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Deploy patch immediately"""
        from deployment_service import get_deployment_service
        
        # Get affected assets
        asset_ids = patch.get("affectedAssets", [])
        
        # Apply group filter if specified
        if config.get("asset_groups"):
            assets = await self.db.assets.find(
                {
                    "id": {"$in": asset_ids},
                    "group": {"$in": config["asset_groups"]}
                },
                {"_id": 0, "id": 1}
            ).to_list(length=None)
            asset_ids = [a["id"] for a in assets]
        
        # Create deployment job
        job_id = f"auto-deploy-{patch['id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        deployment_job = {
            "id": job_id,
            "type": "immediate",
            "tenant_id": tenant_id,
            "patch_ids": [patch["id"]],
            "asset_ids": asset_ids,
            "status": "scheduled",
            "created_by": "policy_engine",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scheduled_for": config.get("schedule", "immediate")
        }
        
        await self.db.patch_deployment_jobs.insert_one(deployment_job)
        
        return {
            "deployment_id": job_id,
            "asset_count": len(asset_ids),
            "scheduled_for": deployment_job["scheduled_for"]
        }
    
    async def _auto_deploy_staged(
        self,
        patch: Dict[str, Any],
        config: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Deploy patch using staged deployment"""
        from deployment_service import get_deployment_service
        
        deployment_service = get_deployment_service(self.db)
        
        asset_ids = patch.get("affectedAssets", [])
        
        deployment = await deployment_service.create_staged_deployment(
            patch_ids=[patch["id"]],
            asset_ids=asset_ids,
            tenant_id=tenant_id,
            created_by="policy_engine",
            deployment_config={
                "auto_progress": config.get("auto_progress", False),
                "rollback_on_failure": config.get("rollback_on_failure", True),
                "failure_threshold": config.get("failure_threshold", 0.10)
            }
        )
        
        return {
            "deployment_id": deployment["id"],
            "type": "staged",
            "stages": len(deployment["stages"])
        }
    
    async def _request_manual_approval(
        self,
        patch: Dict[str, Any],
        config: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Create manual approval request"""
        
        approval_id = f"approval-{patch['id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        approval = {
            "id": approval_id,
            "type": "manual_patch_approval",
            "patch_id": patch["id"],
            "tenant_id": tenant_id,
            "status": "pending",
            "approvers": config.get("approvers", []),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc).timestamp() + (config.get("expiry_hours", 48) * 3600))
        }
        
        await self.db.manual_approvals.insert_one(approval)
        
        # Send notification to approvers
        if config.get("approvers"):
            from email_service import email_service
            smtp_config = await self.db.smtp_config.find_one({"tenant_id": tenant_id})
            
            if smtp_config:
                email_service.send_alert_notification(
                    smtp_config=smtp_config,
                    recipients=config["approvers"],
                    alert={
                        "title": f"Approval Required: Patch {patch.get('name')}",
                        "severity": "High",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "asset": f"Patch ID: {patch['id']}",
                        "description": f"A patch requires your approval before deployment.\nPolicy: {config.get('policy_name', 'Manual Approval Policy')}",
                        "recommendations": f"Please review and approve via the dashboard.\nExpires at: {datetime.fromtimestamp(approval['expires_at'], timezone.utc)}"
                    }
                )
        
        return {"approval_id": approval_id}
    
    async def _send_notifications(
        self,
        patch: Dict[str, Any],
        config: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Send notifications about patch"""
        
        # Prepare notification message
        message = f"New patch available: {patch.get('name')}\n"
        message += f"Severity: {patch.get('severity')}\n"
        message += f"CVSS: {patch.get('cvss_score', 'N/A')}\n"
        message += f"Affected Assets: {len(patch.get('affectedAssets', []))}\n"
        
        # Integrate with actual notification services
        results = {
            "email_sent": False,
            "reasons": []
        }
        
        # 1. Email Notification
        if "email" in config.get("channels", ["email"]):
            from email_service import email_service
            
            # Get SMTP config for tenant
            smtp_config = await self.db.smtp_config.find_one({"tenant_id": tenant_id})
            
            if smtp_config:
                recipients = config.get("recipients", [])
                if recipients:
                    alert_data = {
                        "title": f"Patch Notification: {patch.get('name')}",
                        "severity": patch.get("severity", "Medium"),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "asset": f"{len(patch.get('affectedAssets', []))} assets affected",
                        "description": message,
                        "recommendations": "Review and approve/deploy this patch."
                    }
                    
                    email_result = email_service.send_alert_notification(
                        smtp_config=smtp_config,
                        recipients=recipients,
                        alert=alert_data
                    )
                    results["email_sent"] = email_result["success"]
                    results["email_details"] = email_result
                else:
                    results["reasons"].append("No recipients configured")
            else:
                results["reasons"].append("SMTP config not found for tenant")
        
        # 2. Slack Notification
        if "slack" in config.get("channels", []):
            webhook_url = config.get("slack_webhook")
            if webhook_url:
                payload = {
                    "text": f"🚨 *New Patch Available: {patch.get('name')}*\n*Severity:* {patch.get('severity')}\n*Affected Assets:* {len(patch.get('affectedAssets', []))}"
                }
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(webhook_url, json=payload) as response:
                            results["slack_sent"] = response.status in [200, 201]
                except Exception as e:
                    results["slack_sent"] = False
                    results["reasons"].append(f"Slack webhook failed: {str(e)}")
            else:
                results["reasons"].append("Slack webhook missing")

        # 3. Teams Notification
        if "teams" in config.get("channels", []):
            webhook_url = config.get("teams_webhook")
            if webhook_url:
                payload = {
                    "text": f"**New Patch Available: {patch.get('name')}**\n\n**Severity:** {patch.get('severity')}\n\n**Affected Assets:** {len(patch.get('affectedAssets', []))}"
                }
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(webhook_url, json=payload) as response:
                            results["teams_sent"] = response.status in [200, 201]
                except Exception as e:
                    results["teams_sent"] = False
                    results["reasons"].append(f"Teams webhook failed: {str(e)}")
            else:
                results["reasons"].append("Teams webhook missing")

        return results
    
    async def _quarantine_patch(
        self,
        patch: Dict[str, Any],
        config: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Quarantine patch for manual review"""
        
        await self.db.patches.update_one(
            {"id": patch["id"]},
            {
                "$set": {
                    "quarantined": True,
                    "quarantine_reason": config.get("reason", "Automatic quarantine by policy"),
                    "quarantined_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        return {"quarantined": True}
    
    async def process_new_patch(
        self,
        patch: Dict[str, Any],
        tenant_id: str
    ) -> List[Dict[str, Any]]:
        """
        Automatically process a new patch against all policies
        Returns list of executed actions
        """
        matching_policies = await self.evaluate_patch_against_policies(patch, tenant_id)
        
        all_results = []
        
        for policy in matching_policies:
            results = await self.execute_policy_actions(patch, policy)
            all_results.append({
                "policy_id": policy["id"],
                "policy_name": policy["name"],
                "results": results
            })
        
        return all_results


def get_policy_engine(db):
    """Get policy engine instance"""
    return PatchPolicyEngine(db)
