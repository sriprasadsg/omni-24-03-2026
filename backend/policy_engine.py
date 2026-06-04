"""
Policy Engine Service - Automated Patch Deployment Rules
Handles policy-based automation, scheduling, and conditional deployment
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any
from enum import Enum
from policy_engine_actions import PatchPolicyActionsMixin


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


class PatchPolicyEngine(PatchPolicyActionsMixin):
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
        ).sort("priority", -1).to_list(length=1000)
        
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
                ).to_list(length=1000)
                
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
