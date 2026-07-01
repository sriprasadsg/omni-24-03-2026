from typing import Dict, Any, List
import subprocess
import shlex
import logging
import platform
import re
import os
import requests
import json
from .base import BaseCapability

logger = logging.getLogger(__name__)

# Commands must start with one of these approved prefixes.
# Glob-style: literal prefix match against the full command string.
_COMMAND_ALLOWLIST: List[re.Pattern] = [
    re.compile(r"^(net\s+stop|net\s+start)\s+\w", re.IGNORECASE),          # Windows service control
    re.compile(r"^sc\s+(stop|start|query)\s+\w", re.IGNORECASE),            # Windows sc.exe
    re.compile(r"^powershell\s+-NonInteractive\s+-Command\s+", re.IGNORECASE),  # Restricted PS
    re.compile(r"^systemctl\s+(stop|start|restart|status)\s+\w", re.IGNORECASE),  # Linux services
    re.compile(r"^apt(-get)?\s+(install|remove)\s+(-y\s+)?\w", re.IGNORECASE),   # Linux packages
    re.compile(r"^yum\s+(install|remove)\s+(-y\s+)?\w", re.IGNORECASE),
    re.compile(r"^dnf\s+(install|remove)\s+(-y\s+)?\w", re.IGNORECASE),
    re.compile(r"^chkconfig\s+\w", re.IGNORECASE),
    re.compile(r"^netsh\s+advfirewall\s+", re.IGNORECASE),                  # Windows firewall
    re.compile(r"^iptables\s+-", re.IGNORECASE),                             # Linux firewall
]


def _is_command_allowed(cmd: str) -> bool:
    """Return True only if cmd matches an approved prefix pattern."""
    return any(p.match(cmd.strip()) for p in _COMMAND_ALLOWLIST)

class RemediationCapability(BaseCapability):
    """
    Polls the backend for approved remediation tasks and executes them.
    Implements the 'Active Defense' component of the platform.
    """
    
    @property
    def capability_id(self) -> str:
        return "remediation_executor"

    @property
    def capability_name(self) -> str:
        return "Remediation & SOAR Executor"

    def collect(self) -> Dict[str, Any]:
        """
        1. Poll for pending jobs
        2. Execute commands (if any)
        3. Report results
        """
        base_url = self.config.get("api_url", "http://localhost:5000")
        agent_id = self.config.get("agent_id", "unknown-agent")
        
        executed_jobs = []
        
        try:
            # 1. Fetch pending jobs
            # This endpoint needs to be implemented or we reuse the general requests endpoint with filters
            # For Phase 1, we assume a specific endpoint for agents to pull work
            # For now, let's simulate checking the requests endpoint or define a new one in the backend later
            # Ideally: POST /api/remediation/poll
            
            # Since backends usually push or agent polls, let's try a simple poll
            # We will reuse the 'requests' list but filtered by agent_id and status='approved' not 'executed'
            # Note: In a real system, we'd add authentication headers here
            
            agent_token = self.config.get("agent_token", "")
            _auth_headers = {"Authorization": f"Bearer {agent_token}"} if agent_token else {}
            response = requests.get(f"{base_url}/api/remediation/requests", headers=_auth_headers)
            if response.status_code == 200:
                all_requests = response.json()
                # Filter client-side for MVP (Server-side constraint better for prod)
                my_jobs = [
                    r for r in all_requests 
                    if r.get("agent_id") == agent_id and r.get("status") == "approved"
                ]
                
                for job in my_jobs:
                    result = self._execute_job(job, base_url)
                    executed_jobs.append(result)
                    
        except Exception as e:
            logger.error("Error polling remediation jobs: %s", e)
            return {"error": str(e)}

        return {
            "jobs_executed": len(executed_jobs),
            "details": executed_jobs
        }

    def _execute_job(self, job: Dict[str, Any], base_url: str) -> Dict[str, Any]:
        job_id = job.get("id")
        playbook_id = job.get("playbook_id")
        
        logger.info("Executing Remediation Job %s (Playbook: %s)", job_id, playbook_id)
        
        # In a real implementation, we would fetch the Playbook definition to get the command
        # or the job itself would contain the signed command. 
        # For this MVP, we will fetch the playbook.
        
        try:
            _agent_token = self.config.get("agent_token", "")
            _auth_headers = {"Authorization": f"Bearer {_agent_token}"} if _agent_token else {}
            pb_resp = requests.get(f"{base_url}/api/remediation/playbooks", headers=_auth_headers)
            if pb_resp.status_code != 200:
                return {"job_id": job_id, "status": "failed", "reason": "could_not_fetch_playbook"}
            
            playbooks = pb_resp.json()
            playbook = next((p for p in playbooks if p["id"] == playbook_id), None)
            
            if not playbook:
                return {"job_id": job_id, "status": "failed", "reason": "playbook_not_found"}
                
            # Execute Actions
            execution_log = []
            overall_success = True
            
            for action in playbook.get("actions", []):
                if action.get("type") == "command":
                    cmd = action.get("command")
                    if cmd:
                        if not _is_command_allowed(cmd):
                            logger.warning("[Remediation] Blocked disallowed command: %s", cmd)
                            execution_log.append({"action": "command", "cmd": cmd,
                                                   "output": "BLOCKED: command not on allowlist",
                                                   "success": False})
                            overall_success = False
                            continue
                        logger.info("Running command: %s", cmd)
                        try:
                            proc = subprocess.run(shlex.split(cmd), shell=False, capture_output=True, text=True, timeout=30)
                            output = proc.stdout + proc.stderr
                            success = (proc.returncode == 0)
                            execution_log.append({
                                "action": "command", 
                                "cmd": cmd, 
                                "output": output, 
                                "success": success
                            })
                            if not success:
                                overall_success = False
                        except Exception as e:
                            execution_log.append({"action": "command", "error": str(e), "success": False})
                            overall_success = False
                            
            # Update Backend
            # POST /api/remediation/result or update status
            # We'll reuse the update endpoint but we verify fields match what we wrote in backend
            # Actually backend only has 'approve'. We need 'complete'. 
            # We will ignore updating backend status for this exact step and just log it, 
            # assuming we'd add a "complete" endpoint in next iteration.
            
            return {
                "job_id": job_id,
                "status": "success" if overall_success else "failed",
                "log": execution_log
            }
            
        except Exception as e:
            logger.error("Job execution failed: %s", e)
            return {"job_id": job_id, "status": "error", "error": str(e)}
