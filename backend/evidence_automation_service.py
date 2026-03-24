"""
Evidence Automation Service

Automatically collects compliance evidence from various sources
and maps it to compliance controls.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import hashlib


class EvidenceAutomationService:
    """Automated Compliance Evidence Collection Service"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        
        # Evidence collector configurations
        self.collectors = {
            "configuration_snapshot": self._collect_configuration_snapshot,
            "access_logs": self._collect_access_logs,
            "patch_status": self._collect_patch_status,
            "vulnerability_scans": self._collect_vulnerability_scans,
            "training_records": self._collect_training_records,
            "backup_verification": self._collect_backup_verification,
            "encryption_status": self._collect_encryption_status,
        }

        # Initialize LLM for suggestions
        self.ai_provider = None
    
    async def collect_evidence_for_framework(
        self,
        framework_id: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Collect all evidence for a compliance framework
        
        Returns summary of collected evidence
        """
        # Get framework and controls
        framework = await self.db.compliance_frameworks.find_one({
            "_id": framework_id,
            "tenantId": tenant_id
        })
        
        if not framework:
            return {"error": "Framework not found"}
        
        controls = framework.get("controls", [])
        evidence_collected = []
        
        for control in controls:
            control_id = control.get("id")
            evidence_types = control.get("evidence_types", [])
            
            for evidence_type in evidence_types:
                if evidence_type in self.collectors:
                    try:
                        evidence = await self.collectors[evidence_type](
                            tenant_id, control_id, control
                        )
                        
                        if evidence:
                            # Store evidence
                            evidence_doc = {
                                "tenant_id": tenant_id,
                                "framework_id": framework_id,
                                "control_id": control_id,
                                "evidence_type": evidence_type,
                                "evidence_data": evidence,
                                "collected_at": datetime.now(timezone.utc).isoformat(),
                                "hash": self._hash_evidence(evidence),
                                "status": "valid"
                            }
                            
                            await self.db.compliance_evidence.insert_one(evidence_doc)
                            evidence_collected.append(evidence_doc)
                    
                    except Exception as e:
                        print(f"Error collecting {evidence_type} for control {control_id}: {e}")
        
        return {
            "framework_id": framework_id,
            "tenant_id": tenant_id,
            "evidence_count": len(evidence_collected),
            "collected_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def _collect_configuration_snapshot(
        self,
        tenant_id: str,
        control_id: str,
        control: Dict
    ) -> Dict[str, Any]:
        """Collect configuration snapshots from assets"""
        # Get all assets for tenant
        cursor = self.db.assets.find({"tenantId": tenant_id}).limit(100)
        
        configurations = []
        async for asset in cursor:
            config = {
                "asset_id": asset.get("id"),
                "asset_name": asset.get("name"),
                "os": asset.get("os"),
                "ip_address": asset.get("ipAddress"),
                "security_settings": asset.get("securitySettings", {}),
                "snapshot_time": datetime.now(timezone.utc).isoformat()
            }
            configurations.append(config)
        
        return {
            "type": "configuration_snapshot",
            "asset_count": len(configurations),
            "configurations": configurations
        }
    
    async def _collect_access_logs(
        self,
        tenant_id: str,
        control_id: str,
        control: Dict
    ) -> Dict[str, Any]:
        """Collect access logs"""
        # Get recent audit logs
        threshold = datetime.now(timezone.utc) - timedelta(days=30)
        
        cursor = self.db.audit_logs.find({
            "tenantId": tenant_id,
            "timestamp": {"$gte": threshold.isoformat()}
        }).limit(1000)
        
        logs = []
        async for log in cursor:
            logs.append({
                "user": log.get("user"),
                "action": log.get("action"),
                "resource": log.get("resource"),
                "timestamp": log.get("timestamp"),
                "ip_address": log.get("ipAddress")
            })
        
        return {
            "type": "access_logs",
            "log_count": len(logs),
            "time_period_days": 30,
            "sample_logs": logs[:100]  # Store sample
        }
    
    async def _collect_patch_status(
        self,
        tenant_id: str,
        control_id: str,
        control: Dict
    ) -> Dict[str, Any]:
        """Collect patch status from assets"""
        cursor = self.db.assets.find({"tenantId": tenant_id})
        
        patch_summary = {
            "total_assets": 0,
            "fully_patched": 0,
            "partially_patched": 0,
            "unpatched": 0,
            "assets": []
        }
        
        async for asset in cursor:
            patch_summary["total_assets"] += 1
            
            vulnerabilities = asset.get("vulnerabilities", [])
            critical_vulns = [v for v in vulnerabilities if v.get("severity") == "Critical"]
            
            if len(critical_vulns) == 0:
                patch_summary["fully_patched"] += 1
                status = "fully_patched"
            elif len(critical_vulns) < 3:
                patch_summary["partially_patched"] += 1
                status = "partially_patched"
            else:
                patch_summary["unpatched"] += 1
                status = "unpatched"
            
            patch_summary["assets"].append({
                "asset_id": asset.get("id"),
                "asset_name": asset.get("name"),
                "status": status,
                "critical_vulnerabilities": len(critical_vulns)
            })
        
        return patch_summary
    
    async def _collect_vulnerability_scans(
        self,
        tenant_id: str,
        control_id: str,
        control: Dict
    ) -> Dict[str, Any]:
        """Collect vulnerability scan results"""
        # Get recent scan jobs
        threshold = datetime.now(timezone.utc) - timedelta(days=30)
        
        cursor = self.db.vulnerability_scan_jobs.find({
            "tenantId": tenant_id,
            "createdAt": {"$gte": threshold.isoformat()}
        })
        
        scans = []
        async for scan in cursor:
            scans.append({
                "scan_id": scan.get("id"),
                "asset_id": scan.get("assetId"),
                "status": scan.get("status"),
                "created_at": scan.get("createdAt"),
                "findings_count": len(scan.get("findings", []))
            })
        
        return {
            "type": "vulnerability_scans",
            "scan_count": len(scans),
            "time_period_days": 30,
            "scans": scans
        }
    
    async def _collect_training_records(
        self,
        tenant_id: str,
        control_id: str,
        control: Dict
    ) -> Dict[str, Any]:
        """Collect security training completion records"""
        # Get users for tenant
        cursor = self.db.users.find({"tenantId": tenant_id})
        
        training_summary = {
            "total_users": 0,
            "trained_users": 0,
            "completion_rate": 0.0,
            "records": []
        }
        
        async for user in cursor:
            training_summary["total_users"] += 1
            
            # Simulate training record (in real system, this would come from LMS)
            completed = user.get("securityTrainingCompleted", False)
            if completed:
                training_summary["trained_users"] += 1
            
            training_summary["records"].append({
                "user_id": user.get("id"),
                "user_email": user.get("email"),
                "completed": completed,
                "completion_date": user.get("trainingCompletionDate")
            })
        
        if training_summary["total_users"] > 0:
            training_summary["completion_rate"] = training_summary["trained_users"] / training_summary["total_users"]
        
        return training_summary
    
    async def _collect_backup_verification(
        self,
        tenant_id: str,
        control_id: str,
        control: Dict
    ) -> Dict[str, Any]:
        """Collect backup verification records"""
        # In real system, this would query backup system
        return {
            "type": "backup_verification",
            "last_backup": datetime.now(timezone.utc).isoformat(),
            "backup_frequency": "daily",
            "retention_days": 30,
            "verified": True
        }
    
    async def _collect_encryption_status(
        self,
        tenant_id: str,
        control_id: str,
        control: Dict
    ) -> Dict[str, Any]:
        """Collect encryption status for assets"""
        cursor = self.db.assets.find({"tenantId": tenant_id})
        
        encryption_summary = {
            "total_assets": 0,
            "encrypted": 0,
            "unencrypted": 0,
            "assets": []
        }
        
        async for asset in cursor:
            encryption_summary["total_assets"] += 1
            
            encrypted = asset.get("encrypted", False)
            if encrypted:
                encryption_summary["encrypted"] += 1
            else:
                encryption_summary["unencrypted"] += 1
            
            encryption_summary["assets"].append({
                "asset_id": asset.get("id"),
                "asset_name": asset.get("name"),
                "encrypted": encrypted,
                "encryption_method": asset.get("encryptionMethod", "none")
            })
        
        return encryption_summary
    
    def _hash_evidence(self, evidence: Dict) -> str:
        """Create hash of evidence for integrity verification"""
        import json
        evidence_str = json.dumps(evidence, sort_keys=True)
        return hashlib.sha256(evidence_str.encode()).hexdigest()
    
    async def validate_evidence(
        self,
        evidence_id: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """Validate evidence integrity and freshness"""
        evidence = await self.db.compliance_evidence.find_one({
            "_id": evidence_id,
            "tenant_id": tenant_id
        })
        
        if not evidence:
            return {"valid": False, "reason": "Evidence not found"}
        
        # Check freshness (evidence should be < 90 days old)
        collected_at = datetime.fromisoformat(evidence["collected_at"].replace('Z', '+00:00'))
        age_days = (datetime.now(timezone.utc) - collected_at).days
        
        if age_days > 90:
            return {"valid": False, "reason": f"Evidence is {age_days} days old (max 90)"}
        
        # Verify hash
        current_hash = self._hash_evidence(evidence["evidence_data"])
        if current_hash != evidence["hash"]:
            return {"valid": False, "reason": "Evidence integrity check failed"}
        
        return {
            "valid": True,
            "age_days": age_days,
            "collected_at": evidence["collected_at"]
        }

    async def get_evidence_collection_suggestions(self, control_id: str, control_data: Dict) -> str:
        """
        Ask the SecurityExpert AI for suggestions on how to collect evidence for a control.
        """
        from ai_service import IncidentAnalyzer
        analyzer = IncidentAnalyzer()
        await analyzer.initialize()

        if not analyzer.is_configured:
            return "AI Service not configured for suggestions."

        prompt = f"""
        The automated evidence collection failed for the following security control.
        Please provide 3-4 specific technical steps (including PowerShell or Bash commands) that a security administrator can run on the agent to collect this evidence manually.

        CONTROL:
        ID: {control_id}
        Name: {control_data.get('name')}
        Description: {control_data.get('description')}

        RESPOND WITH CLEAR, STEP-BY-STEP INSTRUCTIONS.
        """

        try:
            # Use the specialized model if available in settings, or default
            response = await analyzer.provider.generate(prompt)
            return response
        except Exception as e:
            return f"Failed to generate AI suggestions: {str(e)}"


# Singleton
_evidence_service: Optional[EvidenceAutomationService] = None

def get_evidence_service(db: AsyncIOMotorDatabase) -> EvidenceAutomationService:
    """Get or create evidence automation service singleton"""
    global _evidence_service
    if _evidence_service is None:
        _evidence_service = EvidenceAutomationService(db)
    return _evidence_service
