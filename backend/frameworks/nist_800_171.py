"""NIST SP 800-171 Rev 2 — Protecting Controlled Unclassified Information (CUI)."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

FRAMEWORK_ID = "nist_800_171"
FRAMEWORK_NAME = "NIST SP 800-171 Rev 2"
FRAMEWORK_VERSION = "Rev 2 (2020)"

CONTROLS: List[Dict[str, Any]] = [
    # 3.1 — Access Control
    {"id": "3.1.1",  "theme": "Access Control",             "check_type": "rbac_configured",
     "title": "Authorized Access Control",
     "description": "Limit system access to authorized users and processes acting on behalf of such users."},
    {"id": "3.1.2",  "theme": "Access Control",             "check_type": "rbac_configured",
     "title": "Transaction and Function Control",
     "description": "Limit system access to the types of transactions and functions authorized users are permitted to execute."},
    # 3.3 — Audit and Accountability
    {"id": "3.3.1",  "theme": "Audit & Accountability",     "check_type": "audit_log_volume",
     "title": "System Auditing",
     "description": "Create and retain system audit logs to enable monitoring, analysis, and investigation."},
    {"id": "3.3.2",  "theme": "Audit & Accountability",     "check_type": "security_events_monitored",
     "title": "User Accountability",
     "description": "Ensure that actions of individual users can be traced to those users."},
    # 3.4 — Configuration Management
    {"id": "3.4.1",  "theme": "Configuration Management",   "check_type": "change_monitoring",
     "title": "System Baselining",
     "description": "Establish and maintain baseline configurations and inventories of systems."},
    # 3.5 — Identification and Authentication
    {"id": "3.5.3",  "theme": "Identification & Authentication", "check_type": "mfa_coverage",
     "title": "Multifactor Authentication",
     "description": "Use multifactor authentication for local and network access to privileged accounts."},
    {"id": "3.5.1",  "theme": "Identification & Authentication", "check_type": "rbac_configured",
     "title": "User Identification",
     "description": "Identify system users, processes, and devices as a prerequisite to allowing access."},
    # 3.6 — Incident Response
    {"id": "3.6.1",  "theme": "Incident Response",          "check_type": "playbooks_present",
     "title": "Incident Handling",
     "description": "Establish an operational incident-handling capability for systems."},
    # 3.11 — Risk Assessment
    {"id": "3.11.2", "theme": "Risk Assessment",            "check_type": "vuln_scan_recent",
     "title": "Vulnerability Scanning",
     "description": "Scan for vulnerabilities in systems periodically and when new vulnerabilities are identified."},
    # 3.13 — System and Communications Protection
    {"id": "3.13.1", "theme": "System & Communications",    "check_type": "security_events_monitored",
     "title": "Boundary Protection",
     "description": "Monitor, control, and protect communications at external boundaries of systems."},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run_check(db, ctrl: Dict[str, Any]):
    """Inline check runner — mirrors soc2.py _run_check patterns."""
    check_type = ctrl.get("check_type", "count_gt_zero")
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    cutoff_7d  = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
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
            roles    = await db.roles.count_documents({})
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
            pb        = await db.playbooks.count_documents({})
            incidents = await db.incidents.count_documents({})
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

    except Exception as exc:
        return "fail", f"Check error: {exc}"
    return "not_applicable", "Unknown check type"


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({**ctrl, "status": status, "evidence": evidence, "evaluated_at": _now()})
    return results
