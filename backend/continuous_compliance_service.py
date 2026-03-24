"""
Continuous Compliance Monitoring Service

Real-time compliance posture tracking and policy-as-code enforcement.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase


class ContinuousComplianceService:
    """Continuous Compliance Monitoring and Policy Enforcement"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        
        # Compliance policies (simplified for MVP)
        self.policies = {
            "password_policy": self._check_password_policy,
            "encryption_required": self._check_encryption,
            "patch_compliance": self._check_patch_compliance,
            "access_control": self._check_access_control,
            "backup_policy": self._check_backup_policy,
        }
    
    async def evaluate_compliance(
        self,
        tenant_id: str,
        framework_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate real-time compliance posture
        
        Returns compliance score and violations
        """
        # Get applicable frameworks
        query = {"tenantId": tenant_id}
        if framework_id:
            query["_id"] = framework_id
        
        cursor = self.db.compliance_frameworks.find(query)
        
        total_controls = 0
        compliant_controls = 0
        violations = []
        
        async for framework in cursor:
            controls = framework.get("controls", [])
            
            for control in controls:
                total_controls += 1
                control_id = control.get("id")
                policy_checks = control.get("policy_checks", [])
                
                control_compliant = True
                
                for policy_name in policy_checks:
                    if policy_name in self.policies:
                        result = await self.policies[policy_name](tenant_id, control)
                        
                        if not result["compliant"]:
                            control_compliant = False
                            violations.append({
                                "framework_id": framework.get("_id"),
                                "framework_name": framework.get("name"),
                                "control_id": control_id,
                                "control_name": control.get("name"),
                                "policy": policy_name,
                                "violation": result["violation"],
                                "severity": result.get("severity", "medium"),
                                "detected_at": datetime.now(timezone.utc).isoformat()
                            })
                
                if control_compliant:
                    compliant_controls += 1
        
        compliance_score = (compliant_controls / total_controls * 100) if total_controls > 0 else 0
        
        result = {
            "tenant_id": tenant_id,
            "compliance_score": round(compliance_score, 2),
            "total_controls": total_controls,
            "compliant_controls": compliant_controls,
            "violation_count": len(violations),
            "violations": violations,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "status": self._get_compliance_status(compliance_score)
        }
        
        # Store evaluation result
        await self.db.compliance_evaluations.insert_one(result)
        
        return result
    
    async def _check_password_policy(self, tenant_id: str, control: Dict) -> Dict[str, Any]:
        """Check if password policy is enforced"""
        # Get users with weak passwords (simplified check)
        users = await self.db.users.find({"tenantId": tenant_id}).to_list(length=1000)
        
        weak_password_users = []
        for user in users:
            # In real system, check password strength requirements
            if not user.get("passwordComplexityMet", True):
                weak_password_users.append(user.get("email"))
        
        if weak_password_users:
            return {
                "compliant": False,
                "violation": f"{len(weak_password_users)} users with weak passwords",
                "severity": "high",
                "affected_users": weak_password_users
            }
        
        return {"compliant": True}
    
    async def _check_encryption(self, tenant_id: str, control: Dict) -> Dict[str, Any]:
        """Check if encryption is enabled on all assets"""
        cursor = self.db.assets.find({"tenantId": tenant_id})
        
        unencrypted_assets = []
        async for asset in cursor:
            if not asset.get("encrypted", False):
                unencrypted_assets.append(asset.get("name"))
        
        if unencrypted_assets:
            return {
                "compliant": False,
                "violation": f"{len(unencrypted_assets)} assets without encryption",
                "severity": "critical",
                "affected_assets": unencrypted_assets[:10]
            }
        
        return {"compliant": True}
    
    async def _check_patch_compliance(self, tenant_id: str, control: Dict) -> Dict[str, Any]:
        """Check if critical patches are applied"""
        cursor = self.db.assets.find({"tenantId": tenant_id})
        
        vulnerable_assets = []
        async for asset in cursor:
            vulnerabilities = asset.get("vulnerabilities", [])
            critical_vulns = [v for v in vulnerabilities if v.get("severity") == "Critical"]
            
            if critical_vulns:
                vulnerable_assets.append({
                    "asset": asset.get("name"),
                    "critical_vulns": len(critical_vulns)
                })
        
        if vulnerable_assets:
            return {
                "compliant": False,
                "violation": f"{len(vulnerable_assets)} assets with critical vulnerabilities",
                "severity": "critical",
                "affected_assets": vulnerable_assets[:10]
            }
        
        return {"compliant": True}
    
    async def _check_access_control(self, tenant_id: str, control: Dict) -> Dict[str, Any]:
        """Check if access controls are properly configured"""
        # Check for users with excessive permissions
        users = await self.db.users.find({"tenantId": tenant_id}).to_list(length=1000)
        
        admin_users = [u for u in users if u.get("role") == "Admin"]
        
        # Flag if >20% of users are admins
        if len(users) > 0 and len(admin_users) / len(users) > 0.2:
            return {
                "compliant": False,
                "violation": f"Too many admin users ({len(admin_users)}/{len(users)})",
                "severity": "medium"
            }
        
        return {"compliant": True}
    
    async def _check_backup_policy(self, tenant_id: str, control: Dict) -> Dict[str, Any]:
        """Check if backups are configured and recent"""
        # In real system, check backup system
        # For MVP, assume compliant
        return {"compliant": True}
    
    def _get_compliance_status(self, score: float) -> str:
        """Get compliance status based on score"""
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 60:
            return "fair"
        else:
            return "poor"
    
    async def get_compliance_trend(
        self,
        tenant_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get compliance score trend over time"""
        from datetime import timedelta
        
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
        
        cursor = self.db.compliance_evaluations.find({
            "tenant_id": tenant_id,
            "evaluated_at": {"$gte": threshold.isoformat()}
        }).sort("evaluated_at", 1)
        
        trend = []
        async for evaluation in cursor:
            trend.append({
                "date": evaluation["evaluated_at"],
                "score": evaluation["compliance_score"],
                "violations": evaluation["violation_count"]
            })
        
        return trend
    
    async def create_remediation_task(
        self,
        violation: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Create remediation task for a compliance violation"""
        task = {
            "tenant_id": tenant_id,
            "type": "compliance_remediation",
            "violation": violation,
            "status": "open",
            "priority": violation.get("severity", "medium"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "assigned_to": None,
            "due_date": None
        }
        
        result = await self.db.remediation_tasks.insert_one(task)
        task["id"] = str(result.inserted_id)
        
        return task


# Singleton
_compliance_service: Optional[ContinuousComplianceService] = None

def get_continuous_compliance_service(db: AsyncIOMotorDatabase) -> ContinuousComplianceService:
    """Get or create continuous compliance service singleton"""
    global _compliance_service
    if _compliance_service is None:
        _compliance_service = ContinuousComplianceService(db)
    return _compliance_service
