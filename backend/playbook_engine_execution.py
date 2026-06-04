"""
PlaybookExecutionMixin — step-level execution logic for PlaybookExecutionEngine.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from enhanced_playbook_enums import StepStatus


class PlaybookExecutionMixin:
    """Mixin providing _execute_step, _execute_action, _evaluate_condition, loop, and parallel."""

    async def _execute_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        execution_id: str,
        step_index: int,
    ) -> Dict[str, Any]:
        step_type = step.get("type", "action")
        step_record = {
            "index": step_index,
            "name": step.get("name", f"Step {step_index}"),
            "type": step_type,
            "status": StepStatus.RUNNING.value,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "output": None,
            "error": None,
        }
        await self.db.playbook_executions.update_one(
            {"_id": execution_id}, {"$push": {"steps": step_record}}
        )

        try:
            if step_type == "action":
                output = await self._execute_action(step, context)
            elif step_type == "condition":
                output = self._evaluate_condition(step.get("condition"), context)
            elif step_type == "loop":
                output = await self._execute_loop(step, context, execution_id)
            elif step_type == "parallel":
                output = await self._execute_parallel(step, context, execution_id)
            elif step_type == "notify":
                output = await self._execute_action({**step, "action": "send_notification"}, context)
            elif step_type == "approval":
                return await self._request_approval(step, context, execution_id, step_index)
            else:
                raise ValueError(f"Unknown step type: {step_type}")

            await self.db.playbook_executions.update_one(
                {"_id": execution_id, f"steps.{step_index}.index": step_index},
                {
                    "$set": {
                        f"steps.{step_index}.status": StepStatus.COMPLETED.value,
                        f"steps.{step_index}.completed_at": datetime.now(timezone.utc).isoformat(),
                        f"steps.{step_index}.output": output,
                    }
                },
            )
            if step.get("output_variable"):
                context["variables"][step["output_variable"]] = output
            return {"status": StepStatus.COMPLETED.value, "output": output}

        except Exception as e:
            self.logger.error(f"Step {step_index} failed: {e}")
            retry_count = step.get("retry_count", 0)
            retry_delay = step.get("retry_delay", 5)

            if retry_count > 0:
                for attempt in range(retry_count):
                    self.logger.info(f"Retrying step {step_index}, attempt {attempt + 1}/{retry_count}")
                    await asyncio.sleep(retry_delay)
                    try:
                        if step_type == "action":
                            output = await self._execute_action(step, context)
                            await self.db.playbook_executions.update_one(
                                {"_id": execution_id, f"steps.{step_index}.index": step_index},
                                {
                                    "$set": {
                                        f"steps.{step_index}.status": StepStatus.COMPLETED.value,
                                        f"steps.{step_index}.completed_at": datetime.now(timezone.utc).isoformat(),
                                        f"steps.{step_index}.output": output,
                                        f"steps.{step_index}.retry_attempts": attempt + 1,
                                    }
                                },
                            )
                            return {"status": StepStatus.COMPLETED.value, "output": output}
                    except Exception:
                        continue

            await self.db.playbook_executions.update_one(
                {"_id": execution_id, f"steps.{step_index}.index": step_index},
                {
                    "$set": {
                        f"steps.{step_index}.status": StepStatus.FAILED.value,
                        f"steps.{step_index}.completed_at": datetime.now(timezone.utc).isoformat(),
                        f"steps.{step_index}.error": str(e),
                    }
                },
            )
            return {"status": StepStatus.FAILED.value, "error": str(e)}

    async def _execute_action(self, step: Dict[str, Any], context: Dict[str, Any]) -> Any:
        action_name = step.get("action")
        params = step.get("params", {})
        resolved_params = self._resolve_variables(params, context)
        handler = self.actions.get(action_name)
        if not handler:
            raise ValueError(f"Unknown action: {action_name}")
        return await handler(resolved_params, context)

    def _evaluate_condition(self, condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
        operator = condition.get("operator")
        left  = self._resolve_value(condition.get("left"), context)
        right = self._resolve_value(condition.get("right"), context)
        if operator == "equals":        return left == right
        if operator == "not_equals":    return left != right
        if operator == "greater_than":  return left > right
        if operator == "less_than":     return left < right
        if operator == "contains":      return right in left
        if operator == "and":           return left and right
        if operator == "or":            return left or right
        raise ValueError(f"Unknown operator: {operator}")

    async def _execute_loop(
        self, step: Dict[str, Any], context: Dict[str, Any], execution_id: str
    ) -> List[Any]:
        loop_type  = step.get("loop_type", "for")
        loop_steps = step.get("steps", [])
        results: List[Any] = []

        if loop_type == "for":
            items         = self._resolve_value(step.get("items"), context)
            item_variable = step.get("item_variable", "item")
            for item in items:
                context["variables"][item_variable] = item
                for loop_step in loop_steps:
                    results.append(await self._execute_step(loop_step, context, execution_id, 0))

        elif loop_type == "while":
            condition       = step.get("condition")
            max_iterations  = step.get("max_iterations", 100)
            iteration       = 0
            while self._evaluate_condition(condition, context) and iteration < max_iterations:
                for loop_step in loop_steps:
                    results.append(await self._execute_step(loop_step, context, execution_id, 0))
                iteration += 1

        return results

    async def _execute_parallel(
        self, step: Dict[str, Any], context: Dict[str, Any], execution_id: str
    ) -> List[Any]:
        tasks = [
            self._execute_step(ps, context, execution_id, 0)
            for ps in step.get("steps", [])
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)
