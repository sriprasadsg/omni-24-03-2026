"""
Penetration Testing Integration Service

Integrates with industry-standard security testing tools:
- Nmap: Network discovery and port scanning
- Nikto: Web server vulnerability scanning
- OpenVAS: Comprehensive vulnerability assessment
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
import subprocess
import socket
import logging
from bson import ObjectId
from pentest_service_tools import PentestToolsMixin

logger = logging.getLogger(__name__)

# Tool availability is checked once per process to avoid repeated subprocess calls
_TOOL_AVAILABILITY: Dict[str, bool] = {}


def _validate_scan_target(target: str) -> None:
    """Reject targets that resolve to private/loopback/reserved addresses (including via DNS)."""
    import ipaddress
    from urllib.parse import urlparse as _urlparse

    if not target:
        raise ValueError("Scan target is required")

    parsed = _urlparse(target if "://" in target else f"scheme://{target}")
    hostname = parsed.hostname or target.split(":")[0]

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve target hostname: {hostname}")

    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if (addr.is_private or addr.is_loopback or
                addr.is_link_local or addr.is_reserved or addr.is_multicast):
            raise ValueError(
                f"Target '{hostname}' resolves to non-public address {info[4][0]} — scanning not permitted"
            )


class PentestIntegrationService(PentestToolsMixin):
    """Penetration Testing Tool Integration Service"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        
        # Tool configurations
        self.tools = {
            "nmap": {
                "name": "Nmap",
                "type": "network_scanner",
                "command": "nmap",
                "available": self._check_tool_available("nmap")
            },
            "nikto": {
                "name": "Nikto",
                "type": "web_scanner",
                "command": "nikto",
                "available": self._check_tool_available("nikto")
            },
            "openvas": {
                "name": "OpenVAS",
                "type": "vulnerability_scanner",
                "command": "gvm-cli",
                "available": False  # Requires separate setup
            }
        }
        
        # Scan templates
        self.scan_templates = {
            "quick_network_scan": {
                "tool": "nmap",
                "description": "Quick network scan (top 100 ports)",
                "args": ["-F", "-sV", "--version-light"]
            },
            "full_network_scan": {
                "tool": "nmap",
                "description": "Comprehensive network scan (all ports)",
                "args": ["-p-", "-sV", "-sC", "-O", "--osscan-guess"]
            },
            "web_vulnerability_scan": {
                "tool": "nikto",
                "description": "Web server vulnerability scan",
                "args": ["-Tuning", "x"]
            },
            "safe_scan": {
                "tool": "nmap",
                "description": "Safe scan (no intrusive tests)",
                "args": ["-sV", "-sC", "--script=safe"]
            },
            "aggressive_scan": {
                "tool": "nmap",
                "description": "Aggressive scan (may trigger IDS)",
                "args": ["-A", "-T4"]
            }
        }
    
    def _check_tool_available(self, tool: str) -> bool:
        """Check if a tool is installed and available (result cached per process)."""
        if tool not in _TOOL_AVAILABILITY:
            try:
                result = subprocess.run(
                    [tool, "--version"],
                    capture_output=True,
                    timeout=5
                )
                _TOOL_AVAILABILITY[tool] = result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                _TOOL_AVAILABILITY[tool] = False
        return _TOOL_AVAILABILITY[tool]
    
    async def create_scan_job(
        self,
        target: str,
        scan_type: str,
        tenant_id: str,
        created_by: str,
        custom_args: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new penetration testing scan job
        
        Args:
            target: Target IP, domain, or URL
            scan_type: Template name or tool name
            tenant_id: Tenant ID
            created_by: User who initiated the scan
            custom_args: Custom arguments (optional)
        
        Returns:
            Scan job document
        """
        # Allowlist of nmap flags permitted in custom_args (no write-output, no script-args, no NSE exploits)
        _NMAP_ARG_ALLOWLIST: frozenset[str] = frozenset({
            "-sV", "-sC", "-sS", "-sT", "-sU", "-sA", "-sN", "-sF", "-sX",
            "-F", "-p-", "-O", "--osscan-guess", "-T1", "-T2", "-T3", "-T4",
            "--version-light", "--version-intensity", "--script=safe",
            "--script=default", "--script=vuln", "--script=discovery",
            "-Pn", "-PE", "-PP", "-PM", "--open", "-v", "-vv",
        })

        # Get scan template or use custom
        if scan_type in self.scan_templates:
            template = self.scan_templates[scan_type]
            tool = template["tool"]
            if custom_args:
                for arg in custom_args:
                    if arg not in _NMAP_ARG_ALLOWLIST:
                        raise ValueError(
                            f"Argument '{arg}' is not in the permitted nmap argument allowlist."
                        )
            args = template["args"] if not custom_args else custom_args
            description = template["description"]
        else:
            tool = scan_type
            if custom_args:
                for arg in custom_args:
                    if arg not in _NMAP_ARG_ALLOWLIST:
                        raise ValueError(
                            f"Argument '{arg}' is not in the permitted nmap argument allowlist."
                        )
            args = custom_args or []
            description = f"Custom {tool} scan"
        
        # Validate scan target before storing
        _validate_scan_target(target)

        # Validate tool availability
        if not self.tools.get(tool, {}).get("available"):
            raise ValueError(f"Tool {tool} is not available. Please install it first.")
        
        # Create job document
        job = {
            "tenant_id": tenant_id,
            "target": target,
            "tool": tool,
            "scan_type": scan_type,
            "description": description,
            "args": args,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": created_by,
            "started_at": None,
            "completed_at": None,
            "results": None,
            "findings": [],
            "error": None
        }
        
        result = await self.db.pentest_jobs.insert_one(job)
        job["id"] = str(result.inserted_id)
        
        return job
    
    async def execute_scan(self, job_id: str) -> Dict[str, Any]:
        """
        Execute a penetration testing scan
        
        This should be called asynchronously (background task)
        """
        # Get job
        job = await self.db.pentest_jobs.find_one({"_id": ObjectId(job_id)})
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Update status to running
        await self.db.pentest_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {
                "$set": {
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        try:
            # Execute scan based on tool
            if job["tool"] == "nmap":
                results = await self._execute_nmap(job["target"], job["args"])
            elif job["tool"] == "nikto":
                results = await self._execute_nikto(job["target"], job["args"])
            elif job["tool"] == "openvas":
                results = await self._execute_openvas(job["target"], job["args"])
            else:
                raise ValueError(f"Unknown tool: {job['tool']}")
            
            # Parse findings
            findings = self._parse_findings(results, job["tool"])
            
            # Update job with results
            await self.db.pentest_jobs.update_one(
                {"_id": ObjectId(job_id)},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "results": results,
                        "findings": findings
                    }
                }
            )
            
            # Correlate with existing assets
            await self._correlate_with_assets(job["tenant_id"], job["target"], findings)
            
            return {"status": "completed", "findings_count": len(findings)}
        
        except Exception as e:
            # Update job with error
            await self.db.pentest_jobs.update_one(
                {"_id": ObjectId(job_id)},
                {
                    "$set": {
                        "status": "failed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "error": str(e)
                    }
                }
            )
            raise
    
    async def get_scan_jobs(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get scan jobs for a tenant"""
        query = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        
        cursor = self.db.pentest_jobs.find(query).sort("created_at", -1).limit(limit)
        
        jobs = []
        async for job in cursor:
            job["id"] = str(job.pop("_id"))
            jobs.append(job)
        
        return jobs
    
    async def get_scan_results(self, job_id: str, tenant_id: str) -> Dict[str, Any]:
        """Get detailed scan results"""
        job = await self.db.pentest_jobs.find_one({
            "_id": ObjectId(job_id),
            "tenant_id": tenant_id
        })
        
        if not job:
            raise ValueError("Scan job not found")
        
        job["id"] = str(job.pop("_id"))
        return job
    
    async def schedule_recurring_scan(
        self,
        target: str,
        scan_type: str,
        tenant_id: str,
        created_by: str,
        schedule: str  # cron expression
    ) -> Dict[str, Any]:
        """Schedule a recurring scan"""
        schedule_doc = {
            "tenant_id": tenant_id,
            "target": target,
            "scan_type": scan_type,
            "schedule": schedule,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "last_run": None,
            "next_run": None  # Calculate based on cron
        }
        
        result = await self.db.pentest_schedules.insert_one(schedule_doc)
        schedule_doc["id"] = str(result.inserted_id)
        
        return schedule_doc


def get_pentest_service(db: AsyncIOMotorDatabase) -> PentestIntegrationService:
    """Create a fresh service instance per request so the DB reference is always current."""
    return PentestIntegrationService(db)
