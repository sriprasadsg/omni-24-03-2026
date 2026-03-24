"""
Reporting Service - Advanced Analytics & Reports
Handles SLA tracking, compliance reports, vulnerability analytics, and change logs
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict


class ReportingService:
    """Advanced patch management reporting and analytics"""
    
    def __init__(self, db):
        self.db = db
    
    async def generate_sla_compliance_report(
        self,
        tenant_id: Optional[str] = None,
        framework: str = "SOC2",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive SLA compliance report
        
        Returns:
        - Overall compliance rate
        - Patches by SLA status
        - Breach details
        - Trend analysis
        """
        from patch_service import get_patch_service
        
        # Default to last 30 days
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Get patches in date range
        query = {
            "createdAt": {
                "$gte": start_date.isoformat(),
                "$lte": end_date.isoformat()
            }
        }
        if tenant_id:
            query["tenantId"] = tenant_id
        
        patches = await self.db.patches.find(query, {"_id": 0}).to_list(length=None)
        
        patch_service = get_patch_service()
        
        compliant = []
        at_risk = []
        breached = []
        total_breach_hours = 0
        severity_stats = defaultdict(lambda: {"total": 0, "compliant": 0, "breached": 0})
        
        for patch in patches:
            severity = patch.get("severity", "Medium")
            sla_hours = patch.get("sla_hours") or patch_service.calculate_patch_sla_hours(severity, framework)
            
            created = datetime.fromisoformat(patch.get("createdAt", datetime.now(timezone.utc).isoformat()))
            deployed = patch.get("deployedAt")
            
            severity_stats[severity]["total"] += 1
            
            if deployed:
                deployed_dt = datetime.fromisoformat(deployed)
                time_to_deploy = (deployed_dt - created).total_seconds() / 3600
                
                if time_to_deploy <= sla_hours:
                    compliant.append({**patch, "time_to_deploy_hours": time_to_deploy})
                    severity_stats[severity]["compliant"] += 1
                else:
                    breach_hours = time_to_deploy - sla_hours
                    breached.append({
                        **patch,
                        "time_to_deploy_hours": time_to_deploy,
                        "sla_hours": sla_hours,
                        "breach_hours": breach_hours
                    })
                    severity_stats[severity]["breached"] += 1
                    total_breach_hours += breach_hours
            else:
                # Not yet deployed - check if exceeded SLA
                deadline = created + timedelta(hours=sla_hours)
                if datetime.now(timezone.utc) > deadline:
                    breach_hours = (datetime.now(timezone.utc) - deadline).total_seconds() / 3600
                    breached.append({
                        **patch,
                        "sla_hours": sla_hours,
                        "breach_hours": breach_hours,
                        "status": "overdue"
                    })
                    severity_stats[severity]["breached"] += 1
                    total_breach_hours += breach_hours
                else:
                    time_remaining = (deadline - datetime.now(timezone.utc)).total_seconds() / 3600
                    if time_remaining < (sla_hours * 0.25):  # Less than 25% remaining
                        at_risk.append({**patch, "time_remaining_hours": time_remaining})
        
        total = len(patches)
        compliance_rate = (len(compliant) / total * 100) if total > 0 else 100
        
        return {
            "framework": framework,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": (end_date - start_date).days
            },
            "summary": {
                "total_patches": total,
                "compliant": len(compliant),
                "at_risk": len(at_risk),
                "breached": len(breached),
                "compliance_rate": round(compliance_rate, 2),
                "total_breach_hours": round(total_breach_hours, 2)
            },
            "by_severity": dict(severity_stats),
            "patches": {
                "compliant": compliant[:10],  # Top 10
                "at_risk": at_risk,
                "breached": breached
            },
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def generate_vulnerability_exposure_report(
        self,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate vulnerability exposure report
        
        Shows:
        - Assets by risk level
        - Critical CVEs
        - Exploit probability
        - Mean time to patch
        """
        query = {"status": "Pending"}
        if tenant_id:
            query["tenantId"] = tenant_id
        
        patches = await self.db.patches.find(query, {"_id": 0}).to_list(length=None)
        
        # Get all assets
        asset_query = {}
        if tenant_id:
            asset_query["tenantId"] = tenant_id
        assets = await self.db.assets.find(asset_query, {"_id": 0}).to_list(length=None)
        
        # Calculate exposure
        exposed_assets = set()
        critical_vulnerabilities = []
        high_epss_vulns = []
        severity_distribution = defaultdict(int)
        cvss_distribution = defaultdict(int)
        
        for patch in patches:
            severity = patch.get("severity", "Medium")
            severity_distribution[severity] += 1
            
            cvss = patch.get("cvss_score")
            if cvss:
                if cvss >= 9.0:
                    cvss_distribution["9.0-10.0"] += 1
                elif cvss >= 7.0:
                    cvss_distribution["7.0-8.9"] += 1
                elif cvss >= 4.0:
                    cvss_distribution["4.0-6.9"] += 1
                else:
                    cvss_distribution["0.0-3.9"] += 1
            
            epss = patch.get("epss_score", 0)
            
            # Track critical vulnerabilities
            if severity == "Critical" or (cvss and cvss >= 9.0):
                critical_vulnerabilities.append(patch)
            
            # Track high exploit probability
            if epss >= 0.5:  # >50% chance
                high_epss_vulns.append(patch)
            
            # Count exposed assets
            for asset_id in patch.get("affectedAssets", []):
                exposed_assets.add(asset_id)
        
        total_assets = len(assets)
        exposed_count = len(exposed_assets)
        exposure_rate = (exposed_count / total_assets * 100) if total_assets > 0 else 0
        
        return {
            "summary": {
                "total_assets": total_assets,
                "exposed_assets": exposed_count,
                "exposure_rate": round(exposure_rate, 2),
                "pending_patches": len(patches),
                "critical_vulnerabilities": len(critical_vulnerabilities),
                "high_exploit_probability": len(high_epss_vulns)
            },
            "severity_distribution": dict(severity_distribution),
            "cvss_distribution": dict(cvss_distribution),
            "critical_vulnerabilities": critical_vulnerabilities[:20],  # Top 20
            "high_exploit_probability": high_epss_vulns[:20],
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def generate_change_management_log(
        self,
        tenant_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Generate ITIL-compliant change management log
        
        Tracks:
        - All deployment activities
        - Who made changes
        - When changes occurred
        - Success/failure status
        """
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        query = {
            "created_at": {
                "$gte": start_date.isoformat(),
                "$lte": end_date.isoformat()
            }
        }
        if tenant_id:
            query["tenant_id"] = tenant_id
        
        # Get deployment jobs
        deployments = await self.db.patch_deployment_jobs.find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(length=None)
        
        # Get staged deployments
        staged_deployments = await self.db.staged_deployments.find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(length=None)
        
        # Get rollbacks
        rollbacks = await self.db.rollback_jobs.find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(length=None)
        
        # Combine and categorize
        change_records = []
        
        for deployment in deployments:
            change_records.append({
                "id": deployment.get("id"),
                "type": "patch_deployment",
                "status": deployment.get("status"),
                "created_by": deployment.get("created_by"),
                "created_at": deployment.get("created_at"),
                "patch_count": len(deployment.get("patch_ids", [])),
                "asset_count": len(deployment.get("asset_ids", []))
            })
        
        for deployment in staged_deployments:
            change_records.append({
                "id": deployment.get("id"),
                "type": "staged_deployment",
                "status": deployment.get("status"),
                "created_by": deployment.get("created_by"),
                "created_at": deployment.get("created_at"),
                "current_stage": deployment.get("current_stage"),
                "patch_count": len(deployment.get("patch_ids", []))
            })
        
        for rollback in rollbacks:
            change_records.append({
                "id": rollback.get("id"),
                "type": "rollback",
                "status": rollback.get("status"),
                "reason": rollback.get("reason"),
                "created_at": rollback.get("created_at"),
                "asset_count": len(rollback.get("asset_ids", []))
            })
        
        # Sort by date
        change_records.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "summary": {
                "total_changes": len(change_records),
                "deployments": len(deployments),
                "staged_deployments": len(staged_deployments),
                "rollbacks": len(rollbacks)
            },
            "changes": change_records,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def generate_executive_summary(
        self,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate executive-level summary dashboard
        
        High-level KPIs for C-suite:
        - Security posture
        - Compliance status
        - Patch deployment velocity
        - Risk exposure
        """
        # Get SLA report
        sla_report = await self.generate_sla_compliance_report(tenant_id=tenant_id, framework="SOC2")
        
        # Get vulnerability exposure
        vuln_report = await self.generate_vulnerability_exposure_report(tenant_id=tenant_id)
        
        # Calculate patch velocity (patches deployed per week)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        
        query = {
            "deployedAt": {"$exists": True, "$gte": thirty_days_ago.isoformat()}
        }
        if tenant_id:
            query["tenantId"] = tenant_id
        
        deployed_patches = await self.db.patches.find(query, {"_id": 0}).to_list(length=None)
        patches_per_week = len(deployed_patches) / 4.3  # Average weeks in a month
        
        # Calculate MTTR (Mean Time To Remediate)
        deploy_times = []
        for patch in deployed_patches:
            if patch.get("createdAt") and patch.get("deployedAt"):
                created = datetime.fromisoformat(patch["createdAt"])
                deployed = datetime.fromisoformat(patch["deployedAt"])
                hours = (deployed - created).total_seconds() / 3600
                deploy_times.append(hours)
        
        mttr_hours = sum(deploy_times) / len(deploy_times) if deploy_times else 0
        
        return {
            "kpis": {
                "compliance_rate": sla_report["summary"]["compliance_rate"],
                "patches_per_week": round(patches_per_week, 1),
                "mttr_hours": round(mttr_hours, 1),
                "asset_exposure_rate": vuln_report["summary"]["exposure_rate"],
                "critical_vulnerabilities": vuln_report["summary"]["critical_vulnerabilities"],
                "high_exploit_risk": vuln_report["summary"]["high_exploit_probability"]
            },
            "sla_summary": sla_report["summary"],
            "vulnerability_summary": vuln_report["summary"],
            "generated_at": datetime.now(timezone.utc).isoformat()
        }


def get_reporting_service(db):
    """Get reporting service instance"""
    return ReportingService(db)
