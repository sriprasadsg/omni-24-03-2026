"""
PlaybookSafetyMixin — dedup, blast-radius, criticality, and variable resolution
for PlaybookExecutionEngine.
"""
import re as _re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from backend_safety import evaluate_action, log_safety_decision
from enhanced_playbook_enums import StepStatus


class PlaybookSafetyMixin:
    """Mixin providing safety gates, deduplication, and variable resolution."""

    async def _check_duplicate_task(self, agent_id: str, action: str, window_minutes: int = 10) -> bool:
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
        """Estimate how many dependent assets could be disrupted if this agent is taken offline."""
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
        Run the full safety pipeline (dedup → blast-radius → criticality → risk eval).
        Returns a WAITING_APPROVAL dict if gated, or None to proceed.
        """
        auto_approved = context.get("auto_approved", False)
        confidence    = context.get("confidence", 1.0)

        if await self._check_duplicate_task(agent_id, action):
            self.logger.info(
                "DEDUP: skipping duplicate '%s' task for agent %s (within 10 min window)",
                action, agent_id,
            )
            return {"status": StepStatus.SKIPPED.value, "output": "Duplicate task suppressed"}

        blast_radius      = await self._estimate_blast_radius(agent_id)
        asset_criticality = await self._get_asset_criticality(agent_id)

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

        return None

    def _resolve_variables(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        return {k: self._resolve_value(v, context) for k, v in params.items()}

    def _resolve_value(self, value: Any, context: Dict[str, Any]) -> Any:
        if isinstance(value, str) and value.startswith("$"):
            result = context["variables"]
            for part in value[1:].split("."):
                result = result.get(part)
                if result is None:
                    return None
            return result
        if isinstance(value, dict):
            return {k: self._resolve_value(v, context) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(item, context) for item in value]
        return value
