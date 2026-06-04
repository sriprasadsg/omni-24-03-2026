"""
SOAR playbook templates: network/data security (DDoS, data breach, insider threat, credential compromise).
"""

from typing import Dict, Any


def ddos_mitigation() -> Dict[str, Any]:
    return {
        "name": "DDoS Mitigation",
        "description": "Automatically mitigate DDoS attacks by blocking source IPs",
        "category": "ddos_mitigation",
        "trigger": "security_event.type == 'ddos_detected'",
        "is_template": True,
        "tags": ["ddos", "network", "firewall"],
        "steps": [
            {"type": "action", "name": "Extract Attack IPs", "action": "set_variable",
             "params": {"name": "attack_ips", "value": "$trigger.source_ips"}},
            {"type": "loop", "name": "Block Attack IPs", "loop_type": "for",
             "items": "$attack_ips", "item_variable": "ip",
             "steps": [
                 {"type": "action", "name": "Block IP", "action": "firewall.block_ip",
                  "params": {"ip": "$ip", "reason": "DDoS attack source", "duration_hours": 24}},
             ]},
            {"type": "action", "name": "Enable Rate Limiting", "action": "log",
             "params": {"message": "Enabling rate limiting on affected services", "level": "info"}},
            {"type": "action", "name": "Notify NOC", "action": "slack.send_message",
             "params": {"channel": "#network-ops",
                        "message": "DDoS attack detected and mitigated. Blocked IPs count: ${attack_ips.length}"}},
            {"type": "action", "name": "Create Incident", "action": "jira.create_ticket",
             "params": {"title": "DDoS Attack Mitigated",
                        "description": "DDoS attack detected from ${attack_ips.length} source IPs. Automated mitigation applied.",
                        "priority": "High", "issue_type": "Incident"}},
        ],
    }


def data_breach_response() -> Dict[str, Any]:
    return {
        "name": "Data Breach Response",
        "description": "Respond to potential data breach incidents",
        "category": "data_breach_response",
        "trigger": "security_event.type == 'data_exfiltration'",
        "is_template": True,
        "tags": ["data_breach", "incident_response", "critical"],
        "steps": [
            {"type": "action", "name": "Isolate Affected Systems", "action": "edr.isolate_endpoint",
             "params": {"endpoint_id": "$trigger.endpoint_id", "hostname": "$trigger.hostname"}},
            {"type": "action", "name": "Revoke Compromised Credentials",
             "action": "cloud_provider.revoke_credentials",
             "params": {"credential_id": "$trigger.credential_id"}},
            {"type": "action", "name": "Create Snapshot for Forensics",
             "action": "cloud_provider.snapshot_instance",
             "params": {"instance_id": "$trigger.instance_id"}, "output_variable": "snapshot"},
            {"type": "approval", "name": "Executive Approval Required",
             "description": "Data breach detected. Executive approval required for next steps.",
             "approvers": ["ciso@company.com", "ceo@company.com"], "timeout_minutes": 60},
            {"type": "action", "name": "Notify Legal Team", "action": "send_email",
             "params": {"to": ["legal@company.com"], "subject": "URGENT: Data Breach Detected",
                        "body": "Data breach detected on $trigger.hostname. Forensic snapshot created: $snapshot.snapshot_id"}},
            {"type": "action", "name": "Create Critical Incident", "action": "jira.create_ticket",
             "params": {"title": "CRITICAL: Data Breach on $trigger.hostname",
                        "description": "Potential data breach detected. Systems isolated. Forensic snapshot: $snapshot.snapshot_id",
                        "priority": "Critical", "issue_type": "Security Incident"}},
            {"type": "action", "name": "Alert Executive Team", "action": "slack.send_message",
             "params": {"channel": "#executive-alerts",
                        "message": "CRITICAL: Data breach detected on $trigger.hostname. Immediate action required."}},
        ],
    }


def insider_threat_investigation() -> Dict[str, Any]:
    return {
        "name": "Insider Threat Investigation",
        "description": "Investigate suspicious insider activity",
        "category": "insider_threat",
        "trigger": "security_event.type == 'insider_threat'",
        "is_template": True,
        "tags": ["insider_threat", "investigation", "ueba"],
        "steps": [
            {"type": "action", "name": "Collect User Activity Logs", "action": "log",
             "params": {"message": "Collecting activity logs for user: $trigger.user_id",
                        "level": "info"}},
            {"type": "action", "name": "Suspend User Account", "action": "log",
             "params": {"message": "Suspending account for user: $trigger.user_id",
                        "level": "warning"}},
            {"type": "action", "name": "Revoke Access Tokens",
             "action": "cloud_provider.revoke_credentials",
             "params": {"credential_id": "$trigger.user_id"}},
            {"type": "approval", "name": "HR Approval for Investigation",
             "description": "Insider threat detected for user $trigger.user_id. HR approval required.",
             "approvers": ["hr@company.com", "security@company.com"], "timeout_minutes": 240},
            {"type": "action", "name": "Create Investigation Ticket", "action": "jira.create_ticket",
             "params": {"title": "Insider Threat Investigation: $trigger.user_id",
                        "description": "Suspicious activity detected for user $trigger.user_id. Account suspended pending investigation.",
                        "priority": "High", "issue_type": "Investigation"}},
            {"type": "action", "name": "Notify Security Team", "action": "slack.send_message",
             "params": {"channel": "#security-investigations",
                        "message": "Insider threat investigation initiated for user $trigger.user_id"}},
        ],
    }


def credential_compromise() -> Dict[str, Any]:
    return {
        "name": "Credential Compromise Response",
        "description": "Respond to compromised credentials",
        "category": "credential_compromise",
        "trigger": "security_event.type == 'credential_compromise'",
        "is_template": True,
        "tags": ["credentials", "compromise", "iam"],
        "steps": [
            {"type": "action", "name": "Revoke Compromised Credentials",
             "action": "cloud_provider.revoke_credentials",
             "params": {"credential_id": "$trigger.credential_id"}},
            {"type": "action", "name": "Force Password Reset", "action": "log",
             "params": {"message": "Forcing password reset for user: $trigger.user_id",
                        "level": "warning"}},
            {"type": "action", "name": "Terminate Active Sessions", "action": "log",
             "params": {"message": "Terminating all active sessions for user: $trigger.user_id",
                        "level": "warning"}},
            {"type": "action", "name": "Enable MFA", "action": "log",
             "params": {"message": "Enforcing MFA for user: $trigger.user_id", "level": "info"}},
            {"type": "action", "name": "Notify User", "action": "send_email",
             "params": {"to": ["$trigger.user_id"],
                        "subject": "URGENT: Your Credentials Have Been Compromised",
                        "body": "Your credentials have been compromised. Please reset your password immediately and enable MFA."}},
            {"type": "action", "name": "Create Incident", "action": "jira.create_ticket",
             "params": {"title": "Credential Compromise: $trigger.user_id",
                        "description": "Credentials compromised for user $trigger.user_id. Credentials revoked and password reset enforced.",
                        "priority": "High", "issue_type": "Security Incident"}},
            {"type": "action", "name": "Alert Security Team", "action": "slack.send_message",
             "params": {"channel": "#security-alerts",
                        "message": "Credential compromise detected for user $trigger.user_id. Automated response completed."}},
        ],
    }
