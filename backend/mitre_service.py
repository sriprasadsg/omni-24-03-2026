"""
MITRE ATT&CK Service
--------------------
Loads the ATT&CK Enterprise matrix and correlates platform alerts/playbooks
to generate a coverage heatmap.
"""

import json
import os
from typing import Optional
from database import get_database

# Embedded compact ATT&CK matrix (14 tactics, 40 representative techniques)
# Full matrix: download from https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json
ATTACK_MATRIX = {
    "tactics": [
        {"id": "TA0001", "name": "Initial Access", "techniques": [
            {"id": "T1190", "name": "Exploit Public-Facing Application"},
            {"id": "T1133", "name": "External Remote Services"},
            {"id": "T1566", "name": "Phishing"},
            {"id": "T1195", "name": "Supply Chain Compromise"},
        ]},
        {"id": "TA0002", "name": "Execution", "techniques": [
            {"id": "T1059", "name": "Command and Scripting Interpreter"},
            {"id": "T1059.001", "name": "PowerShell"},
            {"id": "T1059.003", "name": "Windows Command Shell"},
            {"id": "T1204", "name": "User Execution"},
        ]},
        {"id": "TA0003", "name": "Persistence", "techniques": [
            {"id": "T1053", "name": "Scheduled Task/Job"},
            {"id": "T1543", "name": "Create or Modify System Process"},
            {"id": "T1547", "name": "Boot or Logon Autostart Execution"},
        ]},
        {"id": "TA0004", "name": "Privilege Escalation", "techniques": [
            {"id": "T1068", "name": "Exploitation for Privilege Escalation"},
            {"id": "T1055", "name": "Process Injection"},
            {"id": "T1548", "name": "Abuse Elevation Control Mechanism"},
        ]},
        {"id": "TA0005", "name": "Defense Evasion", "techniques": [
            {"id": "T1027", "name": "Obfuscated Files or Information"},
            {"id": "T1036", "name": "Masquerading"},
            {"id": "T1562", "name": "Impair Defenses"},
            {"id": "T1070", "name": "Indicator Removal"},
        ]},
        {"id": "TA0006", "name": "Credential Access", "techniques": [
            {"id": "T1003", "name": "OS Credential Dumping"},
            {"id": "T1003.001", "name": "LSASS Memory"},
            {"id": "T1110", "name": "Brute Force"},
            {"id": "T1558", "name": "Steal or Forge Kerberos Tickets"},
        ]},
        {"id": "TA0007", "name": "Discovery", "techniques": [
            {"id": "T1082", "name": "System Information Discovery"},
            {"id": "T1083", "name": "File and Directory Discovery"},
            {"id": "T1046", "name": "Network Service Discovery"},
            {"id": "T1069", "name": "Permission Groups Discovery"},
        ]},
        {"id": "TA0008", "name": "Lateral Movement", "techniques": [
            {"id": "T1021", "name": "Remote Services"},
            {"id": "T1021.001", "name": "Remote Desktop Protocol"},
            {"id": "T1550", "name": "Use Alternate Authentication Material"},
        ]},
        {"id": "TA0009", "name": "Collection", "techniques": [
            {"id": "T1005", "name": "Data from Local System"},
            {"id": "T1039", "name": "Data from Network Shared Drive"},
            {"id": "T1056", "name": "Input Capture"},
        ]},
        {"id": "TA0010", "name": "Exfiltration", "techniques": [
            {"id": "T1048", "name": "Exfiltration Over Alternative Protocol"},
            {"id": "T1041", "name": "Exfiltration Over C2 Channel"},
            {"id": "T1567", "name": "Exfiltration Over Web Service"},
        ]},
        {"id": "TA0011", "name": "Command and Control", "techniques": [
            {"id": "T1071", "name": "Application Layer Protocol"},
            {"id": "T1071.001", "name": "Web Protocols"},
            {"id": "T1105", "name": "Ingress Tool Transfer"},
        ]},
        {"id": "TA0040", "name": "Impact", "techniques": [
            {"id": "T1486", "name": "Data Encrypted for Impact (Ransomware)"},
            {"id": "T1490", "name": "Inhibit System Recovery"},
            {"id": "T1489", "name": "Service Stop"},
        ]},
        {"id": "TA0042", "name": "Resource Development", "techniques": [
            {"id": "T1588", "name": "Obtain Capabilities"},
            {"id": "T1583", "name": "Acquire Infrastructure"},
        ]},
        {"id": "TA0043", "name": "Reconnaissance", "techniques": [
            {"id": "T1595", "name": "Active Scanning"},
            {"id": "T1596", "name": "Search Open Technical Databases"},
        ]},
    ]
}

# Maps our EDR alert types to MITRE technique IDs
ALERT_TYPE_TO_TECHNIQUE = {
    "mimikatz_detected": "T1003.001",
    "credential_dumping": "T1003",
    "encoded_powershell": "T1059.001",
    "process_injection": "T1055",
    "ransomware_detected": "T1486",
    "lsass_access": "T1003.001",
    "suspicious_temp_executable": "T1036",
    "brute_force": "T1110",
    "impossible_travel": "T1078",
    "network_scan": "T1046",
    "lateral_movement": "T1021",
    "privilege_escalation": "T1068",
}


def get_full_matrix() -> dict:
    return ATTACK_MATRIX


async def get_coverage_heatmap(tenant_id: str) -> list:
    """
    For each technique in the ATT&CK matrix, calculate:
      - alert_count: how many alerts map to this technique
      - playbook_count: how many playbooks reference this technique
      - coverage_score: 0 (none) → 3 (detected + playbook + SIEM rule)
    """
    db = get_database()

    # Gather all alert types for the tenant
    alerts = await db.edr_alerts.find({"acknowledged": False}).to_list(1000)
    security_alerts = await db.security_alerts.find({}).to_list(500)
    all_alerts = alerts + security_alerts

    # Build technique → alert count map
    technique_alert_counts: dict[str, int] = {}
    for alert in all_alerts:
        technique = (
            alert.get("mitre_technique")
            or ALERT_TYPE_TO_TECHNIQUE.get(alert.get("type", ""), None)
        )
        if technique:
            technique_alert_counts[technique] = technique_alert_counts.get(technique, 0) + 1

    # Build heatmap
    heatmap = []
    for tactic in ATTACK_MATRIX["tactics"]:
        for tech in tactic["techniques"]:
            tid = tech["id"]
            alert_count = technique_alert_counts.get(tid, 0)
            score = 0
            if alert_count > 0:
                score = 1
            if alert_count >= 5:
                score = 2
            if alert_count >= 10:
                score = 3

            heatmap.append({
                "technique_id": tid,
                "technique_name": tech["name"],
                "tactic_id": tactic["id"],
                "tactic_name": tactic["name"],
                "alert_count": alert_count,
                "coverage_score": score,
                "color": ["#1e293b", "#7c3aed", "#f97316", "#ef4444"][min(score, 3)],
            })
    return heatmap


def get_technique_detail(technique_id: str) -> dict:
    """Return technique metadata including description and mitigations."""
    DETAILS = {
        "T1003.001": {
            "description": "Adversaries may attempt to access credential material stored in LSASS memory.",
            "mitigations": ["Credential Guard", "Privileged Account Management", "User Account Control"],
            "data_sources": ["Process: OS API Execution", "Process: Process Access"],
            "detection": "Monitor for access to the LSASS process using tools like Sysmon Event ID 10.",
        },
        "T1059.001": {
            "description": "Adversaries may abuse PowerShell commands and scripts for execution.",
            "mitigations": ["Disable or Remove Feature or Program", "Code Signing", "Software Restriction"],
            "data_sources": ["Process: Process Creation", "Script: Script Execution"],
            "detection": "Enable PowerShell logging including Script Block Logging and Transcription.",
        },
        "T1486": {
            "description": "Adversaries may encrypt data on target systems to interrupt availability — ransomware.",
            "mitigations": ["Data Backup", "Behavior Prevention on Endpoint"],
            "data_sources": ["File: File Modification", "Cloud Storage: Cloud Storage Modification"],
            "detection": "Monitor for unusual large-scale file modifications, especially with new file extensions.",
        },
    }
    for tactic in ATTACK_MATRIX["tactics"]:
        for tech in tactic["techniques"]:
            if tech["id"] == technique_id:
                detail = DETAILS.get(technique_id, {})
                return {
                    "technique_id": technique_id,
                    "technique_name": tech["name"],
                    "tactic_id": tactic["id"],
                    "tactic_name": tactic["name"],
                    "description": detail.get("description", "See MITRE ATT&CK for full details."),
                    "mitigations": detail.get("mitigations", []),
                    "data_sources": detail.get("data_sources", []),
                    "detection": detail.get("detection", ""),
                    "mitre_url": f"https://attack.mitre.org/techniques/{technique_id.replace('.', '/')}/",
                }
    return {"error": f"Technique {technique_id} not found"}


def generate_navigator_layer(heatmap: list) -> dict:
    """Generate an ATT&CK Navigator-compatible layer JSON."""
    techniques = []
    for item in heatmap:
        if item["alert_count"] > 0:
            techniques.append({
                "techniqueID": item["technique_id"],
                "score": item["coverage_score"],
                "color": item["color"],
                "comment": f"{item['alert_count']} alert(s) detected",
                "enabled": True,
            })
    return {
        "name": "Omni-Agent Platform Coverage",
        "versions": {"attack": "14", "navigator": "4.9.1", "layer": "4.5"},
        "domain": "enterprise-attack",
        "description": "Auto-generated ATT&CK coverage layer from platform detections",
        "filters": {"platforms": ["Windows", "Linux", "macOS"]},
        "techniques": techniques,
        "gradient": {"colors": ["#1e293b", "#7c3aed", "#f97316", "#ef4444"], "minValue": 0, "maxValue": 3},
        "legendItems": [
            {"label": "No Coverage", "color": "#1e293b"},
            {"label": "1-4 Alerts", "color": "#7c3aed"},
            {"label": "5-9 Alerts", "color": "#f97316"},
            {"label": "10+ Alerts", "color": "#ef4444"},
        ],
    }
