"""
XDR Built-in Playbooks
Seeded once on startup. Each playbook has trigger_type='correlation' so
the CorrelationEngine fires them automatically when matching patterns are found.

trigger_conditions:
  severity    – list of severities that activate this playbook ([] = all)
  pattern_ids – list of MITRE pattern IDs that activate this playbook ([] = all)
"""
import logging
from datetime import datetime, timezone
from database import get_database

logger = logging.getLogger(__name__)

XDR_PLAYBOOKS = [
    {
        "id": "xdr-isolate-on-lateral-movement",
        "name": "XDR: Isolate Endpoint on Lateral Movement",
        "description": (
            "Automatically isolate the source endpoint when lateral movement "
            "(SMB/RDP/SSH sweep) is detected by the correlation engine."
        ),
        "trigger_type": "correlation",
        "trigger_conditions": {
            "severity": ["critical", "high"],
            "pattern_ids": ["lateral_movement"],
        },
        "enabled": True,
        "tenant_id": "platform",
        "steps": [
            {
                "name": "Log detection",
                "type": "action",
                "action": "log",
                "params": {
                    "message": "XDR lateral movement detected — isolating endpoint",
                    "level": "warning",
                },
            },
            {
                "name": "Isolate endpoint",
                "type": "action",
                "action": "isolate_endpoint",
                "params": {
                    # agent_id resolved at runtime from trigger_data.agent_id
                    "reason": "XDR auto-response: lateral movement detected",
                },
                "output_variable": "isolate_result",
            },
            {
                "name": "Notify SOC",
                "type": "action",
                "action": "send_notification",
                "params": {
                    "channel": "email",
                    "message": "Endpoint isolated due to detected lateral movement. Review XDR correlations.",
                    "recipients": ["soc@company.com"],
                },
            },
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "builtin": True,
    },
    {
        "id": "xdr-block-ip-on-exfiltration",
        "name": "XDR: Block IP on Data Exfiltration",
        "description": (
            "Block the source IP and create a notification when a data-exfiltration "
            "pattern is correlated across endpoints."
        ),
        "trigger_type": "correlation",
        "trigger_conditions": {
            "severity": ["critical", "high"],
            "pattern_ids": ["data_exfiltration"],
        },
        "enabled": True,
        "tenant_id": "platform",
        "steps": [
            {
                "name": "Log detection",
                "type": "action",
                "action": "log",
                "params": {
                    "message": "XDR data-exfiltration pattern detected — blocking source IP",
                    "level": "warning",
                },
            },
            {
                "name": "Block source IP",
                "type": "action",
                "action": "block_ip",
                "params": {
                    # ip resolved at runtime from trigger_data.entity_value (entity_based)
                    # or trigger_data.source_ip
                    "reason": "XDR auto-response: data exfiltration detected",
                },
                "output_variable": "block_result",
            },
            {
                "name": "Notify SOC",
                "type": "action",
                "action": "send_notification",
                "params": {
                    "channel": "email",
                    "message": "Source IP blocked due to detected data exfiltration. Review XDR correlations.",
                    "recipients": ["soc@company.com"],
                },
            },
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "builtin": True,
    },
    {
        "id": "xdr-notify-on-credential-access",
        "name": "XDR: Alert SOC on Credential Access Pattern",
        "description": (
            "Send an immediate SOC notification when a credential-access attack "
            "pattern (brute-force / password spray) is detected."
        ),
        "trigger_type": "correlation",
        "trigger_conditions": {
            "severity": ["critical", "high"],
            "pattern_ids": ["credential_access"],
        },
        "enabled": True,
        "tenant_id": "platform",
        "steps": [
            {
                "name": "Log detection",
                "type": "action",
                "action": "log",
                "params": {
                    "message": "XDR credential-access pattern detected",
                    "level": "warning",
                },
            },
            {
                "name": "Notify SOC",
                "type": "action",
                "action": "send_notification",
                "params": {
                    "channel": "email",
                    "message": (
                        "ALERT: Credential access attack pattern detected across multiple endpoints. "
                        "Immediate investigation required."
                    ),
                    "recipients": ["soc@company.com"],
                },
            },
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "builtin": True,
    },
    {
        "id": "xdr-isolate-on-privilege-escalation",
        "name": "XDR: Isolate Endpoint on Privilege Escalation",
        "description": (
            "Isolate the affected endpoint when privilege-escalation activity "
            "is correlated across sudo/admin/service-creation events."
        ),
        "trigger_type": "correlation",
        "trigger_conditions": {
            "severity": ["critical"],
            "pattern_ids": ["privilege_escalation"],
        },
        "enabled": True,
        "tenant_id": "platform",
        "steps": [
            {
                "name": "Log detection",
                "type": "action",
                "action": "log",
                "params": {
                    "message": "XDR privilege escalation detected — isolating endpoint",
                    "level": "warning",
                },
            },
            {
                "name": "Isolate endpoint",
                "type": "action",
                "action": "isolate_endpoint",
                "params": {
                    "reason": "XDR auto-response: privilege escalation detected",
                },
                "output_variable": "isolate_result",
            },
            {
                "name": "Notify SOC",
                "type": "action",
                "action": "send_notification",
                "params": {
                    "channel": "email",
                    "message": "Endpoint isolated due to privilege escalation. Review XDR correlations.",
                    "recipients": ["soc@company.com"],
                },
            },
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "builtin": True,
    },
    {
        "id": "xdr-ransomware-recovery",
        "name": "XDR: Ransomware Recovery",
        "description": (
            "Full ransomware response: isolate infected endpoint, trigger VSS rollback "
            "on the agent, notify SOC, and create a critical incident ticket."
        ),
        "trigger_type": "correlation",
        "trigger_conditions": {
            "severity": ["critical"],
            "pattern_ids": ["ransomware"],
        },
        "enabled": True,
        "tenant_id": "platform",
        "steps": [
            {
                "name": "Log ransomware detection",
                "type": "action",
                "action": "log",
                "params": {
                    "message": "XDR ransomware activity detected — initiating recovery",
                    "level": "critical",
                },
            },
            {
                "name": "Isolate infected endpoint",
                "type": "action",
                "action": "isolate_endpoint",
                "params": {
                    "reason": "XDR auto-response: ransomware activity detected",
                },
                "output_variable": "isolate_result",
            },
            {
                "name": "Trigger VSS rollback",
                "type": "action",
                "action": "rollback_ransomware",
                "params": {
                    "volume": "C:",
                    "reason": "XDR auto-response: ransomware rollback via VSS",
                },
                "output_variable": "rollback_result",
            },
            {
                "name": "Notify SOC — critical incident",
                "type": "action",
                "action": "send_notification",
                "params": {
                    "channel": "email",
                    "message": (
                        "CRITICAL: Ransomware activity detected and auto-response initiated. "
                        "Endpoint isolated. VSS rollback triggered. Immediate review required."
                    ),
                    "recipients": ["soc@company.com", "ciso@company.com"],
                },
            },
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "builtin": True,
    },
]


async def seed_xdr_playbooks() -> None:
    """Insert XDR built-in playbooks if they don't already exist."""
    db = get_database()
    for pb in XDR_PLAYBOOKS:
        existing = await db._db.playbooks.find_one({"id": pb["id"]})
        if not existing:
            await db._db.playbooks.insert_one(dict(pb))
            logger.info("Seeded XDR playbook: %s", pb["name"])
