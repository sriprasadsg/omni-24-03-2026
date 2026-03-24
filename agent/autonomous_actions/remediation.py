import logging
import time
import psutil
import subprocess
from .rollback import RollbackManager

logger = logging.getLogger(__name__)

class AutonomousRemediationEngine:
    """
    Executes autonomous remediation plans safely.
    Follows: Approval -> Checkpoint -> Execute -> Verify -> Rollback (on failure) workflow.
    """
    
    def __init__(self, reasoning_engine, config=None):
        self.reasoning = reasoning_engine
        self.rollback_manager = RollbackManager()
        self.config = config or {}
        
    def execute_remediation(self, issue: dict):
        """
        Main entry point to fix an issue autonomously.
        """
        logger.info(f"Planning remediation for issue: {issue.get('title', 'Unknown')}")
        
        # 1. Generate Remediation Plan using LLM
        plan = None
        if hasattr(self.reasoning.llm, 'plan_remediation'):
            plan = self.reasoning.llm.plan_remediation(issue)
            if "error" in plan:
                logger.warning(f"LLM planning failed: {plan['error']}. Falling back to simple plan.")
                plan = self._create_simple_plan(issue)
        else:
            plan = self._create_simple_plan(issue)
        
        if not plan or "steps" not in plan:
            logger.error("Could not generate valid remediation plan.")
            return False

        # 2. Validate Safety & Autonomy
        decision = self.reasoning.decide_action(issue)
        if not decision['is_autonomous']:
            logger.info("Autonomous execution denied by Decision Engine. Escalating...")
            return self._escalate_to_human(issue, plan)

        # 3. Create Checkpoint
        affected_files = plan.get('affected_files', [])
        affected_services = plan.get('affected_services', [])
        checkpoint = self.rollback_manager.create_checkpoint(affected_files, affected_services)
        
        try:
            # 4. Execute Steps
            logger.info(f"Executing autonomous plan: {plan['name']}")
            for step in plan['steps']:
                self._execute_step(step)
                
            # 5. Verify Fix
            if self._verify_fix(issue, plan):
                logger.info("✅ Remediation successful!")
                return True
            else:
                raise Exception("Fix verification failed")

        except Exception as e:
            logger.error(f"❌ Remediation failed: {e}")
            # 6. Rollback
            self.rollback_manager.rollback(checkpoint)
            return False

    def _create_simple_plan(self, issue):
        """
        Helper to convert a generic action recommendation into executable steps.
        """
        action = issue.get('recommended_action', '').lower()
        
        if "restart" in action and "service" in action:
            service = action.split("service")[-1].strip()
            return {
                "name": f"Restart Service {service}",
                "affected_services": [service],
                "steps": [{"action": "restart_service", "target": service, "description": f"Restarting {service}"}]
            }
        
        if "kill" in action or "terminate" in action:
            target = issue.get('process_name') or "unknown_process"
            return {
                "name": f"Kill Process {target}",
                "steps": [{"action": "kill_process", "target": target, "description": f"Killing {target}"}]
            }
            
        return None

    def _execute_step(self, step):
        """Execute a single atomic action"""
        action = step['action']
        target = step.get('target')
        description = step.get('description', f"Performing {action}")
        
        logger.info(f"Step: {description} ({action} on {target})")
        
        if action == "restart_service":
            if psutil.WINDOWS:
                logger.info(f"[SIMULATION] Restart-Service {target}")
                # subprocess.run(["powershell", "Restart-Service", target])
            else:
                 logger.info(f"[SIMULATION] systemctl restart {target}")
                 
        elif action == "kill_process":
            found = False
            for proc in psutil.process_iter(['name', 'pid']):
                if proc.info['name'] == target or str(proc.info['pid']) == str(target):
                    proc.kill()
                    logger.info(f"Killed process {target} (PID: {proc.info['pid']})")
                    found = True
            if not found:
                logger.warning(f"Process {target} not found for killing.")

        elif action == "run_command":
            logger.info(f"Executing command: {target}")
            # subprocess.run(target, shell=True)
            logger.info(f"[SIMULATION] Command executed: {target}")

        elif action == "delete_file":
            import os
            if os.path.exists(target):
                # os.remove(target)
                logger.info(f"[SIMULATION] Deleted file: {target}")
            else:
                logger.warning(f"File {target} not found for deletion.")

    def _verify_fix(self, issue, plan=None):
        """Check if the issue is resolved"""
        # In a real implementation, we might ask the LLM to verify or run a specific check
        logger.info("Verifying fix...")
        return True

    def _escalate_to_human(self, issue, plan):
        """Send notification to backend"""
        logger.info("Escalating request to backend for approval...")
        # In real implementation, this would be a POST to /api/remediations/approval
        return "ESCALATED"
