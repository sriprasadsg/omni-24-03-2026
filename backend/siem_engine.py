"""
Native SIEM Engine - Correlation and Rule Execution
Processes incoming normalized logs and evaluates them against active correlation rules.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import uuid

class SiemEngine:
    def __init__(self, db):
        self.db = db

    async def ingest_logs(self, logs: List[Dict[str, Any]], tenant_id: str, agent_id: str):
        """
        Normalize and ingest raw logs. Evaluate them against correlation rules.
        """
        parsed_events = []
        for log in logs:
            event = self._normalize_log(log, tenant_id, agent_id)
            if event:
                parsed_events.append(event)
        
        if not parsed_events:
            return

        # Store in raw collection
        await self.db.siem_events.insert_many(parsed_events)
        
        # Evaluate rules
        await self._evaluate_rules(parsed_events, tenant_id)

    def _normalize_log(self, raw_log: Dict[str, Any], tenant_id: str, agent_id: str) -> Optional[Dict[str, Any]]:
        """Normalize raw Windows/Linux logs into a standard schema."""
        source = raw_log.get("source")
        msg = raw_log.get("raw_message", "").lower()
        
        event = {
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "timestamp": raw_log.get("collected_at", datetime.now(timezone.utc).isoformat()),
            "source": source,
            "raw": raw_log.get("raw_message"),
            "category": "unknown",
            "action": "unknown",
            "user": "unknown",
        }

        # Simple heuristic parser
        if source == "windows_event_log":
            event_id = raw_log.get("event_id")
            if event_id == 4624:
                event["category"] = "authentication"
                event["action"] = "login_success"
            elif event_id == 4625:
                event["category"] = "authentication"
                event["action"] = "login_failed"
            elif event_id == 4688:
                event["category"] = "process"
                event["action"] = "process_creation"
        elif source == "syslog":
            if "failed password" in msg:
                event["category"] = "authentication"
                event["action"] = "login_failed"
            elif "accepted password" in msg or "session opened" in msg:
                event["category"] = "authentication"
                event["action"] = "login_success"
            elif "sudo" in msg and "command" in msg:
                event["category"] = "privilege_escalation"
                event["action"] = "sudo_executed"

        return event

    async def _evaluate_rules(self, events: List[Dict[str, Any]], tenant_id: str):
        """Evaluate events against active correlation rules."""
        rules = await self.db.siem_rules.find({"tenantId": tenant_id, "enabled": True}).to_list(length=None)
        
        for rule in rules:
            for event in events:
                if self._match_rule(event, rule):
                    await self._trigger_alert(event, rule, tenant_id)

    def _match_rule(self, event: Dict[str, Any], rule: Dict[str, Any]) -> bool:
        """Evaluate a single rule against a single event."""
        # Simple AND-based matching defined in rule conditions
        conditions = rule.get("conditions", {})
        for key, expected_value in conditions.items():
            if event.get(key) != expected_value:
                return False
        return True

    async def _trigger_alert(self, event: Dict[str, Any], rule: Dict[str, Any], tenant_id: str):
        """Trigger alert natively and create a security case."""
        case_id = f"CASE-{datetime.now(timezone.utc).strftime('%Y%j%H%M')}-{uuid.uuid4().hex[:4].upper()}"
        
        case_doc = {
            "id": case_id,
            "title": f"SIEM Alert: {rule.get('name')}",
            "description": f"Triggered by event {event['id']}. RAW: {event['raw']}",
            "severity": rule.get("severity", "Medium"),
            "status": "Open",
            "tenantId": tenant_id,
            "assignedTo": "Unassigned",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "source": "SIEM Engine",
            "relatedAssets": [event["agent_id"]],
            "relatedEvents": [event["id"]]
        }
        
        await self.db.security_cases.insert_one(case_doc)
        
        # Dispatch notification 
        try:
            from email_service import email_service
            smtp_config = await self.db.smtp_config.find_one({"tenant_id": tenant_id})
            if smtp_config:
                alert_data = {
                    "title": case_doc["title"],
                    "severity": case_doc["severity"],
                    "timestamp": case_doc["createdAt"],
                    "asset": event["agent_id"],
                    "description": case_doc["description"],
                    "recommendations": rule.get("remediation", "Investigate immediately.")
                }
                admin_users = await self.db.users.find({"tenantId": tenant_id, "role": "Tenant Admin"}).to_list(length=10)
                recipients = [u["email"] for u in admin_users if "email" in u]
                if recipients:
                    email_service.send_alert_notification(smtp_config, recipients, alert_data)
        except Exception as e:
            print(f"[SIEMEngine] Failed to dispatch alert notification: {e}")

def get_siem_engine(db):
    return SiemEngine(db)
