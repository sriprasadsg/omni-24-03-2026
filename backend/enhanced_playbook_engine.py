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

from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import asyncio
import json
import logging
import re as _re
from enum import Enum
from backend_safety import evaluate_action, log_safety_decision, APPROVAL_REQUIRED_ACTIONS


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"


class PlaybookExecutionEngine:
    """Advanced playbook execution engine with conditional logic and error handling"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.logger = logging.getLogger("PlaybookEngine")
        
        # Action registry
        self.actions = {}
        self._register_default_actions()
    
    def _register_default_actions(self):
        """Register default actions"""
        self.actions = {
            "log": self._action_log,
            "http_request": self._action_http_request,
            "send_notification": self._action_send_notification,
            "create_ticket": self._action_create_ticket,
            "block_ip": self._action_block_ip,
            "isolate_endpoint": self._action_isolate_endpoint,
            "quarantine_file": self._action_quarantine_file,
            "rollback_ransomware": self._action_rollback_ransomware,
            "send_email": self._action_send_email,
            "wait": self._action_wait,
            "set_variable": self._action_set_variable,
        }
    
    def register_action(self, name: str, handler: Callable):
        """Register a custom action handler"""
        self.actions[name] = handler
    
    async def execute_playbook(
        self,
        playbook_id: str,
        trigger_data: Dict[str, Any],
        tenant_id: str,
        executed_by: str
    ) -> Dict[str, Any]:
        """
        Execute a playbook with advanced flow control
        
        Args:
            playbook_id: Playbook ID
            trigger_data: Data that triggered the playbook
            tenant_id: Tenant ID
            executed_by: User who triggered execution
        
        Returns:
            Execution result with status and outputs
        """
        # Get playbook
        playbook = await self.db.playbooks.find_one({"_id": playbook_id})
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} not found")
        
        # Create execution record
        execution = {
            "playbook_id": playbook_id,
            "playbook_name": playbook.get("name"),
            "tenant_id": tenant_id,
            "executed_by": executed_by,
            "trigger_data": trigger_data,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "steps": [],
            "variables": {},  # Execution context
            "error": None
        }
        
        result = await self.db.playbook_executions.insert_one(execution)
        execution_id = str(result.inserted_id)
        
        try:
            # Initialize execution context
            context = {
                "variables": {"trigger": trigger_data},
                "execution_id": execution_id,
                "tenant_id": tenant_id,
                "executed_by": executed_by
            }
            
            # Execute steps
            steps = playbook.get("steps", [])
            for step_index, step in enumerate(steps):
                step_result = await self._execute_step(
                    step,
                    context,
                    execution_id,
                    step_index
                )
                
                # Check if step requires approval
                if step_result["status"] == StepStatus.WAITING_APPROVAL.value:
                    # Update execution status and save context
                    await self.db.playbook_executions.update_one(
                        {"_id": execution_id},
                        {
                            "$set": {
                                "status": "waiting_approval",
                                "current_step": step_index,
                                "variables": context["variables"]
                            }
                        }
                    )
                    return {
                        "execution_id": execution_id,
                        "status": "waiting_approval",
                        "message": "Playbook execution paused for approval"
                    }
                
                # Handle step failure
                if step_result["status"] == StepStatus.FAILED.value:
                    if not step.get("continue_on_error", False):
                        raise Exception(f"Step {step_index} failed: {step_result.get('error')}")
                
                # Handle conditional branching
                if step.get("type") == "condition":
                    if not self._evaluate_condition(step.get("condition"), context):
                        # Skip to else branch or next step
                        continue
            
            # Mark execution as completed
            await self.db.playbook_executions.update_one(
                {"_id": execution_id},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "variables": context["variables"]
                    }
                }
            )
            
            return {
                "execution_id": execution_id,
                "status": "completed",
                "variables": context["variables"]
            }
        
        except Exception as e:
            self.logger.error(f"Playbook execution failed: {e}")
            
            # Mark execution as failed
            await self.db.playbook_executions.update_one(
                {"_id": execution_id},
                {
                    "$set": {
                        "status": "failed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "error": str(e)
                    }
                }
            )
            
            return {
                "execution_id": execution_id,
                "status": "failed",
                "error": str(e)
            }

    async def resume_playbook_execution(
        self,
        execution_id: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """Resume a paused playbook execution"""
        execution = await self.db.playbook_executions.find_one({
            "_id": execution_id, 
            "tenant_id": tenant_id
        })
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")
        
        playbook_id = execution["playbook_id"]
        playbook = await self.db.playbooks.find_one({"_id": playbook_id})
        if not playbook:
             raise ValueError(f"Playbook {playbook_id} not found")

        # Reconstruct context from saved state
        context = {
            "variables": execution.get("variables", {}),
            "execution_id": execution_id,
            "tenant_id": tenant_id,
            "executed_by": execution.get("executed_by")
        }

        # Update status back to running
        await self.db.playbook_executions.update_one(
            {"_id": execution_id},
            {"$set": {"status": "running", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

        try:
            start_step = execution.get("current_step", 0) + 1
            steps = playbook.get("steps", [])
            
            for step_index in range(start_step, len(steps)):
                step = steps[step_index]
                step_result = await self._execute_step(
                    step,
                    context,
                    execution_id,
                    step_index
                )
                
                if step_result["status"] == StepStatus.WAITING_APPROVAL.value:
                    await self.db.playbook_executions.update_one(
                        {"_id": execution_id},
                        {
                            "$set": {
                                "status": "waiting_approval",
                                "current_step": step_index,
                                "variables": context["variables"]
                            }
                        }
                    )
                    return {
                        "execution_id": execution_id,
                        "status": "waiting_approval",
                        "message": "Playbook paused again for approval"
                    }
                
                if step_result["status"] == StepStatus.FAILED.value:
                    if not step.get("continue_on_error", False):
                        raise Exception(f"Step {step_index} failed: {step_result.get('error')}")

            # Mark as completed
            await self.db.playbook_executions.update_one(
                {"_id": execution_id},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "variables": context["variables"]
                    }
                }
            )
            return {"execution_id": execution_id, "status": "completed"}

        except Exception as e:
            self.logger.error(f"Playbook resumption failed: {e}")
            await self.db.playbook_executions.update_one(
                {"_id": execution_id},
                {
                    "$set": {
                        "status": "failed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "error": str(e)
                    }
                }
            )
            return {"execution_id": execution_id, "status": "failed", "error": str(e)}
    
    async def _execute_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        execution_id: str,
        step_index: int
    ) -> Dict[str, Any]:
        """Execute a single playbook step"""
        step_type = step.get("type", "action")
        
        # Record step start
        step_record = {
            "index": step_index,
            "name": step.get("name", f"Step {step_index}"),
            "type": step_type,
            "status": StepStatus.RUNNING.value,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "output": None,
            "error": None
        }
        
        await self.db.playbook_executions.update_one(
            {"_id": execution_id},
            {"$push": {"steps": step_record}}
        )
        
        try:
            # Execute based on step type
            if step_type == "action":
                output = await self._execute_action(step, context)
            elif step_type == "condition":
                output = self._evaluate_condition(step.get("condition"), context)
            elif step_type == "loop":
                output = await self._execute_loop(step, context, execution_id)
            elif step_type == "parallel":
                output = await self._execute_parallel(step, context, execution_id)
            elif step_type == "notify":
                output = await self._execute_action(
                    {**step, "action": "send_notification"}, context
                )
            elif step_type == "approval":
                return await self._request_approval(step, context, execution_id, step_index)
            else:
                raise ValueError(f"Unknown step type: {step_type}")
            
            # Update step record
            await self.db.playbook_executions.update_one(
                {"_id": execution_id, f"steps.{step_index}.index": step_index},
                {
                    "$set": {
                        f"steps.{step_index}.status": StepStatus.COMPLETED.value,
                        f"steps.{step_index}.completed_at": datetime.now(timezone.utc).isoformat(),
                        f"steps.{step_index}.output": output
                    }
                }
            )
            
            # Store output in context if variable name specified
            if step.get("output_variable"):
                context["variables"][step["output_variable"]] = output
            
            return {
                "status": StepStatus.COMPLETED.value,
                "output": output
            }
        
        except Exception as e:
            self.logger.error(f"Step {step_index} failed: {e}")
            
            # Check retry configuration
            retry_count = step.get("retry_count", 0)
            retry_delay = step.get("retry_delay", 5)
            
            if retry_count > 0:
                for attempt in range(retry_count):
                    self.logger.info(f"Retrying step {step_index}, attempt {attempt + 1}/{retry_count}")
                    await asyncio.sleep(retry_delay)
                    
                    try:
                        if step_type == "action":
                            output = await self._execute_action(step, context)
                            
                            # Success after retry
                            await self.db.playbook_executions.update_one(
                                {"_id": execution_id, f"steps.{step_index}.index": step_index},
                                {
                                    "$set": {
                                        f"steps.{step_index}.status": StepStatus.COMPLETED.value,
                                        f"steps.{step_index}.completed_at": datetime.now(timezone.utc).isoformat(),
                                        f"steps.{step_index}.output": output,
                                        f"steps.{step_index}.retry_attempts": attempt + 1
                                    }
                                }
                            )
                            
                            return {
                                "status": StepStatus.COMPLETED.value,
                                "output": output
                            }
                    except Exception:
                        continue
            
            # Update step as failed
            await self.db.playbook_executions.update_one(
                {"_id": execution_id, f"steps.{step_index}.index": step_index},
                {
                    "$set": {
                        f"steps.{step_index}.status": StepStatus.FAILED.value,
                        f"steps.{step_index}.completed_at": datetime.now(timezone.utc).isoformat(),
                        f"steps.{step_index}.error": str(e)
                    }
                }
            )
            
            return {
                "status": StepStatus.FAILED.value,
                "error": str(e)
            }
    
    async def _execute_action(self, step: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Execute an action step"""
        action_name = step.get("action")
        params = step.get("params", {})
        
        # Resolve variables in params
        resolved_params = self._resolve_variables(params, context)
        
        # Get action handler
        handler = self.actions.get(action_name)
        if not handler:
            raise ValueError(f"Unknown action: {action_name}")
        
        # Execute action
        return await handler(resolved_params, context)
    
    def _evaluate_condition(self, condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate a conditional expression"""
        operator = condition.get("operator")
        left = self._resolve_value(condition.get("left"), context)
        right = self._resolve_value(condition.get("right"), context)
        
        if operator == "equals":
            return left == right
        elif operator == "not_equals":
            return left != right
        elif operator == "greater_than":
            return left > right
        elif operator == "less_than":
            return left < right
        elif operator == "contains":
            return right in left
        elif operator == "and":
            return left and right
        elif operator == "or":
            return left or right
        else:
            raise ValueError(f"Unknown operator: {operator}")
    
    async def _execute_loop(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        execution_id: str
    ) -> List[Any]:
        """Execute a loop"""
        loop_type = step.get("loop_type", "for")
        results = []
        
        if loop_type == "for":
            # For each loop
            items = self._resolve_value(step.get("items"), context)
            item_variable = step.get("item_variable", "item")
            loop_steps = step.get("steps", [])
            
            for item in items:
                # Set loop variable
                context["variables"][item_variable] = item
                
                # Execute loop steps
                for loop_step in loop_steps:
                    result = await self._execute_step(loop_step, context, execution_id, 0)
                    results.append(result)
        
        elif loop_type == "while":
            # While loop
            condition = step.get("condition")
            loop_steps = step.get("steps", [])
            max_iterations = step.get("max_iterations", 100)
            iteration = 0
            
            while self._evaluate_condition(condition, context) and iteration < max_iterations:
                for loop_step in loop_steps:
                    result = await self._execute_step(loop_step, context, execution_id, 0)
                    results.append(result)
                iteration += 1
        
        return results
    
    async def _execute_parallel(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        execution_id: str
    ) -> List[Any]:
        """Execute steps in parallel"""
        parallel_steps = step.get("steps", [])
        
        # Create tasks for parallel execution
        tasks = []
        for parallel_step in parallel_steps:
            task = self._execute_step(parallel_step, context, execution_id, 0)
            tasks.append(task)
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return results
    
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
            "escalate"    — emit a high-priority notification (default)
            "auto_approve"— resume the playbook automatically
            "skip"        — skip this step and continue
        """
        timeout_minutes = step.get("timeout_minutes", 60)
        timeout_action = step.get("timeout_action", "escalate")
        expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
        ).isoformat()

        approval_request = {
            "execution_id": execution_id,
            "step_index": step_index,
            "step_name": step.get("name"),
            "description": step.get("description"),
            "approvers": step.get("approvers", []),
            "timeout_minutes": timeout_minutes,
            "timeout_action": timeout_action,
            "expires_at": expires_at,
            "action_name": action_name,
            "agent_id": agent_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": None,
            "approved_at": None,
        }

        await self.db.playbook_approvals.insert_one(approval_request)
        self.logger.info(
            "Approval gate created for execution %s step %d (timeout=%dm action=%s)",
            execution_id, step_index, timeout_minutes, timeout_action,
        )
        return {
            "status": StepStatus.WAITING_APPROVAL.value,
            "message": "Waiting for approval",
        }

    # ------------------------------------------------------------------
    # Safety helpers (Phase 1-2, 2-3, 2-4, 3-3)
    # ------------------------------------------------------------------

    async def _check_duplicate_task(
        self, agent_id: str, action: str, window_minutes: int = 10
    ) -> bool:
        """Return True if the same action was already queued for this agent recently."""
        since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
        existing = await self.db.response_tasks.find_one({
            "agent_id": agent_id,
            "action": action,
            "status": {"$in": ["queued", "executed"]},
            "created_at": {"$gte": since},
        })
        return existing is not None

    async def _get_asset_criticality(self, agent_id: str) -> Optional[str]:
        """Look up the criticality of the asset associated with an agent."""
        agent = await self.db.agents.find_one({"id": agent_id}, {"hostname": 1})
        if not agent:
            return None
        hostname = agent.get("hostname", "")
        asset = await self.db.assets.find_one(
            {"$or": [{"id": f"asset-{hostname}"}, {"hostname": hostname}]},
            {"criticality": 1},
        )
        return asset.get("criticality") if asset else None

    async def _estimate_blast_radius(self, agent_id: str) -> int:
        """
        Estimate how many dependent services/assets could be disrupted
        if this agent were isolated or taken offline.
        """
        hostname = ""
        agent = await self.db.agents.find_one({"id": agent_id}, {"hostname": 1})
        if agent:
            hostname = agent.get("hostname", "")
        count = await self.db.assets.count_documents({
            "dependencies": {"$elemMatch": {"$regex": _re.escape(hostname), "$options": "i"}}
        })
        return int(count)

    async def _gate_high_risk_action(
        self,
        action: str,
        agent_id: str,
        context: Dict[str, Any],
        execution_id: str,
        step_index: int,
        step: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Run the full safety + dedup + blast-radius + risk-based auto-approval
        pipeline before any high-risk response task is queued.

        Returns a WAITING_APPROVAL result dict if the action must be gated,
        or None if the action may proceed immediately.
        """
        auto_approved = context.get("auto_approved", False)
        confidence = context.get("confidence", 1.0)

        # 1. Temporal deduplication
        if await self._check_duplicate_task(agent_id, action):
            self.logger.info(
                "DEDUP: skipping duplicate '%s' task for agent %s (within 10 min window)",
                action, agent_id,
            )
            return {"status": StepStatus.SKIPPED.value, "output": "Duplicate task suppressed"}

        # 2. Blast radius
        blast_radius = await self._estimate_blast_radius(agent_id)

        # 3. Asset criticality
        asset_criticality = await self._get_asset_criticality(agent_id)

        # 4. Safety evaluation
        risk = evaluate_action(
            action,
            confidence=confidence,
            asset_criticality=asset_criticality,
            blast_radius=blast_radius,
            auto_approved=auto_approved,
        )
        log_safety_decision(action, risk, context)

        if not risk.allowed:
            raise ValueError(f"Safety block: {risk.reason}")

        if risk.requires_approval:
            return await self._request_approval(
                step, context, execution_id, step_index,
                action_name=action, agent_id=agent_id,
            )

        return None  # cleared — proceed
    
    def _resolve_variables(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve variables in parameters"""
        resolved = {}
        for key, value in params.items():
            resolved[key] = self._resolve_value(value, context)
        return resolved
    
    def _resolve_value(self, value: Any, context: Dict[str, Any]) -> Any:
        """Resolve a value (may contain variable references)"""
        if isinstance(value, str) and value.startswith("$"):
            # Variable reference
            var_path = value[1:].split(".")
            result = context["variables"]
            for part in var_path:
                result = result.get(part)
                if result is None:
                    return None
            return result
        elif isinstance(value, dict):
            return {k: self._resolve_value(v, context) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._resolve_value(item, context) for item in value]
        else:
            return value
    
    # Default action implementations
    async def _action_log(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Log a message"""
        message = params.get("message", "")
        level = params.get("level", "info")
        
        if level == "info":
            self.logger.info(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        
        return f"Logged: {message}"
    
    async def _action_http_request(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Make an HTTP request via httpx."""
        import httpx
        method  = params.get("method", "GET").upper()
        url     = params.get("url", "")
        headers = params.get("headers", {})
        body    = params.get("body") or params.get("json")
        timeout = float(params.get("timeout", 30))

        if not url:
            raise ValueError("http_request action requires 'url' parameter")

        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=body)
            elif method == "PUT":
                resp = await client.put(url, headers=headers, json=body)
            elif method == "PATCH":
                resp = await client.patch(url, headers=headers, json=body)
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text

        return {
            "status_code": resp.status_code,
            "ok": resp.is_success,
            "body": resp_body,
        }
    
    async def _action_send_notification(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Send a notification"""
        channel = params.get("channel", "email")
        message = params.get("message", "")
        recipients = params.get("recipients", [])
        
        # Store notification in database
        notification = {
            "channel": channel,
            "message": message,
            "recipients": recipients,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "execution_id": context.get("execution_id")
        }
        
        await self.db.playbook_notifications.insert_one(notification)
        
        return f"Notification sent via {channel}"
    
    async def _action_create_ticket(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Create a ticket via the configured SOAR integration (Jira / ServiceNow fallback to DB)."""
        title = params.get("title", "Security Incident")
        description = params.get("description", "")
        priority = params.get("priority", "Medium")
        system = params.get("system", "jira").lower()

        # Interpolate variables
        for k, v in (context.get("variables") or {}).items():
            description = description.replace(f"{{{{{k}}}}}", str(v))

        try:
            from soar_integrations import get_integration_manager
            mgr = get_integration_manager()
            connector = mgr.get_connector(system)
            if connector:
                result = await connector.execute("create_ticket", {
                    "title": title,
                    "description": description,
                    "priority": priority,
                    "project_key": params.get("project_key"),
                    "issue_type": params.get("issue_type", "Task"),
                })
                if result.get("status") == "success":
                    self.logger.info("Ticket created: %s", result.get("ticket_id"))
                    return f"Ticket created: {result.get('ticket_id')} — {result.get('ticket_url', '')}"
        except Exception as exc:
            self.logger.warning("SOAR ticket creation failed: %s — persisting to DB", exc)

        # Fallback: persist to DB for manual triage
        import uuid as _uuid
        ticket_id = f"LOCAL-{_uuid.uuid4().hex[:8].upper()}"
        await self.db.pending_tickets.insert_one({
            "ticket_id": ticket_id, "system": system, "title": title,
            "description": description, "priority": priority,
            "execution_id": context.get("execution_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "soar_unavailable",
        })
        return f"Ticket queued locally as {ticket_id} ({system} unavailable)"
    
    async def _action_block_ip(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Block an IP address by queuing a block_ip response task on the
        target agent.  params keys:
            ip          – IP address to block (required)
            agent_id    – target agent (falls back to trigger.agent_id)
            reason      – human-readable reason (optional)
        """
        ip = params.get("ip") or (context["variables"].get("trigger") or {}).get("source_ip")
        agent_id = (
            params.get("agent_id")
            or (context["variables"].get("trigger") or {}).get("agent_id")
        )
        if not ip or not agent_id:
            raise ValueError("block_ip requires 'ip' and 'agent_id'")

        # Temporal deduplication for block_ip (keyed on ip, not agent)
        since = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        dup = await self.db.response_tasks.find_one({
            "action": "block_ip",
            "params.ip": ip,
            "status": {"$in": ["queued", "executed"]},
            "created_at": {"$gte": since},
        })
        if dup:
            self.logger.info("DEDUP: block_ip for %s already queued, skipping", ip)
            return f"block_ip for {ip} already queued (deduplicated)"

        task = {
            "task_id": f"PB-BLK-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "agent_id": agent_id,
            "action": "block_ip",
            "params": {"ip": ip, "reason": params.get("reason", "playbook-auto")},
            "triggered_by_playbook": context.get("execution_id"),
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executed_at": None,
            "result": None,
        }
        await self.db.response_tasks.insert_one(task)
        self.logger.info("Playbook queued block_ip task for IP %s on agent %s", ip, agent_id)
        return f"block_ip task queued for {ip} on agent {agent_id}"

    async def _action_isolate_endpoint(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Isolate an endpoint. Runs safety gate (dedup + blast-radius + criticality)
        before queuing the response task; may return WAITING_APPROVAL.
        """
        agent_id = (
            params.get("agent_id")
            or params.get("endpoint_id")
            or (context["variables"].get("trigger") or {}).get("agent_id")
        )
        if not agent_id:
            raise ValueError("isolate_endpoint requires 'agent_id' or 'endpoint_id'")

        # Safety gate — may raise, return approval result, or return None (proceed)
        execution_id = context.get("execution_id", "")
        gate = await self._gate_high_risk_action(
            "isolate_host", agent_id, context, execution_id,
            step_index=context.get("_current_step_index", 0),
            step=params,
        )
        if gate is not None:
            return gate  # type: ignore[return-value]

        task = {
            "task_id": f"PB-ISO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "agent_id": agent_id,
            "action": "isolate_host",
            "params": {"reason": params.get("reason", "playbook-auto")},
            "triggered_by_playbook": execution_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executed_at": None,
            "result": None,
        }
        await self.db.response_tasks.insert_one(task)
        self.logger.info("Playbook queued isolate_host task for agent %s", agent_id)
        return f"isolate_host task queued for agent {agent_id}"

    async def _action_quarantine_file(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Quarantine a file by queuing a quarantine_file response task on the
        target agent.  params keys:
            file_path   – path of the file to quarantine (required)
            agent_id    – target agent (falls back to trigger.agent_id)
            reason      – human-readable reason (optional)
        """
        file_path = (
            params.get("file_path")
            or (context["variables"].get("trigger") or {}).get("process", {}).get("path")
        )
        agent_id = (
            params.get("agent_id")
            or (context["variables"].get("trigger") or {}).get("agent_id")
        )
        if not file_path or not agent_id:
            raise ValueError("quarantine_file requires 'file_path' and 'agent_id'")

        task = {
            "task_id": f"PB-QRN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "agent_id": agent_id,
            "action": "quarantine_file",
            "params": {"file_path": file_path, "reason": params.get("reason", "playbook-auto")},
            "triggered_by_playbook": context.get("execution_id"),
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executed_at": None,
            "result": None,
        }
        await self.db.response_tasks.insert_one(task)
        self.logger.info(
            "Playbook queued quarantine_file task for %s on agent %s", file_path, agent_id
        )
        return f"quarantine_file task queued for {file_path} on agent {agent_id}"
    
    async def _action_rollback_ransomware(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Queue a rollback_ransomware task (VSS restore). Runs safety gate first.
        """
        agent_id = (
            params.get("agent_id")
            or (context["variables"].get("trigger") or {}).get("agent_id")
        )
        if not agent_id:
            raise ValueError("rollback_ransomware requires 'agent_id'")

        execution_id = context.get("execution_id", "")
        gate = await self._gate_high_risk_action(
            "rollback_ransomware", agent_id, context, execution_id,
            step_index=context.get("_current_step_index", 0),
            step=params,
        )
        if gate is not None:
            return gate  # type: ignore[return-value]

        task = {
            "task_id": f"PB-RRB-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "agent_id": agent_id,
            "action": "rollback_ransomware",
            "params": {
                "volume": params.get("volume", "C:"),
                "reason": params.get("reason", "playbook-auto: ransomware rollback"),
            },
            "triggered_by_playbook": execution_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executed_at": None,
            "result": None,
        }
        await self.db.response_tasks.insert_one(task)
        self.logger.info("Playbook queued rollback_ransomware task for agent %s", agent_id)
        return f"rollback_ransomware task queued for agent {agent_id}"

    async def _action_send_email(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Send an email via SMTP (config from environment) or log to DB as fallback."""
        import os, smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        to_list: list = params.get("to") or []
        if isinstance(to_list, str):
            to_list = [t.strip() for t in to_list.split(",")]
        subject: str = params.get("subject", "Security Alert")
        body: str = params.get("body", "")

        # Interpolate context variables into body
        for k, v in (context.get("variables") or {}).items():
            body = body.replace(f"{{{{{k}}}}}", str(v))

        smtp_host = os.environ.get("SMTP_HOST", "")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")
        smtp_from = os.environ.get("SMTP_FROM", smtp_user)

        if smtp_host and smtp_user and to_list:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = smtp_from
                msg["To"] = ", ".join(to_list)
                msg.attach(MIMEText(body, "plain"))
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
                    srv.starttls()
                    if smtp_pass:
                        srv.login(smtp_user, smtp_pass)
                    srv.sendmail(smtp_from, to_list, msg.as_string())
                self.logger.info("Email sent to %s: %s", to_list, subject)
                return f"Email sent to {', '.join(to_list)}"
            except Exception as exc:
                self.logger.warning("SMTP send failed: %s — storing in DB for review", exc)

        # Fallback: persist to DB so it can be reviewed / retried
        await self.db.pending_notifications.insert_one({
            "channel": "email", "to": to_list, "subject": subject, "body": body,
            "execution_id": context.get("execution_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "smtp_unavailable",
        })
        return f"Email queued (SMTP not configured) for {', '.join(to_list)}"
    
    async def _action_wait(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Wait for specified duration"""
        seconds = params.get("seconds", 0)
        await asyncio.sleep(seconds)
        return f"Waited {seconds} seconds"
    
    async def _action_set_variable(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Set a variable in context"""
        name = params.get("name")
        value = params.get("value")
        context["variables"][name] = value
        return value


# Singleton
_playbook_engine: Optional[PlaybookExecutionEngine] = None

def get_playbook_engine(db: AsyncIOMotorDatabase) -> PlaybookExecutionEngine:
    """Get or create playbook engine singleton"""
    global _playbook_engine
    if _playbook_engine is None:
        _playbook_engine = PlaybookExecutionEngine(db)
    return _playbook_engine


async def process_approval_timeouts(db: AsyncIOMotorDatabase) -> None:
    """
    Background task: check for expired approval requests and act according
    to their timeout_action field.
    Should be called periodically (e.g. every 60 s) from app.py lifespan.

    timeout_action values:
        "escalate"     — mark as escalated, emit high-priority notification
        "auto_approve" — approve automatically and resume the playbook
        "skip"         — mark step as skipped and resume the playbook
    """
    logger = logging.getLogger("PlaybookEngine.Timeouts")
    now = datetime.now(timezone.utc).isoformat()

    expired = await db.playbook_approvals.find({
        "status": "pending",
        "expires_at": {"$lt": now},
    }).to_list(length=100)

    for req in expired:
        req_id = str(req.get("_id"))
        timeout_action = req.get("timeout_action", "escalate")
        execution_id = req.get("execution_id")

        if timeout_action == "auto_approve":
            await db.playbook_approvals.update_one(
                {"_id": req["_id"]},
                {"$set": {"status": "auto_approved", "approved_by": "system-timeout", "approved_at": now}},
            )
            logger.info("Approval %s auto-approved after timeout", req_id)
            # Resume playbook in background
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
                "channel": "soc",
                "priority": "high",
                "message": (
                    f"ESCALATION: Approval request for playbook execution {execution_id} "
                    f"(action: {req.get('action_name', 'unknown')}, "
                    f"agent: {req.get('agent_id', 'unknown')}) has expired without a decision."
                ),
                "execution_id": execution_id,
                "approval_request_id": req_id,
                "created_at": now,
            })
            logger.warning("Approval %s escalated after timeout (no human response)", req_id)
