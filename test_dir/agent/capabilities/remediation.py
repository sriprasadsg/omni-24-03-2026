from typing import Dict, Any, List
import subprocess
import logging
import platform
import os
import requests
import json
from .base import BaseCapability

logger = logging.getLogger(__name__)

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
            
            response = requests.get(f"{base_url}/api/remediation/requests")
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
            logger.error(f"Error polling remediation jobs: {e}")
            return {"error": str(e)}

        return {
            "jobs_executed": len(executed_jobs),
            "details": executed_jobs
        }

    def _execute_job(self, job: Dict[str, Any], base_url: str) -> Dict[str, Any]:
        job_id = job.get("id")
        playbook_id = job.get("playbook_id")
        
        logger.info(f"Executing Remediation Job {job_id} (Playbook: {playbook_id})")
        
        # In a real implementation, we would fetch the Playbook definition to get the command
        # or the job itself would contain the signed command. 
        # For this MVP, we will fetch the playbook.
        
        try:
            # Fetch playbook to get the command
            # GET /api/remediation/playbooks
            # Ideally we have GET /api/remediation/playbooks/{id}
            pb_resp = requests.get(f"{base_url}/api/remediation/playbooks")
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
                        # SECURITY: Verify logic would go here (allowlist, signature)
                        logger.info(f"Running command: {cmd}")
                        try:
                            # Use shell=True for MVP, but strictly dangerous in prod
                            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
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
            logger.error(f"Job execution failed: {e}")
            return {"job_id": job_id, "status": "error", "error": str(e)}
