"""
SAST (Static Application Security Testing) Service

Integrates with:
- SonarQube for code quality and security analysis
- Checkmarx for comprehensive SAST scanning
- Custom security rules and patterns

Provides:
- Automated code scanning
- Vulnerability detection
- Code quality metrics
- Security hotspot identification
- Compliance checking
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
import hashlib
from sast_service_analysis import SASTServiceAnalysisMixin, ScanStatus


class SASTService(SASTServiceAnalysisMixin):
    """Static Application Security Testing Service"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.logger = logging.getLogger("SASTService")
        
        import os
        self.sonarqube_config = {
            "url": os.environ.get("SONARQUBE_URL", "http://localhost:9000"),
            "token": os.environ.get("SONARQUBE_TOKEN", ""),
            "enabled": bool(os.environ.get("SONARQUBE_TOKEN")),
        }
        
        # Checkmarx configuration
        self.checkmarx_config = {
            "url": "",
            "username": "",
            "password": "",
            "enabled": False
        }
        
        # Security patterns for custom scanning
        self.security_patterns = self._load_security_patterns()
    
    async def trigger_scan(
        self,
        project_name: str,
        repository_url: str,
        branch: str = "main",
        scan_type: str = "full",
        tenant_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Trigger a SAST scan
        
        Args:
            project_name: Name of the project
            repository_url: Git repository URL
            branch: Branch to scan
            scan_type: full, incremental, or quick
            tenant_id: Tenant ID
        
        Returns:
            Scan job details
        """
        scan_id = hashlib.sha256(
            f"{project_name}:{branch}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]
        
        scan_job = {
            "scan_id": scan_id,
            "project_name": project_name,
            "repository_url": repository_url,
            "branch": branch,
            "scan_type": scan_type,
            "tenant_id": tenant_id,
            "status": ScanStatus.PENDING,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "vulnerabilities_found": 0,
            "code_quality_score": None,
            "results": None,
            "error": None
        }
        
        # Store scan job
        await self.db.sast_scans.insert_one(scan_job.copy())
        
        # In production, trigger actual scan asynchronously
        # For now, simulate scan execution
        await self._execute_scan(scan_id)
        
        self.logger.info(f"SAST scan triggered: {scan_id} for project {project_name}")
        
        return scan_job
    
    async def _execute_scan(self, scan_id: str):
        """Execute SAST scan via SonarQube when configured, else pattern-based analysis."""
        await self.db.sast_scans.update_one(
            {"scan_id": scan_id},
            {"$set": {"status": ScanStatus.RUNNING,
                      "started_at": datetime.now(timezone.utc).isoformat()}}
        )

        scan = await self.db.sast_scans.find_one({"scan_id": scan_id})
        project_key = (scan.get("project_name", scan_id)
                       .lower().replace(" ", "_").replace("-", "_"))
        repository_url = scan.get("repository_url", "")

        if self.sonarqube_config.get("enabled") and self.sonarqube_config.get("token"):
            vulnerabilities = await self._fetch_sonarqube_issues(project_key)
        else:
            vulnerabilities = await self._pattern_scan(repository_url)

        code_quality_score = self._calculate_code_quality_score(vulnerabilities)
        
        # Store results
        await self.db.sast_scans.update_one(
            {"scan_id": scan_id},
            {
                "$set": {
                    "status": ScanStatus.COMPLETED,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "vulnerabilities_found": len(vulnerabilities),
                    "code_quality_score": code_quality_score,
                    "results": {
                        "vulnerabilities": vulnerabilities,
                        "code_quality": code_quality_score,
                        "summary": self._generate_summary(vulnerabilities)
                    }
                }
            }
        )
        
        # Store individual vulnerabilities
        for vuln in vulnerabilities:
            vuln["scan_id"] = scan_id
            vuln["created_at"] = datetime.now(timezone.utc).isoformat()
            vuln["status"] = "open"
            vuln["false_positive"] = False
            await self.db.sast_vulnerabilities.insert_one(vuln)
        
        self.logger.info(f"SAST scan completed: {scan_id}, found {len(vulnerabilities)} vulnerabilities")
    
    async def get_scan_results(self, scan_id: str, tenant_id: str = "") -> Dict[str, Any]:
        """Get scan results"""
        query: dict = {"scan_id": scan_id}
        if tenant_id:
            query["tenant_id"] = tenant_id
        scan = await self.db.sast_scans.find_one(query)
        
        if not scan:
            raise ValueError(f"Scan not found: {scan_id}")
        
        scan["id"] = str(scan.pop("_id"))
        return scan
    
    async def list_vulnerabilities(
        self,
        scan_id: Optional[str] = None,
        severity: Optional[str] = None,
        status: str = "open",
        limit: int = 100,
        tenant_id: str = "",
    ) -> List[Dict[str, Any]]:
        """List vulnerabilities"""
        query = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if scan_id:
            query["scan_id"] = scan_id
        if severity:
            query["severity"] = severity
        if status:
            query["status"] = status
        
        cursor = self.db.sast_vulnerabilities.find(query).sort("severity_score", -1).limit(limit)
        
        vulnerabilities = []
        async for vuln in cursor:
            vuln["id"] = str(vuln.pop("_id"))
            vulnerabilities.append(vuln)
        
        return vulnerabilities
    
    async def mark_false_positive(
        self,
        vulnerability_id: str,
        reason: str,
        user: str
    ) -> Dict[str, Any]:
        """Mark vulnerability as false positive"""
        result = await self.db.sast_vulnerabilities.update_one(
            {"_id": vulnerability_id},
            {
                "$set": {
                    "false_positive": True,
                    "false_positive_reason": reason,
                    "false_positive_marked_by": user,
                    "false_positive_marked_at": datetime.now(timezone.utc).isoformat(),
                    "status": "false_positive"
                }
            }
        )
        
        if result.modified_count == 0:
            raise ValueError(f"Vulnerability not found: {vulnerability_id}")
        
        return {"success": True, "message": "Marked as false positive"}
    
    async def get_code_quality_metrics(self, scan_id: str, tenant_id: str = "") -> Dict[str, Any]:
        """Get code quality metrics for a scan"""
        query: dict = {"scan_id": scan_id}
        if tenant_id:
            query["tenant_id"] = tenant_id
        scan = await self.db.sast_scans.find_one(query)
        
        if not scan:
            raise ValueError(f"Scan not found: {scan_id}")
        
        # Get vulnerability breakdown
        pipeline = [
            {"$match": {"scan_id": scan_id}},
            {
                "$group": {
                    "_id": "$severity",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        cursor = self.db.sast_vulnerabilities.aggregate(pipeline)
        severity_breakdown = {}
        
        async for result in cursor:
            severity_breakdown[result["_id"]] = result["count"]
        
        return {
            "scan_id": scan_id,
            "code_quality_score": scan.get("code_quality_score"),
            "total_vulnerabilities": scan.get("vulnerabilities_found", 0),
            "severity_breakdown": severity_breakdown,
            "metrics": {
                "maintainability": self._calculate_maintainability_score(scan),
                "reliability": self._calculate_reliability_score(scan),
                "security": self._calculate_security_score(scan),
                "coverage": self._calculate_coverage_score(scan)
            }
        }
    
    async def get_scan_history(
        self,
        project_name: Optional[str] = None,
        limit: int = 50,
        tenant_id: str = "",
    ) -> List[Dict[str, Any]]:
        """Get scan history"""
        query = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if project_name:
            query["project_name"] = project_name
        
        cursor = self.db.sast_scans.find(query).sort("created_at", -1).limit(limit)
        
        scans = []
        async for scan in cursor:
            scan["id"] = str(scan.pop("_id"))
            scans.append(scan)
        
        return scans
    
    async def get_statistics(self, tenant_id: str) -> Dict[str, Any]:
        """Get SAST statistics"""
        # Total scans
        total_scans = await self.db.sast_scans.count_documents({"tenant_id": tenant_id})
        
        # Scans by status
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        cursor = self.db.sast_scans.aggregate(pipeline)
        scans_by_status = {}
        
        async for result in cursor:
            scans_by_status[result["_id"]] = result["count"]
        
        # Total vulnerabilities
        total_vulnerabilities = await self.db.sast_vulnerabilities.count_documents({})
        
        # Open vulnerabilities by severity
        pipeline = [
            {"$match": {"status": "open"}},
            {
                "$group": {
                    "_id": "$severity",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        cursor = self.db.sast_vulnerabilities.aggregate(pipeline)
        open_by_severity = {}
        
        async for result in cursor:
            open_by_severity[result["_id"]] = result["count"]
        
        return {
            "total_scans": total_scans,
            "scans_by_status": scans_by_status,
            "total_vulnerabilities": total_vulnerabilities,
            "open_vulnerabilities": sum(open_by_severity.values()),
            "open_by_severity": open_by_severity
        }
    


# Singleton
_sast_service: Optional[SASTService] = None

def get_sast_service(db: AsyncIOMotorDatabase) -> SASTService:
    """Get or create SAST service singleton"""
    global _sast_service
    if _sast_service is None:
        _sast_service = SASTService(db)
    return _sast_service
