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
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
import asyncio
import json
import logging
from enum import Enum


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
        step_index: int
    ) -> Dict[str, Any]:
        """Request approval for a step"""
        approval_request = {
            "execution_id": execution_id,
            "step_index": step_index,
            "step_name": step.get("name"),
            "description": step.get("description"),
            "approvers": step.get("approvers", []),
            "timeout_minutes": step.get("timeout_minutes", 60),
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": None,
            "approved_at": None
        }
        
        await self.db.playbook_approvals.insert_one(approval_request)
        
        return {
            "status": StepStatus.WAITING_APPROVAL.value,
            "message": "Waiting for approval"
        }
    
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
        """Make an HTTP request"""
        # Placeholder - would use aiohttp in production
        return {"status": "success", "message": "HTTP request placeholder"}
    
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
        """Create a ticket in external system"""
        # Placeholder for Jira/ServiceNow integration
        return f"Ticket created: {params.get('title')}"
    
    async def _action_block_ip(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Block an IP address"""
        ip = params.get("ip")
        # Placeholder for firewall integration
        return f"Blocked IP: {ip}"
    
    async def _action_isolate_endpoint(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Isolate an endpoint"""
        endpoint_id = params.get("endpoint_id")
        # Placeholder for EDR integration
        return f"Isolated endpoint: {endpoint_id}"
    
    async def _action_quarantine_file(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Quarantine a file"""
        file_path = params.get("file_path")
        # Placeholder for file quarantine
        return f"Quarantined file: {file_path}"
    
    async def _action_send_email(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Send an email"""
        to = params.get("to", [])
        subject = params.get("subject", "")
        body = params.get("body", "")
        
        # Use existing email service
        return f"Email sent to {', '.join(to)}"
    
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
