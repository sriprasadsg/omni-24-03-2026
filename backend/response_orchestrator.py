"""
Response Policy Orchestrator
Evaluates incoming EDR alerts against response policies stored in MongoDB
and automatically triggers the appropriate response action.
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from database import get_database

logger = logging.getLogger(__name__)


class ResponseOrchestrator:
    """
    Reads response_policies from MongoDB.
    Each policy looks like:
    {
      "policy_id": "auto-kill-mimikatz",
      "name": "Auto-Kill Mimikatz",
      "enabled": True,
      "conditions": [
        {"field": "type", "operator": "eq", "value": "KNOWN_MALICIOUS_PROCESS"},
        {"field": "severity", "operator": "in", "value": ["critical", "high"]}
      ],
      "actions": [
        {"action": "kill_process", "params": {"reason": "auto-policy"}},
        {"action": "quarantine_file", "params": {"reason": "auto-policy"}}
      ],
      "notify_on_trigger": True
    }
    """

    async def evaluate_alert(self, alert: Dict[str, Any], agent_id: str) -> List[Dict]:
        """
        Evaluate an alert against all enabled policies.
        Returns a list of response tasks dispatched.
        """
        db = get_database()
        policies = await db.response_policies.find({"enabled": True}, {"_id": 0}).to_list(length=100)
        dispatched = []

        for policy in policies:
            if self._matches(alert, policy.get("conditions", [])):
                logger.info(f"Policy '{policy['policy_id']}' matched alert {alert.get('alert_id')}")

                for action_def in policy.get("actions", []):
                    task = await self._dispatch(
                        action=action_def["action"],
                        params={**action_def.get("params", {}), "alert": alert, "agent_id": agent_id},
                        policy=policy,
                        alert=alert,
                    )
                    dispatched.append(task)

        return dispatched

    def _matches(self, alert: Dict, conditions: List[Dict]) -> bool:
        """Check if all conditions match the alert."""
        for cond in conditions:
            field = cond.get("field")
            op = cond.get("operator", "eq")
            value = cond.get("value")
            alert_val = alert.get(field) or (alert.get("process") or {}).get(field)

            if op == "eq" and alert_val != value:
                return False
            elif op == "in" and alert_val not in value:
                return False
            elif op == "contains" and (value not in str(alert_val)):
                return False
            elif op == "ne" and alert_val == value:
                return False

        return True

    async def _dispatch(self, action: str, params: Dict,
                        policy: Dict, alert: Dict) -> Dict[str, Any]:
        """Record and queue a response action for the target agent."""
        db = get_database()
        task = {
            "task_id": f"RSP-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            "agent_id": params.get("agent_id"),
            "action": action,
            "params": {k: v for k, v in params.items() if k not in ("alert", "agent_id")},
            "triggered_by_policy": policy.get("policy_id"),
            "triggered_by_alert": alert.get("alert_id"),
            "status": "queued",
            "created_at": datetime.utcnow().isoformat(),
            "executed_at": None,
            "result": None,
        }
        await db.response_tasks.insert_one(task)
        # Remove non-serializable _id
        task.pop("_id", None)
        return task

    async def get_pending_tasks(self, agent_id: str) -> List[Dict]:
        """
        Called by agent polling. Returns queued response tasks for this agent.
        The agent will execute them and call /response/task/{task_id}/result.
        """
        db = get_database()
        tasks = await db.response_tasks.find(
            {"agent_id": agent_id, "status": "queued"}, {"_id": 0}
        ).to_list(length=20)
        return tasks

    async def mark_executed(self, task_id: str, result: Dict) -> bool:
        db = get_database()
        res = await db.response_tasks.update_one(
            {"task_id": task_id},
            {"$set": {
                "status": "executed",
                "executed_at": datetime.utcnow().isoformat(),
                "result": result
            }}
        )
        return res.matched_count > 0


# Default built-in policies to seed on first startup
BUILTIN_POLICIES = [
    {
        "policy_id": "auto-kill-mimikatz",
        "name": "Auto-Kill Known Credential Dumpers",
        "description": "Automatically terminate processes matching known credential-dumping tools",
        "enabled": True,
        "conditions": [
            {"field": "type", "operator": "eq", "value": "KNOWN_MALICIOUS_PROCESS"},
            {"field": "severity", "operator": "eq", "value": "critical"},
        ],
        "actions": [
            {"action": "kill_process", "params": {"reason": "Auto-policy: credential dumper detected"}},
        ],
        "notify_on_trigger": True,
        "created_at": datetime.utcnow().isoformat(),
        "builtin": True,
    },
    {
        "policy_id": "alert-encoded-powershell",
        "name": "Alert on Encoded PowerShell",
        "description": "Create an alert when obfuscated PowerShell commands are detected",
        "enabled": True,
        "conditions": [
            {"field": "type", "operator": "eq", "value": "ENCODED_POWERSHELL"},
        ],
        "actions": [],   # Alert-only — no automated action by default
        "notify_on_trigger": True,
        "created_at": datetime.utcnow().isoformat(),
        "builtin": True,
    },
    {
        "policy_id": "quarantine-suspicious-temp",
        "name": "Quarantine Executables in TEMP",
        "description": "Quarantine processes running from TEMP or Downloads directories",
        "enabled": False,   # Disabled by default (aggressive)
        "conditions": [
            {"field": "type", "operator": "eq", "value": "EXECUTABLE_IN_TEMP"},
            {"field": "severity", "operator": "in", "value": ["medium", "high", "critical"]},
        ],
        "actions": [
            {"action": "quarantine_file", "params": {"reason": "Auto-policy: executable in suspicious path"}},
        ],
        "notify_on_trigger": True,
        "created_at": datetime.utcnow().isoformat(),
        "builtin": True,
    },
]


async def seed_builtin_policies():
    """Seed built-in response policies on first startup."""
    db = get_database()
    for policy in BUILTIN_POLICIES:
        existing = await db.response_policies.find_one({"policy_id": policy["policy_id"]})
        if not existing:
            await db.response_policies.insert_one(policy)
            logger.info(f"Seeded response policy: {policy['policy_id']}")
