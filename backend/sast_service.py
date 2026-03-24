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
import json


class VulnerabilitySeverity:
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ScanStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SASTService:
    """Static Application Security Testing Service"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.logger = logging.getLogger("SASTService")
        
        # SonarQube configuration (in production, load from environment)
        self.sonarqube_config = {
            "url": "http://localhost:9000",
            "token": "",  # Set via environment variable
            "enabled": False
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
        """Execute SAST scan (simulated for now)"""
        # Update status to running
        await self.db.sast_scans.update_one(
            {"scan_id": scan_id},
            {
                "$set": {
                    "status": ScanStatus.RUNNING,
                    "started_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # In production, this would:
        # 1. Clone repository
        # 2. Run SonarQube scanner
        # 3. Run Checkmarx scan
        # 4. Parse results
        # 5. Store vulnerabilities
        
        # Simulate scan results
        vulnerabilities = self._simulate_scan_results()
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
    
    async def get_scan_results(self, scan_id: str) -> Dict[str, Any]:
        """Get scan results"""
        scan = await self.db.sast_scans.find_one({"scan_id": scan_id})
        
        if not scan:
            raise ValueError(f"Scan not found: {scan_id}")
        
        scan["id"] = str(scan.pop("_id"))
        return scan
    
    async def list_vulnerabilities(
        self,
        scan_id: Optional[str] = None,
        severity: Optional[str] = None,
        status: str = "open",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List vulnerabilities"""
        query = {}
        
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
    
    async def get_code_quality_metrics(self, scan_id: str) -> Dict[str, Any]:
        """Get code quality metrics for a scan"""
        scan = await self.db.sast_scans.find_one({"scan_id": scan_id})
        
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
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get scan history"""
        query = {}
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
    
    def _simulate_scan_results(self) -> List[Dict[str, Any]]:
        """Simulate scan results (replace with actual scanner integration)"""
        # Simulated vulnerabilities
        vulnerabilities = [
            {
                "title": "SQL Injection vulnerability",
                "description": "User input is not properly sanitized before being used in SQL query",
                "severity": VulnerabilitySeverity.CRITICAL,
                "severity_score": 9.8,
                "category": "Injection",
                "cwe_id": "CWE-89",
                "owasp_category": "A03:2021 - Injection",
                "file_path": "backend/user_service.py",
                "line_number": 145,
                "code_snippet": "query = f\"SELECT * FROM users WHERE username = '{username}'\"",
                "recommendation": "Use parameterized queries or ORM to prevent SQL injection"
            },
            {
                "title": "Hardcoded credentials",
                "description": "Database password is hardcoded in source code",
                "severity": VulnerabilitySeverity.CRITICAL,
                "severity_score": 9.0,
                "category": "Sensitive Data Exposure",
                "cwe_id": "CWE-798",
                "owasp_category": "A02:2021 - Cryptographic Failures",
                "file_path": "backend/config.py",
                "line_number": 23,
                "code_snippet": "DB_PASSWORD = 'admin123'",
                "recommendation": "Use environment variables or secrets management system"
            },
            {
                "title": "Cross-Site Scripting (XSS)",
                "description": "User input is rendered without proper escaping",
                "severity": VulnerabilitySeverity.HIGH,
                "severity_score": 7.5,
                "category": "Cross-Site Scripting",
                "cwe_id": "CWE-79",
                "owasp_category": "A03:2021 - Injection",
                "file_path": "components/UserProfile.tsx",
                "line_number": 67,
                "code_snippet": "dangerouslySetInnerHTML={{ __html: userBio }}",
                "recommendation": "Sanitize user input before rendering or use safe rendering methods"
            },
            {
                "title": "Insecure random number generation",
                "description": "Using predictable random number generator for security-sensitive operations",
                "severity": VulnerabilitySeverity.MEDIUM,
                "severity_score": 5.3,
                "category": "Cryptographic Issues",
                "cwe_id": "CWE-338",
                "owasp_category": "A02:2021 - Cryptographic Failures",
                "file_path": "backend/auth_service.py",
                "line_number": 89,
                "code_snippet": "token = random.randint(100000, 999999)",
                "recommendation": "Use secrets.token_urlsafe() for cryptographically secure random generation"
            },
            {
                "title": "Missing input validation",
                "description": "API endpoint does not validate input parameters",
                "severity": VulnerabilitySeverity.MEDIUM,
                "severity_score": 5.0,
                "category": "Input Validation",
                "cwe_id": "CWE-20",
                "owasp_category": "A03:2021 - Injection",
                "file_path": "backend/api_endpoints.py",
                "line_number": 234,
                "code_snippet": "def update_user(user_id, data):",
                "recommendation": "Add input validation using Pydantic models or similar"
            }
        ]
        
        return vulnerabilities
    
    def _calculate_code_quality_score(self, vulnerabilities: List[Dict[str, Any]]) -> float:
        """Calculate overall code quality score (0-100)"""
        if not vulnerabilities:
            return 100.0
        
        # Weighted scoring based on severity
        severity_weights = {
            VulnerabilitySeverity.CRITICAL: 20,
            VulnerabilitySeverity.HIGH: 10,
            VulnerabilitySeverity.MEDIUM: 5,
            VulnerabilitySeverity.LOW: 2,
            VulnerabilitySeverity.INFO: 1
        }
        
        total_penalty = sum(
            severity_weights.get(v["severity"], 1)
            for v in vulnerabilities
        )
        
        # Score decreases with more/severe vulnerabilities
        score = max(0, 100 - total_penalty)
        
        return round(score, 1)
    
    def _calculate_maintainability_score(self, scan: Dict[str, Any]) -> float:
        """Calculate maintainability score"""
        # Simulated - in production, analyze code complexity, duplication, etc.
        return 75.0
    
    def _calculate_reliability_score(self, scan: Dict[str, Any]) -> float:
        """Calculate reliability score"""
        # Simulated - in production, analyze bug patterns, error handling, etc.
        return 80.0
    
    def _calculate_security_score(self, scan: Dict[str, Any]) -> float:
        """Calculate security score"""
        return scan.get("code_quality_score", 70.0)
    
    def _calculate_coverage_score(self, scan: Dict[str, Any]) -> float:
        """Calculate test coverage score"""
        # Simulated - in production, integrate with coverage tools
        return 65.0
    
    def _generate_summary(self, vulnerabilities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate scan summary"""
        severity_counts = {
            VulnerabilitySeverity.CRITICAL: 0,
            VulnerabilitySeverity.HIGH: 0,
            VulnerabilitySeverity.MEDIUM: 0,
            VulnerabilitySeverity.LOW: 0,
            VulnerabilitySeverity.INFO: 0
        }
        
        for vuln in vulnerabilities:
            severity = vuln.get("severity", VulnerabilitySeverity.INFO)
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        return {
            "total": len(vulnerabilities),
            "by_severity": severity_counts,
            "critical_count": severity_counts[VulnerabilitySeverity.CRITICAL],
            "high_count": severity_counts[VulnerabilitySeverity.HIGH],
            "medium_count": severity_counts[VulnerabilitySeverity.MEDIUM],
            "low_count": severity_counts[VulnerabilitySeverity.LOW]
        }
    
    def _load_security_patterns(self) -> List[Dict[str, Any]]:
        """Load custom security patterns"""
        return [
            {
                "pattern": r"password\s*=\s*['\"][^'\"]+['\"]",
                "severity": VulnerabilitySeverity.CRITICAL,
                "description": "Hardcoded password detected"
            },
            {
                "pattern": r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]",
                "severity": VulnerabilitySeverity.CRITICAL,
                "description": "Hardcoded API key detected"
            },
            {
                "pattern": r"eval\s*\(",
                "severity": VulnerabilitySeverity.HIGH,
                "description": "Use of eval() detected - potential code injection"
            }
        ]


# Singleton
_sast_service: Optional[SASTService] = None

def get_sast_service(db: AsyncIOMotorDatabase) -> SASTService:
    """Get or create SAST service singleton"""
    global _sast_service
    if _sast_service is None:
        _sast_service = SASTService(db)
    return _sast_service
