"""
SOAR playbook templates: incident response (phishing, malware, ransomware, brute force).
"""

from typing import Dict, Any


def phishing_response() -> Dict[str, Any]:
    return {
        "name": "Phishing Email Response",
        "description": "Automated response to phishing email reports",
        "category": "phishing_response",
        "trigger": "security_event.type == 'phishing_reported'",
        "is_template": True,
        "tags": ["phishing", "email", "automated"],
        "steps": [
            {"type": "action", "name": "Extract Email Details", "action": "set_variable",
             "params": {"name": "email_id", "value": "$trigger.email_id"},
             "output_variable": "email_details"},
            {"type": "action", "name": "Quarantine Email",
             "action": "email_gateway.quarantine_email",
             "params": {"message_id": "$email_details.message_id"},
             "retry_count": 2, "retry_delay": 5},
            {"type": "action", "name": "Extract Indicators", "action": "set_variable",
             "params": {"name": "sender", "value": "$trigger.sender"}},
            {"type": "action", "name": "Block Sender",
             "action": "email_gateway.block_sender",
             "params": {"sender": "$sender"}},
            {"type": "action", "name": "Search for Similar Emails", "action": "log",
             "params": {"message": "Searching for similar emails from $sender", "level": "info"}},
            {"type": "action", "name": "Create Jira Ticket", "action": "jira.create_ticket",
             "params": {"title": "Phishing Email Detected: $sender",
                        "description": "Automated phishing response triggered for email from $sender",
                        "priority": "High", "issue_type": "Security Incident"},
             "output_variable": "ticket"},
            {"type": "action", "name": "Notify Security Team", "action": "slack.send_message",
             "params": {"channel": "#security-alerts",
                        "message": "Phishing email detected and quarantined. Sender: $sender. Ticket: $ticket.ticket_url"}},
            {"type": "action", "name": "Log Response", "action": "log",
             "params": {"message": "Phishing response completed for $sender", "level": "info"}},
        ],
    }


def malware_containment() -> Dict[str, Any]:
    return {
        "name": "Malware Containment",
        "description": "Isolate infected endpoints and contain malware spread",
        "category": "malware_containment",
        "trigger": "security_event.type == 'malware_detected'",
        "is_template": True,
        "tags": ["malware", "containment", "edr"],
        "steps": [
            {"type": "action", "name": "Extract Endpoint Details", "action": "set_variable",
             "params": {"name": "endpoint_id", "value": "$trigger.endpoint_id"}},
            {"type": "action", "name": "Isolate Endpoint", "action": "edr.isolate_endpoint",
             "params": {"endpoint_id": "$endpoint_id", "hostname": "$trigger.hostname"},
             "retry_count": 3, "retry_delay": 10},
            {"type": "action", "name": "Quarantine Malicious File",
             "action": "edr.quarantine_file",
             "params": {"file_hash": "$trigger.file_hash", "file_path": "$trigger.file_path"}},
            {"type": "action", "name": "Scan Endpoint", "action": "edr.scan_endpoint",
             "params": {"endpoint_id": "$endpoint_id"}},
            {"type": "approval", "name": "Approve Endpoint Release",
             "description": "Review scan results before releasing endpoint",
             "approvers": ["security-team@company.com"], "timeout_minutes": 120},
            {"type": "action", "name": "Release Endpoint", "action": "edr.release_endpoint",
             "params": {"endpoint_id": "$endpoint_id"}},
            {"type": "action", "name": "Create Incident Ticket", "action": "jira.create_ticket",
             "params": {"title": "Malware Containment: $trigger.hostname",
                        "description": "Malware detected and contained on endpoint $trigger.hostname",
                        "priority": "Critical", "issue_type": "Security Incident"}},
            {"type": "action", "name": "Notify Team", "action": "slack.send_message",
             "params": {"channel": "#security-incidents",
                        "message": "Malware contained on $trigger.hostname. Endpoint isolated and scanned."}},
        ],
    }


def ransomware_recovery() -> Dict[str, Any]:
    return {
        "name": "Ransomware Recovery",
        "description": "Respond to and recover from ransomware attacks",
        "category": "ransomware_recovery",
        "trigger": "security_event.type == 'ransomware_detected'",
        "is_template": True,
        "tags": ["ransomware", "recovery", "critical"],
        "steps": [
            {"type": "action", "name": "Isolate Infected Systems", "action": "edr.isolate_endpoint",
             "params": {"endpoint_id": "$trigger.endpoint_id", "hostname": "$trigger.hostname"}},
            {"type": "action", "name": "Disable Network Shares", "action": "log",
             "params": {"message": "Disabling network shares to prevent spread", "level": "warning"}},
            {"type": "action", "name": "Identify Ransomware Variant", "action": "log",
             "params": {"message": "Analyzing ransomware variant: $trigger.ransomware_type",
                        "level": "info"}},
            {"type": "action", "name": "Check Backup Availability", "action": "log",
             "params": {"message": "Verifying backup integrity and availability", "level": "info"}},
            {"type": "approval", "name": "Recovery Plan Approval",
             "description": "Ransomware detected. Approve recovery plan before proceeding.",
             "approvers": ["ciso@company.com", "it-director@company.com"],
             "timeout_minutes": 30},
            {"type": "action", "name": "Initiate Backup Restore", "action": "log",
             "params": {"message": "Initiating backup restore for affected systems", "level": "info"}},
            {"type": "action", "name": "Create Critical Incident", "action": "jira.create_ticket",
             "params": {"title": "CRITICAL: Ransomware Attack - $trigger.ransomware_type",
                        "description": "Ransomware attack detected on $trigger.hostname. Systems isolated. Recovery in progress.",
                        "priority": "Critical", "issue_type": "Security Incident"}},
            {"type": "action", "name": "Alert All Teams", "action": "slack.send_message",
             "params": {"channel": "#all-hands",
                        "message": "CRITICAL: Ransomware attack detected. Recovery procedures initiated."}},
        ],
    }


def brute_force_response() -> Dict[str, Any]:
    return {
        "name": "Brute Force Attack Response",
        "description": "Respond to brute force login attempts",
        "category": "brute_force_response",
        "trigger": "security_event.type == 'brute_force_detected'",
        "is_template": True,
        "tags": ["brute_force", "authentication", "firewall"],
        "steps": [
            {"type": "action", "name": "Block Source IP", "action": "firewall.block_ip",
             "params": {"ip": "$trigger.source_ip", "reason": "Brute force attack",
                        "duration_hours": 48}},
            {"type": "action", "name": "Lock Targeted Account", "action": "log",
             "params": {"message": "Locking account: $trigger.target_account", "level": "warning"}},
            {"type": "action", "name": "Notify Account Owner", "action": "send_email",
             "params": {"to": ["$trigger.target_account"],
                        "subject": "Security Alert: Brute Force Attack Detected",
                        "body": "Brute force attack detected on your account. Your account has been temporarily locked for security."}},
            {"type": "action", "name": "Create Security Alert", "action": "jira.create_ticket",
             "params": {"title": "Brute Force Attack: $trigger.target_account",
                        "description": "Brute force attack detected from $trigger.source_ip targeting $trigger.target_account",
                        "priority": "Medium", "issue_type": "Security Alert"}},
        ],
    }
