"""NIST SP 800-53 Rev 5 — Security and Privacy Controls for Information Systems."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

FRAMEWORK_ID = "nist_800_53"
FRAMEWORK_NAME = "NIST SP 800-53 Rev 5"
FRAMEWORK_VERSION = "Rev 5 (2020)"

CONTROLS: List[Dict[str, Any]] = [
    # AC — Access Control
    {"id": "AC-2",  "theme": "Access Control",             "check_type": "rbac_configured",
     "title": "Account Management",
     "description": "Manage information system accounts including establishing, activating, and reviewing."},
    {"id": "AC-17", "theme": "Access Control",             "check_type": "mfa_coverage",
     "title": "Remote Access",
     "description": "Establish usage restrictions and implementation guidance for remote access."},
    # AU — Audit and Accountability
    {"id": "AU-2",  "theme": "Audit & Accountability",     "check_type": "audit_log_volume",
     "title": "Event Logging",
     "description": "Identify types of events that the system is capable of logging."},
    {"id": "AU-6",  "theme": "Audit & Accountability",     "check_type": "security_events_monitored",
     "title": "Audit Record Review and Analysis",
     "description": "Review and analyse system audit records for indications of inappropriate activity."},
    # CM — Configuration Management
    {"id": "CM-3",  "theme": "Configuration Management",   "check_type": "change_monitoring",
     "title": "Configuration Change Control",
     "description": "Determine the types of changes that are configuration-controlled."},
    # IA — Identification and Authentication
    {"id": "IA-2",  "theme": "Identification & Authentication", "check_type": "mfa_coverage",
     "title": "Identification and Authentication (Organizational Users)",
     "description": "Uniquely identify and authenticate organizational users."},
    # IR — Incident Response
    {"id": "IR-4",  "theme": "Incident Response",          "check_type": "playbooks_present",
     "title": "Incident Handling",
     "description": "Implement an incident handling capability for security incidents."},
    # SC — System and Communications Protection
    {"id": "SC-7",  "theme": "System & Communications",    "check_type": "security_events_monitored",
     "title": "Boundary Protection",
     "description": "Monitor and control communications at the external boundary of the system."},
    # SI — System and Information Integrity
    {"id": "SI-2",  "theme": "System & Info Integrity",    "check_type": "vuln_scan_recent",
     "title": "Flaw Remediation",
     "description": "Identify, report, and correct information system flaws."},
    # RA — Risk Assessment
    {"id": "RA-5",  "theme": "Risk Assessment",            "check_type": "vuln_scan_recent",
     "title": "Vulnerability Monitoring and Scanning",
     "description": "Monitor and scan the system for vulnerabilities periodically."},
    # SA — System and Services Acquisition
    {"id": "SA-11", "theme": "System & Services Acquisition", "check_type": "count_gt_zero",
     "check_collection": "vendors",
     "title": "Developer Testing and Evaluation",
     "description": "Require system developers to create a security assessment plan."},
    # CA — Assessment, Authorization, Monitoring
    {"id": "CA-7",  "theme": "Assessment & Authorization", "check_type": "audit_log_volume",
     "title": "Continuous Monitoring",
     "description": "Develop a system-level continuous monitoring strategy."},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run_check(db, ctrl: Dict[str, Any]):
    """Inline check runner — mirrors soc2.py _run_check patterns."""
    check_type = ctrl.get("check_type", "count_gt_zero")
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    cutoff_7d  = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
        if check_type == "count_gt_zero":
            coll = ctrl.get("check_collection", "")
            count = await db[coll].count_documents({})
            return ("pass" if count > 0 else "fail"), f"{count} records in {coll}"

        if check_type == "mfa_coverage":
            total = await db.users.count_documents({})
            mfa   = await db.users.count_documents({"mfa_enabled": True})
            if total == 0:
                return "not_applicable", "No user records"
            pct = round(mfa / total * 100)
            if pct >= 90:
                return "pass",    f"{pct}% of users have MFA ({mfa}/{total})"
            if pct >= 50:
                return "partial", f"MFA coverage at {pct}% ({mfa}/{total})"
            return "fail", f"MFA coverage critically low: {pct}%"

        if check_type == "rbac_configured":
            roles = await db.roles.count_documents({})
            assigned = await db.users.count_documents({"role": {"$exists": True, "$ne": None}})
            if roles > 0 and assigned > 0:
                return "pass",    f"{roles} RBAC roles; {assigned} users assigned"
            if roles > 0:
                return "partial", f"{roles} roles defined but no users assigned"
            return "fail", "No RBAC configuration"

        if check_type == "audit_log_volume":
            total  = await db.audit_logs.count_documents({})
            recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_7d}})
            if recent > 50:
                return "pass",    f"{recent} audit entries in last 7 days ({total} total)"
            if recent > 0:
                return "partial", f"Low audit volume: {recent} entries in 7 days"
            return "fail", "No recent audit log activity"

        if check_type == "security_events_monitored":
            events = await db.security_events.count_documents({"timestamp": {"$gte": cutoff_7d}})
            alerts = await db.security_alerts.count_documents({"created_at": {"$gte": cutoff_7d}})
            if events > 0 or alerts > 0:
                return "pass", f"{events} security events + {alerts} alerts in last 7 days"
            return "fail", "No security events or alerts in last 7 days"

        if check_type == "change_monitoring":
            recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_30d}})
            changes = await db.audit_logs.count_documents({
                "timestamp": {"$gte": cutoff_30d},
                "action": {"$regex": "update|change|modify|delete|create", "$options": "i"},
            })
            if recent > 0:
                return "pass", f"{changes} change events in audit logs (30-day total: {recent})"
            return "fail", "No audit log evidence of change monitoring"

        if check_type == "playbooks_present":
            pb         = await db.playbooks.count_documents({})
            incidents  = await db.incidents.count_documents({})
            if pb > 0:
                return "pass", f"{pb} IR playbooks; {incidents} incidents tracked"
            return "fail", "No incident response playbooks defined"

        if check_type == "vuln_scan_recent":
            agent_scans  = await db.agent_vulnerability_scans.count_documents(
                {"scanned_at": {"$gte": cutoff_30d}}
            )
            formal_scans = await db.vulnerability_scans.count_documents(
                {"created_at": {"$gte": cutoff_30d}}
            )
            total = max(agent_scans, formal_scans)
            if total > 0:
                return "pass", f"{total} vulnerability scans in last 30 days"
            return "fail", "No vulnerability scans in last 30 days"

        if check_type == "backup_recent":
            count = await db.backups.count_documents({"created_at": {"$gte": cutoff_30d}})
            total = await db.backups.count_documents({})
            if count > 0:
                return "pass", f"{count} backups in last 30 days ({total} total)"
            return "fail", "No backups in last 30 days"

    except Exception as exc:
        return "fail", f"Check error: {exc}"
    return "not_applicable", "Unknown check type"


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({**ctrl, "status": status, "evidence": evidence, "evaluated_at": _now()})
    return results
