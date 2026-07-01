"""
Enhanced SOAR Playbook Engine

Advanced playbook execution engine with:
- Conditional branching (if/else/switch)
- Loops (for/while)
- Error handling and retry logic
- Parallel execution
- Approval gates
- Variable passing between steps
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from enhanced_playbook_enums import StepStatus
from playbook_engine_actions import PlaybookActionsMixin
from playbook_engine_execution import PlaybookExecutionMixin
from playbook_engine_safety import PlaybookSafetyMixin

# Re-export for any external code that imports StepStatus from this module
__all__ = ["PlaybookExecutionEngine", "get_playbook_engine", "process_approval_timeouts", "StepStatus"]


class PlaybookExecutionEngine(PlaybookSafetyMixin, PlaybookExecutionMixin, PlaybookActionsMixin):
    """Advanced playbook execution engine with conditional logic and error handling."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.logger = logging.getLogger("PlaybookEngine")
        self.actions: Dict[str, Callable] = {}
        self._register_default_actions()

    def _register_default_actions(self):
        self.actions = {
            "log":               self._action_log,
            "http_request":      self._action_http_request,
            "send_notification": self._action_send_notification,
            "create_ticket":     self._action_create_ticket,
            "block_ip":          self._action_block_ip,
            "isolate_endpoint":  self._action_isolate_endpoint,
            "quarantine_file":   self._action_quarantine_file,
            "rollback_ransomware": self._action_rollback_ransomware,
            "send_email":        self._action_send_email,
            "wait":              self._action_wait,
            "set_variable":      self._action_set_variable,
        }

    def register_action(self, name: str, handler: Callable):
        self.actions[name] = handler

    async def execute_playbook(
        self,
        playbook_id: str,
        trigger_data: Dict[str, Any],
        tenant_id: str,
        executed_by: str,
    ) -> Dict[str, Any]:
        playbook = await self.db.playbooks.find_one({"_id": playbook_id})
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")

        execution = {
            "playbook_id":   playbook_id,
            "playbook_name": playbook.get("name"),
            "tenant_id":     tenant_id,
            "executed_by":   executed_by,
            "trigger_data":  trigger_data,
            "status":        "running",
            "started_at":    datetime.now(timezone.utc).isoformat(),
            "completed_at":  None,
            "steps":         [],
            "variables":     {},
            "error":         None,
        }
        result = await self.db.playbook_executions.insert_one(execution)
        execution_id = str(result.inserted_id)

        try:
            context = {
                "variables":   {"trigger": trigger_data},
                "execution_id": execution_id,
                "tenant_id":   tenant_id,
                "executed_by": executed_by,
            }
            for step_index, step in enumerate(playbook.get("steps", [])):
                step_result = await self._execute_step(step, context, execution_id, step_index)

                if step_result["status"] == StepStatus.WAITING_APPROVAL.value:
                    await self.db.playbook_executions.update_one(
                        {"_id": execution_id},
                        {"$set": {
                            "status": "waiting_approval",
                            "current_step": step_index,
                            "variables": context["variables"],
                        }},
                    )
                    return {
                        "execution_id": execution_id,
                        "status": "waiting_approval",
                        "message": "Playbook execution paused for approval",
                    }

                if step_result["status"] == StepStatus.FAILED.value:
                    if not step.get("continue_on_error", False):
                        raise Exception(f"Step {step_index} failed: {step_result.get('error')}")

                if step.get("type") == "condition":
                    if not self._evaluate_condition(step.get("condition"), context):
                        continue

            await self.db.playbook_executions.update_one(
                {"_id": execution_id},
                {"$set": {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "variables": context["variables"],
                }},
            )
            return {"execution_id": execution_id, "status": "completed", "variables": context["variables"]}

        except Exception as e:
            self.logger.error(f"Playbook execution failed: {e}")
            await self.db.playbook_executions.update_one(
                {"_id": execution_id},
                {"$set": {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }},
            )
            return {"execution_id": execution_id, "status": "failed", "error": str(e)}

    async def resume_playbook_execution(
        self, execution_id: str, tenant_id: str
    ) -> Dict[str, Any]:
        execution = await self.db.playbook_executions.find_one(
            {"_id": execution_id, "tenant_id": tenant_id}
        )
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        playbook = await self.db.playbooks.find_one({"_id": execution["playbook_id"]})
        if not playbook:
            raise ValueError(f"Playbook {execution['playbook_id']} not found")

        context = {
            "variables":   execution.get("variables", {}),
            "execution_id": execution_id,
            "tenant_id":   tenant_id,
            "executed_by": execution.get("executed_by"),
        }
        await self.db.playbook_executions.update_one(
            {"_id": execution_id},
            {"$set": {"status": "running", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )

        try:
            start_step = execution.get("current_step", 0) + 1
            steps = playbook.get("steps", [])
            for step_index in range(start_step, len(steps)):
                step = steps[step_index]
                step_result = await self._execute_step(step, context, execution_id, step_index)

                if step_result["status"] == StepStatus.WAITING_APPROVAL.value:
                    await self.db.playbook_executions.update_one(
                        {"_id": execution_id},
                        {"$set": {
                            "status": "waiting_approval",
                            "current_step": step_index,
                            "variables": context["variables"],
                        }},
                    )
                    return {
                        "execution_id": execution_id,
                        "status": "waiting_approval",
                        "message": "Playbook paused again for approval",
                    }

                if step_result["status"] == StepStatus.FAILED.value:
                    if not step.get("continue_on_error", False):
                        raise Exception(f"Step {step_index} failed: {step_result.get('error')}")

            await self.db.playbook_executions.update_one(
                {"_id": execution_id},
                {"$set": {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "variables": context["variables"],
                }},
            )
            return {"execution_id": execution_id, "status": "completed"}

        except Exception as e:
            self.logger.error(f"Playbook resumption failed: {e}")
            await self.db.playbook_executions.update_one(
                {"_id": execution_id},
                {"$set": {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }},
            )
            return {"execution_id": execution_id, "status": "failed", "error": str(e)}

    async def _request_approval(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        execution_id: str,
        step_index: int,
        action_name: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Request human approval for a step.
        timeout_action controls what happens if no human responds:
            "escalate"     — emit a high-priority notification (default)
            "auto_approve" — resume the playbook automatically
            "skip"         — skip this step and continue
        """
        timeout_minutes = step.get("timeout_minutes", 60)
        timeout_action  = step.get("timeout_action", "escalate")
        expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
        ).isoformat()

        approval_request = {
            "execution_id":   execution_id,
            "step_index":     step_index,
            "step_name":      step.get("name"),
            "description":    step.get("description"),
            "approvers":      step.get("approvers", []),
            "timeout_minutes": timeout_minutes,
            "timeout_action": timeout_action,
            "expires_at":     expires_at,
            "action_name":    action_name,
            "agent_id":       agent_id,
            "status":         "pending",
            "created_at":     datetime.now(timezone.utc).isoformat(),
            "approved_by":    None,
            "approved_at":    None,
        }
        await self.db.playbook_approvals.insert_one(approval_request)
        self.logger.info(
            "Approval gate created for execution %s step %d (timeout=%dm action=%s)",
            execution_id, step_index, timeout_minutes, timeout_action,
        )
        return {"status": StepStatus.WAITING_APPROVAL.value, "message": "Waiting for approval"}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_playbook_engine: Optional[PlaybookExecutionEngine] = None


def get_playbook_engine(db: AsyncIOMotorDatabase) -> PlaybookExecutionEngine:
    global _playbook_engine
    if _playbook_engine is None:
        _playbook_engine = PlaybookExecutionEngine(db)
    return _playbook_engine


async def process_approval_timeouts(db: AsyncIOMotorDatabase) -> None:
    """
    Background task: check for expired approval requests and act according
    to their timeout_action field.
    Should be called periodically (e.g. every 60 s) from app.py lifespan.
    """
    logger = logging.getLogger("PlaybookEngine.Timeouts")
    now = datetime.now(timezone.utc).isoformat()

    expired = await db.playbook_approvals.find({
        "status": "pending",
        "expires_at": {"$lt": now},
    }).to_list(length=100)

    for req in expired:
        req_id         = str(req.get("_id"))
        timeout_action = req.get("timeout_action", "escalate")
        execution_id   = req.get("execution_id")

        if timeout_action == "auto_approve":
            await db.playbook_approvals.update_one(
                {"_id": req["_id"]},
                {"$set": {"status": "auto_approved", "approved_by": "system-timeout", "approved_at": now}},
            )
            logger.info("Approval %s auto-approved after timeout", req_id)
            engine = get_playbook_engine(db)
            asyncio.create_task(
                engine.resume_playbook_execution(execution_id, req.get("tenant_id", ""))
            )

        elif timeout_action == "skip":
            await db.playbook_approvals.update_one(
                {"_id": req["_id"]},
                {"$set": {"status": "skipped", "resolved_at": now}},
            )
            logger.info("Approval %s step skipped after timeout", req_id)
            engine = get_playbook_engine(db)
            asyncio.create_task(
                engine.resume_playbook_execution(execution_id, req.get("tenant_id", ""))
            )

        else:  # escalate (default)
            await db.playbook_approvals.update_one(
                {"_id": req["_id"]},
                {"$set": {"status": "escalated", "escalated_at": now}},
            )
            await db.playbook_notifications.insert_one({
                "channel":              "soc",
                "priority":             "high",
                "message": (
                    f"ESCALATION: Approval request for playbook execution {execution_id} "
                    f"(action: {req.get('action_name', 'unknown')}, "
                    f"agent: {req.get('agent_id', 'unknown')}) has expired without a decision."
                ),
                "execution_id":         execution_id,
                "approval_request_id":  req_id,
                "created_at":           now,
            })
            logger.warning("Approval %s escalated after timeout (no human response)", req_id)
