"""
Response Policy Orchestrator
Evaluates incoming EDR alerts against response policies stored in MongoDB
and automatically triggers the appropriate response action.
"""
import logging
from datetime import datetime, timedelta, timezone
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

    async def evaluate_alert(
        self, alert: Dict[str, Any], agent_id: str, dry_run: bool = False
    ) -> List[Dict]:
        """
        Evaluate an alert against all enabled policies.
        Returns a list of response tasks dispatched (or simulated when dry_run=True).
        dry_run=True: policies are matched and tasks are built but NOT written to the DB.
        """
        db = get_database()
        # Use _db directly to bypass tenant isolation — response policies are global/platform-level
        policies = await db._db.response_policies.find({"enabled": True}, {"_id": 0}).to_list(length=100)
        dispatched = []

        for policy in policies:
            if self._matches(alert, policy.get("conditions", [])):
                logger.info(
                    "Policy '%s' matched alert %s%s",
                    policy["policy_id"], alert.get("alert_id"),
                    " [DRY RUN]" if dry_run else "",
                )

                for action_def in policy.get("actions", []):
                    if dry_run:
                        task = {
                            "task_id": f"DRY-RSP-{policy['policy_id']}",
                            "agent_id": agent_id,
                            "action": action_def["action"],
                            "params": action_def.get("params", {}),
                            "triggered_by_policy": policy.get("policy_id"),
                            "triggered_by_alert": alert.get("alert_id"),
                            "status": "simulated",
                            "dry_run": True,
                        }
                    else:
                        task = await self._dispatch(
                            action=action_def["action"],
                            params={**action_def.get("params", {}), "alert": alert, "agent_id": agent_id},
                            policy=policy,
                            alert=alert,
                        )
                    dispatched.append(task)

        return dispatched

    def _matches(self, alert: Dict, conditions: List[Dict]) -> bool:
        """Check if all conditions match the alert (case-insensitive string comparison)."""
        for cond in conditions:
            field = cond.get("field")
            op = cond.get("operator", "eq")
            value = cond.get("value")
            alert_val = alert.get(field) or (alert.get("process") or {}).get(field)

            # Normalise strings to lowercase for comparison
            def _norm(v):
                return v.lower() if isinstance(v, str) else v

            a = _norm(alert_val)
            if op == "eq":
                if a != _norm(value):
                    return False
            elif op == "in":
                if a not in [_norm(v) for v in value]:
                    return False
            elif op == "contains":
                if _norm(value) not in str(a):
                    return False
            elif op == "ne":
                if a == _norm(value):
                    return False

        return True

    async def _dispatch(self, action: str, params: Dict,
                        policy: Dict, alert: Dict) -> Dict[str, Any]:
        """Record and queue a response action for the target agent."""
        db = get_database()
        task = {
            "task_id": f"RSP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "agent_id": params.get("agent_id"),
            "action": action,
            "params": {k: v for k, v in params.items() if k not in ("alert", "agent_id")},
            "triggered_by_policy": policy.get("policy_id"),
            "triggered_by_alert": alert.get("alert_id"),
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executed_at": None,
            "result": None,
        }
        await db._db.response_tasks.insert_one(task)
        # Remove non-serializable _id
        task.pop("_id", None)
        return task

    async def mark_executed(self, task_id: str, result: Dict) -> bool:
        db = get_database()
        res = await db._db.response_tasks.update_one(
            {"task_id": task_id},
            {"$set": {
                "status": "executed",
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "result": result
            }}
        )
        return res.matched_count > 0

    async def record_feedback(
        self,
        task_id: str,
        success: bool,
        false_positive: bool,
        message: str,
        reported_by: str = "agent",
    ) -> bool:
        """
        Record execution feedback (success/failure/false_positive) for a task.
        Feedback is stored on the task doc and in a separate analytics collection
        so the correlation engine and decision engines can learn from outcomes.
        """
        db = get_database()
        feedback = {
            "success": success,
            "false_positive": false_positive,
            "message": message,
            "reported_by": reported_by,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        res = await db._db.response_tasks.update_one(
            {"task_id": task_id},
            {"$set": {"feedback": feedback}}
        )
        if res.matched_count == 0:
            return False

        # Retrieve task to link feedback to the triggering policy/pattern
        task = await db._db.response_tasks.find_one({"task_id": task_id}, {"_id": 0})
        if task:
            await db._db.task_feedback_log.insert_one({
                "task_id": task_id,
                "agent_id": task.get("agent_id"),
                "action": task.get("action"),
                "triggered_by_policy": task.get("triggered_by_policy"),
                "triggered_by_playbook": task.get("triggered_by_playbook"),
                "correlation_pattern": task.get("correlation_pattern"),
                **feedback,
            })
            if false_positive:
                logger.warning(
                    "FALSE_POSITIVE reported for task %s (action=%s, policy=%s)",
                    task_id, task.get("action"), task.get("triggered_by_policy"),
                )
                # Feed false positive back to correlation engine so it raises
                # the detection threshold for this pattern and reduces noise
                pattern_id = task.get("correlation_pattern")
                tenant_id = task.get("tenant_id") or task.get("tenantId")
                if pattern_id and tenant_id:
                    try:
                        from correlation_engine import CorrelationEngine
                        engine = CorrelationEngine(db._db)
                        await engine.record_false_positive(
                            tenant_id=tenant_id,
                            pattern_id=pattern_id,
                        )
                        logger.info(
                            "FP feedback forwarded to correlation engine: pattern=%s tenant=%s",
                            pattern_id, tenant_id,
                        )
                    except Exception as _ce:
                        logger.warning("Could not forward FP to correlation engine: %s", _ce)
        return True

    async def is_duplicate_task(
        self,
        agent_id: str,
        action: str,
        dedup_window_minutes: int = 10,
        tenant_id: str = "",
        alert_type: str = "",
    ) -> bool:
        """
        Return True if an identical action was already queued or executed within the
        deduplication window. Deduplicates at both the agent level (same agent+action)
        and the incident level (same tenant+alert_type+action) to prevent multiple
        agents from responding to the same incident.
        """
        db = get_database()
        since = (datetime.now(timezone.utc) - timedelta(minutes=dedup_window_minutes)).isoformat()

        # Per-agent dedup
        agent_dup = await db._db.response_tasks.find_one({
            "agent_id": agent_id,
            "action": action,
            "status": {"$in": ["queued", "executed"]},
            "created_at": {"$gte": since},
        })
        if agent_dup:
            return True

        # Cross-agent dedup: same incident type in the same tenant
        if tenant_id and alert_type:
            incident_dup = await db._db.response_tasks.find_one({
                "tenant_id": tenant_id,
                "alert_type": alert_type,
                "action": action,
                "status": {"$in": ["queued", "executed"]},
                "created_at": {"$gte": since},
            })
            if incident_dup:
                return True

        return False

    async def get_pending_tasks(self, agent_id: str) -> List[Dict]:
        """
        Called by agent polling. Returns queued response tasks for this agent.
        The agent will execute them and call /response/task/{task_id}/result.
        """
        db = get_database()
        tasks = await db._db.response_tasks.find(
            {"agent_id": agent_id, "status": "queued"}, {"_id": 0}
        ).to_list(length=20)
        return tasks


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
        "created_at": datetime.now(timezone.utc).isoformat(),
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
        "created_at": datetime.now(timezone.utc).isoformat(),
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
        "created_at": datetime.now(timezone.utc).isoformat(),
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
