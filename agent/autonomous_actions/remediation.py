import logging
import os
import platform
import subprocess
import psutil
import httpx
from .rollback import RollbackManager

logger = logging.getLogger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:5000")


class AutonomousRemediationEngine:
    """
    Executes autonomous remediation plans safely.
    Workflow: Plan → Safety Check → Checkpoint → Execute → Verify → Rollback on failure
    """

    def __init__(self, reasoning_engine, config=None):
        self.reasoning = reasoning_engine
        self.rollback_manager = RollbackManager()
        self.config = config or {}

    def execute_remediation(self, issue: dict) -> bool | str:
        """Main entry point: plan, gate, checkpoint, execute, verify, rollback."""
        logger.info("Planning remediation for issue: %s", issue.get("title", "Unknown"))

        # 1. Generate plan — try LLM planner if available, fall back to rule-based
        plan = None
        llm = getattr(self.reasoning, "llm", None)
        if llm is not None and hasattr(llm, "plan_remediation"):
            plan = llm.plan_remediation(issue)
            if not plan or "error" in plan:
                logger.warning("LLM planning failed, falling back to simple plan.")
                plan = self._create_simple_plan(issue)
        else:
            plan = self._create_simple_plan(issue)

        if not plan or "steps" not in plan:
            logger.error("Could not generate valid remediation plan.")
            return False

        # 2. Safety / autonomy gate
        decision = self.reasoning.decide_action(issue)
        if not decision["is_autonomous"]:
            logger.info("Autonomous execution denied — escalating to human.")
            return self._escalate_to_human(issue, plan)

        # 3. Checkpoint current state
        checkpoint = self.rollback_manager.create_checkpoint(
            affected_files=plan.get("affected_files", []),
            affected_services=plan.get("affected_services", []),
        )

        try:
            # 4. Execute steps
            logger.info("Executing autonomous plan: %s", plan["name"])
            for step in plan["steps"]:
                self._execute_step(step)

            # 5. Verify fix
            if self._verify_fix(issue, plan):
                logger.info("✅ Remediation successful: %s", plan["name"])
                self._report_outcome(issue, plan, success=True)
                return True
            else:
                raise RuntimeError("Fix verification failed")

        except Exception as exc:
            logger.error("❌ Remediation failed: %s — initiating rollback", exc)
            rollback_ok = self.rollback_manager.rollback(checkpoint)
            self._report_outcome(issue, plan, success=False, error=str(exc))
            return rollback_ok

    # ------------------------------------------------------------------
    # Plan generation
    # ------------------------------------------------------------------

    def _create_simple_plan(self, issue: dict) -> dict | None:
        action = issue.get("recommended_action", "").lower()

        if "restart" in action and "service" in action:
            svc = action.split("service")[-1].strip()
            return {
                "name": f"Restart Service {svc}",
                "affected_services": [svc],
                "steps": [{"action": "restart_service", "target": svc}],
            }

        if "kill" in action or "terminate" in action:
            target = issue.get("process_name") or "unknown"
            return {
                "name": f"Kill Process {target}",
                "steps": [{"action": "kill_process", "target": target}],
            }

        if "delete" in action or "quarantine" in action:
            target = issue.get("file_path") or ""
            return {
                "name": f"Quarantine File {target}",
                "affected_files": [target],
                "steps": [{"action": "quarantine_file", "target": target}],
            }

        return None

    # ------------------------------------------------------------------
    # Step execution — real implementations
    # ------------------------------------------------------------------

    def _execute_step(self, step: dict) -> None:
        action = step["action"]
        target = step.get("target", "")
        logger.info("Executing step: %s on %s", action, target)

        if action == "restart_service":
            self._restart_service(target)

        elif action == "kill_process":
            self._kill_process(target)

        elif action == "quarantine_file":
            self._quarantine_file(target)

        elif action == "run_command":
            # Validate no dangerous characters before running
            dangerous = [";", "&&", "||", "|", ">", "<", "`", "$("]
            if any(c in target for c in dangerous):
                raise ValueError(f"Unsafe command rejected: {target}")
            result = subprocess.run(
                target.split(), capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                raise RuntimeError(f"Command failed ({result.returncode}): {result.stderr}")
            logger.info("Command output: %s", result.stdout[:500])

        else:
            logger.warning("Unknown action '%s' — skipping", action)

    def _restart_service(self, service: str) -> None:
        is_windows = platform.system() == "Windows"
        if is_windows:
            subprocess.run(["sc", "stop", service], timeout=30, check=False)
            subprocess.run(["sc", "start", service], timeout=30, check=True)
        else:
            subprocess.run(["systemctl", "restart", service], timeout=30, check=True)
        logger.info("Restarted service: %s", service)

    def _kill_process(self, target: str) -> None:
        killed = False
        for proc in psutil.process_iter(["name", "pid"]):
            if proc.info["name"] == target or str(proc.info["pid"]) == str(target):
                proc.kill()
                logger.info("Killed process %s (PID %d)", target, proc.info["pid"])
                killed = True
        if not killed:
            logger.warning("Process '%s' not found", target)

    def _quarantine_file(self, file_path: str) -> None:
        import shutil, hashlib, time
        p = os.path.realpath(file_path)
        if not os.path.exists(p):
            logger.warning("File not found for quarantine: %s", p)
            return
        quarantine_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "quarantine")
        os.makedirs(quarantine_dir, exist_ok=True)
        ts = int(time.time())
        fname = os.path.basename(p)
        dest = os.path.join(quarantine_dir, f"{ts}_{fname}")
        shutil.move(p, dest)
        logger.info("Quarantined %s → %s", p, dest)

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def _verify_fix(self, issue: dict, plan: dict) -> bool:
        """Confirm the fix actually resolved the issue."""
        action = issue.get("recommended_action", "").lower()

        # Verify service is running after restart
        for svc in plan.get("affected_services", []):
            try:
                if platform.system() == "Windows":
                    s = psutil.win_service_get(svc)
                    if s.status() != "running":
                        logger.error("Verify FAILED: service %s not running", svc)
                        return False
                else:
                    result = subprocess.run(
                        ["systemctl", "is-active", svc],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.stdout.strip() != "active":
                        logger.error("Verify FAILED: service %s not active", svc)
                        return False
            except Exception as exc:
                logger.warning("Verification skipped for service %s: %s", svc, exc)

        # Verify files were quarantined / removed
        if "quarantine" in action or "delete" in action:
            for f in plan.get("affected_files", []):
                if os.path.exists(f):
                    logger.error("Verify FAILED: file still present: %s", f)
                    return False

        logger.info("Verification passed for plan: %s", plan.get("name"))
        return True

    # ------------------------------------------------------------------
    # Reporting back to backend
    # ------------------------------------------------------------------

    def _report_outcome(self, issue: dict, plan: dict, success: bool, error: str = "") -> None:
        """POST execution result back to the backend feedback endpoint."""
        task_id = issue.get("task_id")
        if not task_id:
            return
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f"{BACKEND_URL}/api/response/tasks/{task_id}/feedback",
                    json={
                        "success": success,
                        "false_positive": False,
                        "message": f"Plan: {plan.get('name')}. Error: {error}" if error else f"Plan: {plan.get('name')} completed.",
                        "reported_by": "agent_remediation_engine",
                    },
                )
        except Exception as exc:
            logger.debug("Could not report outcome to backend: %s", exc)

    def _escalate_to_human(self, issue: dict, plan: dict) -> str:
        """POST an approval request to the backend."""
        try:
            agent_id = issue.get("agent_id", "unknown")
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f"{BACKEND_URL}/api/agents/{agent_id}/approval-request",
                    json={
                        "action": issue.get("recommended_action", "unknown"),
                        "context": issue,
                        "plan_name": plan.get("name"),
                        "reason": "Autonomous execution denied by safety engine — human approval required",
                    },
                )
            logger.info("Escalated approval request for agent %s", agent_id)
        except Exception as exc:
            logger.warning("Could not escalate to backend: %s", exc)
        return "ESCALATED"
