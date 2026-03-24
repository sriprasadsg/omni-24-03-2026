"""
SOAR Playbook Template Library

Pre-built playbook templates for common security scenarios:
- Phishing response
- Malware containment
- DDoS mitigation
- Data breach response
- Insider threat investigation
- Ransomware recovery
"""

from typing import List, Dict, Any


class PlaybookTemplateLibrary:
    """Library of pre-built playbook templates"""
    
    @staticmethod
    def get_all_templates() -> List[Dict[str, Any]]:
        """Get all available templates"""
        return [
            PlaybookTemplateLibrary.phishing_response(),
            PlaybookTemplateLibrary.malware_containment(),
            PlaybookTemplateLibrary.ddos_mitigation(),
            PlaybookTemplateLibrary.data_breach_response(),
            PlaybookTemplateLibrary.insider_threat_investigation(),
            PlaybookTemplateLibrary.ransomware_recovery(),
            PlaybookTemplateLibrary.brute_force_response(),
            PlaybookTemplateLibrary.credential_compromise()
        ]
    
    @staticmethod
    def phishing_response() -> Dict[str, Any]:
        """Automated phishing email response playbook"""
        return {
            "name": "Phishing Email Response",
            "description": "Automated response to phishing email reports",
            "category": "phishing_response",
            "trigger": "security_event.type == 'phishing_reported'",
            "is_template": True,
            "tags": ["phishing", "email", "automated"],
            "steps": [
                {
                    "type": "action",
                    "name": "Extract Email Details",
                    "action": "set_variable",
                    "params": {
                        "name": "email_id",
                        "value": "$trigger.email_id"
                    },
                    "output_variable": "email_details"
                },
                {
                    "type": "action",
                    "name": "Quarantine Email",
                    "action": "email_gateway.quarantine_email",
                    "params": {
                        "message_id": "$email_details.message_id"
                    },
                    "retry_count": 2,
                    "retry_delay": 5
                },
                {
                    "type": "action",
                    "name": "Extract Indicators",
                    "action": "set_variable",
                    "params": {
                        "name": "sender",
                        "value": "$trigger.sender"
                    }
                },
                {
                    "type": "action",
                    "name": "Block Sender",
                    "action": "email_gateway.block_sender",
                    "params": {
                        "sender": "$sender"
                    }
                },
                {
                    "type": "action",
                    "name": "Search for Similar Emails",
                    "action": "log",
                    "params": {
                        "message": "Searching for similar emails from $sender",
                        "level": "info"
                    }
                },
                {
                    "type": "action",
                    "name": "Create Jira Ticket",
                    "action": "jira.create_ticket",
                    "params": {
                        "title": "Phishing Email Detected: $sender",
                        "description": "Automated phishing response triggered for email from $sender",
                        "priority": "High",
                        "issue_type": "Security Incident"
                    },
                    "output_variable": "ticket"
                },
                {
                    "type": "action",
                    "name": "Notify Security Team",
                    "action": "slack.send_message",
                    "params": {
                        "channel": "#security-alerts",
                        "message": "🚨 Phishing email detected and quarantined. Sender: $sender. Ticket: $ticket.ticket_url"
                    }
                },
                {
                    "type": "action",
                    "name": "Log Response",
                    "action": "log",
                    "params": {
                        "message": "Phishing response completed for $sender",
                        "level": "info"
                    }
                }
            ]
        }
    
    @staticmethod
    def malware_containment() -> Dict[str, Any]:
        """Automated malware containment playbook"""
        return {
            "name": "Malware Containment",
            "description": "Isolate infected endpoints and contain malware spread",
            "category": "malware_containment",
            "trigger": "security_event.type == 'malware_detected'",
            "is_template": True,
            "tags": ["malware", "containment", "edr"],
            "steps": [
                {
                    "type": "action",
                    "name": "Extract Endpoint Details",
                    "action": "set_variable",
                    "params": {
                        "name": "endpoint_id",
                        "value": "$trigger.endpoint_id"
                    }
                },
                {
                    "type": "action",
                    "name": "Isolate Endpoint",
                    "action": "edr.isolate_endpoint",
                    "params": {
                        "endpoint_id": "$endpoint_id",
                        "hostname": "$trigger.hostname"
                    },
                    "retry_count": 3,
                    "retry_delay": 10
                },
                {
                    "type": "action",
                    "name": "Quarantine Malicious File",
                    "action": "edr.quarantine_file",
                    "params": {
                        "file_hash": "$trigger.file_hash",
                        "file_path": "$trigger.file_path"
                    }
                },
                {
                    "type": "action",
                    "name": "Scan Endpoint",
                    "action": "edr.scan_endpoint",
                    "params": {
                        "endpoint_id": "$endpoint_id"
                    }
                },
                {
                    "type": "approval",
                    "name": "Approve Endpoint Release",
                    "description": "Review scan results before releasing endpoint",
                    "approvers": ["security-team@company.com"],
                    "timeout_minutes": 120
                },
                {
                    "type": "action",
                    "name": "Release Endpoint",
                    "action": "edr.release_endpoint",
                    "params": {
                        "endpoint_id": "$endpoint_id"
                    }
                },
                {
                    "type": "action",
                    "name": "Create Incident Ticket",
                    "action": "jira.create_ticket",
                    "params": {
                        "title": "Malware Containment: $trigger.hostname",
                        "description": "Malware detected and contained on endpoint $trigger.hostname",
                        "priority": "Critical",
                        "issue_type": "Security Incident"
                    }
                },
                {
                    "type": "action",
                    "name": "Notify Team",
                    "action": "slack.send_message",
                    "params": {
                        "channel": "#security-incidents",
                        "message": "🦠 Malware contained on $trigger.hostname. Endpoint isolated and scanned."
                    }
                }
            ]
        }
    
    @staticmethod
    def ddos_mitigation() -> Dict[str, Any]:
        """Automated DDoS attack mitigation playbook"""
        return {
            "name": "DDoS Mitigation",
            "description": "Automatically mitigate DDoS attacks by blocking source IPs",
            "category": "ddos_mitigation",
            "trigger": "security_event.type == 'ddos_detected'",
            "is_template": True,
            "tags": ["ddos", "network", "firewall"],
            "steps": [
                {
                    "type": "action",
                    "name": "Extract Attack IPs",
                    "action": "set_variable",
                    "params": {
                        "name": "attack_ips",
                        "value": "$trigger.source_ips"
                    }
                },
                {
                    "type": "loop",
                    "name": "Block Attack IPs",
                    "loop_type": "for",
                    "items": "$attack_ips",
                    "item_variable": "ip",
                    "steps": [
                        {
                            "type": "action",
                            "name": "Block IP",
                            "action": "firewall.block_ip",
                            "params": {
                                "ip": "$ip",
                                "reason": "DDoS attack source",
                                "duration_hours": 24
                            }
                        }
                    ]
                },
                {
                    "type": "action",
                    "name": "Enable Rate Limiting",
                    "action": "log",
                    "params": {
                        "message": "Enabling rate limiting on affected services",
                        "level": "info"
                    }
                },
                {
                    "type": "action",
                    "name": "Notify NOC",
                    "action": "slack.send_message",
                    "params": {
                        "channel": "#network-ops",
                        "message": "🌊 DDoS attack detected and mitigated. Blocked IPs count: ${attack_ips.length}"
                    }
                },
                {
                    "type": "action",
                    "name": "Create Incident",
                    "action": "jira.create_ticket",
                    "params": {
                        "title": "DDoS Attack Mitigated",
                        "description": "DDoS attack detected from ${attack_ips.length} source IPs. Automated mitigation applied.",
                        "priority": "High",
                        "issue_type": "Incident"
                    }
                }
            ]
        }
    
    @staticmethod
    def data_breach_response() -> Dict[str, Any]:
        """Data breach response playbook"""
        return {
            "name": "Data Breach Response",
            "description": "Respond to potential data breach incidents",
            "category": "data_breach_response",
            "trigger": "security_event.type == 'data_exfiltration'",
            "is_template": True,
            "tags": ["data_breach", "incident_response", "critical"],
            "steps": [
                {
                    "type": "action",
                    "name": "Isolate Affected Systems",
                    "action": "edr.isolate_endpoint",
                    "params": {
                        "endpoint_id": "$trigger.endpoint_id",
                        "hostname": "$trigger.hostname"
                    }
                },
                {
                    "type": "action",
                    "name": "Revoke Compromised Credentials",
                    "action": "cloud_provider.revoke_credentials",
                    "params": {
                        "credential_id": "$trigger.credential_id"
                    }
                },
                {
                    "type": "action",
                    "name": "Create Snapshot for Forensics",
                    "action": "cloud_provider.snapshot_instance",
                    "params": {
                        "instance_id": "$trigger.instance_id"
                    },
                    "output_variable": "snapshot"
                },
                {
                    "type": "approval",
                    "name": "Executive Approval Required",
                    "description": "Data breach detected. Executive approval required for next steps.",
                    "approvers": ["ciso@company.com", "ceo@company.com"],
                    "timeout_minutes": 60
                },
                {
                    "type": "action",
                    "name": "Notify Legal Team",
                    "action": "send_email",
                    "params": {
                        "to": ["legal@company.com"],
                        "subject": "URGENT: Data Breach Detected",
                        "body": "Data breach detected on $trigger.hostname. Forensic snapshot created: $snapshot.snapshot_id"
                    }
                },
                {
                    "type": "action",
                    "name": "Create Critical Incident",
                    "action": "jira.create_ticket",
                    "params": {
                        "title": "CRITICAL: Data Breach on $trigger.hostname",
                        "description": "Potential data breach detected. Systems isolated. Forensic snapshot: $snapshot.snapshot_id",
                        "priority": "Critical",
                        "issue_type": "Security Incident"
                    }
                },
                {
                    "type": "action",
                    "name": "Alert Executive Team",
                    "action": "slack.send_message",
                    "params": {
                        "channel": "#executive-alerts",
                        "message": "🚨 CRITICAL: Data breach detected on $trigger.hostname. Immediate action required."
                    }
                }
            ]
        }
    
    @staticmethod
    def insider_threat_investigation() -> Dict[str, Any]:
        """Insider threat investigation playbook"""
        return {
            "name": "Insider Threat Investigation",
            "description": "Investigate suspicious insider activity",
            "category": "insider_threat",
            "trigger": "security_event.type == 'insider_threat'",
            "is_template": True,
            "tags": ["insider_threat", "investigation", "ueba"],
            "steps": [
                {
                    "type": "action",
                    "name": "Collect User Activity Logs",
                    "action": "log",
                    "params": {
                        "message": "Collecting activity logs for user: $trigger.user_id",
                        "level": "info"
                    }
                },
                {
                    "type": "action",
                    "name": "Suspend User Account",
                    "action": "log",
                    "params": {
                        "message": "Suspending account for user: $trigger.user_id",
                        "level": "warning"
                    }
                },
                {
                    "type": "action",
                    "name": "Revoke Access Tokens",
                    "action": "cloud_provider.revoke_credentials",
                    "params": {
                        "credential_id": "$trigger.user_id"
                    }
                },
                {
                    "type": "approval",
                    "name": "HR Approval for Investigation",
                    "description": "Insider threat detected for user $trigger.user_id. HR approval required.",
                    "approvers": ["hr@company.com", "security@company.com"],
                    "timeout_minutes": 240
                },
                {
                    "type": "action",
                    "name": "Create Investigation Ticket",
                    "action": "jira.create_ticket",
                    "params": {
                        "title": "Insider Threat Investigation: $trigger.user_id",
                        "description": "Suspicious activity detected for user $trigger.user_id. Account suspended pending investigation.",
                        "priority": "High",
                        "issue_type": "Investigation"
                    }
                },
                {
                    "type": "action",
                    "name": "Notify Security Team",
                    "action": "slack.send_message",
                    "params": {
                        "channel": "#security-investigations",
                        "message": "🔍 Insider threat investigation initiated for user $trigger.user_id"
                    }
                }
            ]
        }
    
    @staticmethod
    def ransomware_recovery() -> Dict[str, Any]:
        """Ransomware attack recovery playbook"""
        return {
            "name": "Ransomware Recovery",
            "description": "Respond to and recover from ransomware attacks",
            "category": "ransomware_recovery",
            "trigger": "security_event.type == 'ransomware_detected'",
            "is_template": True,
            "tags": ["ransomware", "recovery", "critical"],
            "steps": [
                {
                    "type": "action",
                    "name": "Isolate Infected Systems",
                    "action": "edr.isolate_endpoint",
                    "params": {
                        "endpoint_id": "$trigger.endpoint_id",
                        "hostname": "$trigger.hostname"
                    }
                },
                {
                    "type": "action",
                    "name": "Disable Network Shares",
                    "action": "log",
                    "params": {
                        "message": "Disabling network shares to prevent spread",
                        "level": "warning"
                    }
                },
                {
                    "type": "action",
                    "name": "Identify Ransomware Variant",
                    "action": "log",
                    "params": {
                        "message": "Analyzing ransomware variant: $trigger.ransomware_type",
                        "level": "info"
                    }
                },
                {
                    "type": "action",
                    "name": "Check Backup Availability",
                    "action": "log",
                    "params": {
                        "message": "Verifying backup integrity and availability",
                        "level": "info"
                    }
                },
                {
                    "type": "approval",
                    "name": "Recovery Plan Approval",
                    "description": "Ransomware detected. Approve recovery plan before proceeding.",
                    "approvers": ["ciso@company.com", "it-director@company.com"],
                    "timeout_minutes": 30
                },
                {
                    "type": "action",
                    "name": "Initiate Backup Restore",
                    "action": "log",
                    "params": {
                        "message": "Initiating backup restore for affected systems",
                        "level": "info"
                    }
                },
                {
                    "type": "action",
                    "name": "Create Critical Incident",
                    "action": "jira.create_ticket",
                    "params": {
                        "title": "CRITICAL: Ransomware Attack - $trigger.ransomware_type",
                        "description": "Ransomware attack detected on $trigger.hostname. Systems isolated. Recovery in progress.",
                        "priority": "Critical",
                        "issue_type": "Security Incident"
                    }
                },
                {
                    "type": "action",
                    "name": "Alert All Teams",
                    "action": "slack.send_message",
                    "params": {
                        "channel": "#all-hands",
                        "message": "🚨 CRITICAL: Ransomware attack detected. Recovery procedures initiated. Do not open suspicious emails or files."
                    }
                }
            ]
        }
    
    @staticmethod
    def brute_force_response() -> Dict[str, Any]:
        """Brute force attack response playbook"""
        return {
            "name": "Brute Force Attack Response",
            "description": "Respond to brute force login attempts",
            "category": "brute_force_response",
            "trigger": "security_event.type == 'brute_force_detected'",
            "is_template": True,
            "tags": ["brute_force", "authentication", "firewall"],
            "steps": [
                {
                    "type": "action",
                    "name": "Block Source IP",
                    "action": "firewall.block_ip",
                    "params": {
                        "ip": "$trigger.source_ip",
                        "reason": "Brute force attack",
                        "duration_hours": 48
                    }
                },
                {
                    "type": "action",
                    "name": "Lock Targeted Account",
                    "action": "log",
                    "params": {
                        "message": "Locking account: $trigger.target_account",
                        "level": "warning"
                    }
                },
                {
                    "type": "action",
                    "name": "Notify Account Owner",
                    "action": "send_email",
                    "params": {
                        "to": ["$trigger.target_account"],
                        "subject": "Security Alert: Brute Force Attack Detected",
                        "body": "Brute force attack detected on your account. Your account has been temporarily locked for security."
                    }
                },
                {
                    "type": "action",
                    "name": "Create Security Alert",
                    "action": "jira.create_ticket",
                    "params": {
                        "title": "Brute Force Attack: $trigger.target_account",
                        "description": "Brute force attack detected from $trigger.source_ip targeting $trigger.target_account",
                        "priority": "Medium",
                        "issue_type": "Security Alert"
                    }
                }
            ]
        }
    
    @staticmethod
    def credential_compromise() -> Dict[str, Any]:
        """Credential compromise response playbook"""
        return {
            "name": "Credential Compromise Response",
            "description": "Respond to compromised credentials",
            "category": "credential_compromise",
            "trigger": "security_event.type == 'credential_compromise'",
            "is_template": True,
            "tags": ["credentials", "compromise", "iam"],
            "steps": [
                {
                    "type": "action",
                    "name": "Revoke Compromised Credentials",
                    "action": "cloud_provider.revoke_credentials",
                    "params": {
                        "credential_id": "$trigger.credential_id"
                    }
                },
                {
                    "type": "action",
                    "name": "Force Password Reset",
                    "action": "log",
                    "params": {
                        "message": "Forcing password reset for user: $trigger.user_id",
                        "level": "warning"
                    }
                },
                {
                    "type": "action",
                    "name": "Terminate Active Sessions",
                    "action": "log",
                    "params": {
                        "message": "Terminating all active sessions for user: $trigger.user_id",
                        "level": "warning"
                    }
                },
                {
                    "type": "action",
                    "name": "Enable MFA",
                    "action": "log",
                    "params": {
                        "message": "Enforcing MFA for user: $trigger.user_id",
                        "level": "info"
                    }
                },
                {
                    "type": "action",
                    "name": "Notify User",
                    "action": "send_email",
                    "params": {
                        "to": ["$trigger.user_id"],
                        "subject": "URGENT: Your Credentials Have Been Compromised",
                        "body": "Your credentials have been compromised. Please reset your password immediately and enable MFA."
                    }
                },
                {
                    "type": "action",
                    "name": "Create Incident",
                    "action": "jira.create_ticket",
                    "params": {
                        "title": "Credential Compromise: $trigger.user_id",
                        "description": "Credentials compromised for user $trigger.user_id. Credentials revoked and password reset enforced.",
                        "priority": "High",
                        "issue_type": "Security Incident"
                    }
                },
                {
                    "type": "action",
                    "name": "Alert Security Team",
                    "action": "slack.send_message",
                    "params": {
                        "channel": "#security-alerts",
                        "message": "🔐 Credential compromise detected for user $trigger.user_id. Automated response completed."
                    }
                }
            ]
        }


# Initialize templates in database
async def initialize_playbook_templates(db):
    """Initialize playbook templates in database"""
    library = PlaybookTemplateLibrary()
    templates = library.get_all_templates()
    
    for template in templates:
        # Check if template already exists
        existing = await db.playbooks.find_one({
            "name": template["name"],
            "is_template": True
        })
        
        if not existing:
            await db.playbooks.insert_one(template)
            print(f"Initialized template: {template['name']}")
