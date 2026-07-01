"""CIS Controls v8 — 18 control groups with automated database checks."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

FRAMEWORK_ID = "cis_v8"
FRAMEWORK_NAME = "CIS Controls v8"
FRAMEWORK_VERSION = "8.0"

CONTROLS: List[Dict[str, Any]] = [
    {"id": "CIS-01", "title": "Inventory and Control of Enterprise Assets",
     "description": "Actively manage all enterprise assets connected to the network.",
     "check_type": "count_gt_zero", "check_collection": "assets", "ig_level": 1},
    {"id": "CIS-02", "title": "Inventory and Control of Software Assets",
     "description": "Actively manage all software on the network.",
     "check_type": "sbom_present", "ig_level": 1},
    {"id": "CIS-03", "title": "Data Protection",
     "description": "Develop processes to identify, classify, handle, retain, and dispose of data.",
     "check_type": "dlp_active", "ig_level": 1},
    {"id": "CIS-04", "title": "Secure Configuration of Enterprise Assets",
     "description": "Establish and maintain secure configurations.",
     "check_type": "hardening_applied", "ig_level": 1},
    {"id": "CIS-05", "title": "Account Management",
     "description": "Manage the lifecycle of system and application accounts.",
     "check_type": "users_with_mfa", "ig_level": 1},
    {"id": "CIS-06", "title": "Access Control Management",
     "description": "Use processes and tools to create, assign, manage, and revoke access credentials.",
     "check_type": "rbac_configured", "ig_level": 1},
    {"id": "CIS-07", "title": "Continuous Vulnerability Management",
     "description": "Continuously acquire, assess, and take action on vulnerability information.",
     "check_type": "vuln_scan_recent", "ig_level": 1},
    {"id": "CIS-08", "title": "Audit Log Management",
     "description": "Collect, alert, review, and retain audit logs to detect attacks.",
     "check_type": "audit_logs_active", "ig_level": 1},
    {"id": "CIS-09", "title": "Email and Web Browser Protections",
     "description": "Improve protections and detections of threats from email and web vectors.",
     "check_type": "count_gt_zero", "check_collection": "email_security_configs", "ig_level": 1},
    {"id": "CIS-10", "title": "Malware Defenses",
     "description": "Prevent or control the installation, spread, and execution of malicious code.",
     "check_type": "edr_active", "ig_level": 1},
    {"id": "CIS-11", "title": "Data Recovery",
     "description": "Establish and maintain data recovery practices.",
     "check_type": "recent_30d", "check_collection": "backups", "ig_level": 1},
    {"id": "CIS-12", "title": "Network Infrastructure Management",
     "description": "Establish, implement, and actively manage network devices.",
     "check_type": "network_managed", "ig_level": 2},
    {"id": "CIS-13", "title": "Network Monitoring and Defense",
     "description": "Operate processes and tools to establish and maintain network monitoring.",
     "check_type": "siem_active", "ig_level": 2},
    {"id": "CIS-14", "title": "Security Awareness and Skills Training",
     "description": "Establish a security awareness program.",
     "check_type": "count_gt_zero", "check_collection": "training_completions", "ig_level": 1},
    {"id": "CIS-15", "title": "Service Provider Management",
     "description": "Evaluate service providers who hold sensitive data.",
     "check_type": "vendors_assessed", "ig_level": 2},
    {"id": "CIS-16", "title": "Application Software Security",
     "description": "Manage the security lifecycle of software.",
     "check_type": "sast_dast_active", "ig_level": 2},
    {"id": "CIS-17", "title": "Incident Response Management",
     "description": "Establish a program to develop and maintain an incident response capability.",
     "check_type": "playbooks_present", "ig_level": 1},
    {"id": "CIS-18", "title": "Penetration Testing",
     "description": "Test the effectiveness and resiliency of enterprise assets.",
     "check_type": "pentest_recent", "ig_level": 2},
]


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({**ctrl, "status": status, "evidence": evidence,
                        "evaluated_at": datetime.now(timezone.utc).isoformat()})
    return results


async def _run_check(db, ctrl: Dict[str, Any]):
    check_type = ctrl.get("check_type", "count_gt_zero")
    coll_name  = ctrl.get("check_collection", "")
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    try:
        # ── Generic helpers ────────────────────────────────────────────────────
        if check_type == "count_gt_zero":
            coll = db[coll_name]
            count = await coll.count_documents({})
            return ("pass" if count > 0 else "fail"), f"{count} records"

        if check_type == "recent_30d":
            coll = db[coll_name]
            count = await coll.count_documents({"created_at": {"$gte": cutoff_30d}})
            return ("pass" if count > 0 else "fail"), f"{count} in last 30 days"

        # ── CIS-02: Software inventory (SBOMs uploaded) ────────────────────────
        if check_type == "sbom_present":
            count = await db.sboms.count_documents({})
            comps = await db.software_components.count_documents({})
            if count > 0:
                return "pass", f"{count} SBOMs, {comps} components tracked"
            pkg_count = await db.software_inventory.count_documents({})
            return ("pass" if pkg_count > 0 else "fail"), f"{pkg_count} packages in software inventory"

        # ── CIS-03: DLP / data classification ─────────────────────────────────
        if check_type == "dlp_active":
            dlp_count  = await db.dlp_policies.count_documents({})
            sens_count = await db.sensitive_data_findings.count_documents({})
            if dlp_count > 0 and sens_count > 0:
                return "pass", f"{dlp_count} DLP policies, {sens_count} data findings classified"
            if dlp_count > 0:
                return "partial", f"{dlp_count} DLP policies but no scan results"
            return "fail", "No DLP policies configured"

        # ── CIS-04: Hardening / security baselines ─────────────────────────────
        if check_type == "hardening_applied":
            baseline_count = await db.security_baselines.count_documents({})
            # Also check agent CISSP assessments as proxy
            assessment_count = await db.cissp_assessments.count_documents({"status": "completed"})
            if baseline_count > 0:
                return "pass", f"{baseline_count} hardening baselines applied"
            if assessment_count > 0:
                return "partial", f"No formal baselines, but {assessment_count} CISSP assessments completed"
            return "fail", "No hardening baselines or assessments found"

        # ── CIS-05: Account management + MFA coverage ──────────────────────────
        if check_type == "users_with_mfa":
            total = await db.users.count_documents({})
            mfa_enabled = await db.users.count_documents({"mfa_enabled": True})
            if total == 0:
                return "not_applicable", "No user records"
            pct = round(mfa_enabled / total * 100)
            if pct >= 90:
                return "pass", f"{pct}% of users have MFA ({mfa_enabled}/{total})"
            if pct >= 50:
                return "partial", f"{pct}% of users have MFA ({mfa_enabled}/{total})"
            return "fail", f"Only {pct}% of users have MFA enabled"

        # ── CIS-06: RBAC configured ────────────────────────────────────────────
        if check_type == "rbac_configured":
            roles = await db.roles.count_documents({})
            users_with_role = await db.users.count_documents({"role": {"$exists": True, "$ne": None}})
            if roles > 0 and users_with_role > 0:
                return "pass", f"{roles} roles configured, {users_with_role} users assigned"
            if roles > 0:
                return "partial", f"{roles} roles defined but no user assignments found"
            return "fail", "No RBAC roles configured"

        # ── CIS-07: Recent vulnerability scan ─────────────────────────────────
        if check_type == "vuln_scan_recent":
            scan_count = await db.vulnerability_scans.count_documents({"created_at": {"$gte": cutoff_30d}})
            vuln_count = await db.vulnerabilities.count_documents({})
            if scan_count > 0:
                return "pass", f"{scan_count} scans in last 30 days, {vuln_count} total vulnerabilities tracked"
            # Check for OSV scan results via software_components with cve data
            cve_comps = await db.software_components.count_documents({"vulnerabilities.0": {"$exists": True}})
            if cve_comps > 0:
                return "partial", f"No formal scans in 30d; {cve_comps} SBOM components have CVE data"
            return "fail", "No vulnerability scans in the last 30 days"

        # ── CIS-08: Audit log volume ───────────────────────────────────────────
        if check_type == "audit_logs_active":
            total = await db.audit_logs.count_documents({})
            recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_30d}})
            if recent > 100:
                return "pass", f"{recent} audit log entries in last 30 days ({total} total)"
            if recent > 0:
                return "partial", f"Only {recent} audit entries in last 30 days — volume may be too low"
            return "fail", "No audit log entries in last 30 days"

        # ── CIS-10: EDR active on agents ──────────────────────────────────────
        if check_type == "edr_active":
            total_agents = await db.agents.count_documents({})
            edr_agents  = await db.edr_agents.count_documents({})
            if total_agents == 0:
                return "fail", "No agents registered"
            pct = round(edr_agents / total_agents * 100) if total_agents else 0
            if pct >= 90:
                return "pass", f"EDR active on {pct}% of agents ({edr_agents}/{total_agents})"
            if pct >= 50:
                return "partial", f"EDR on {pct}% of agents ({edr_agents}/{total_agents})"
            return "fail", f"EDR only on {pct}% of agents ({edr_agents}/{total_agents})"

        # ── CIS-12: Network devices managed ────────────────────────────────────
        if check_type == "network_managed":
            devices = await db.network_topology.count_documents({})
            agents  = await db.agents.count_documents({})
            if devices > 0 or agents > 0:
                return "pass", f"{devices} network devices + {agents} managed agents discovered"
            return "fail", "No network topology data available"

        # ── CIS-13: SIEM active (events in last 7 days) ────────────────────────
        if check_type == "siem_active":
            cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            siem_events = await db.siem_logs.count_documents({"timestamp": {"$gte": cutoff_7d}})
            alert_count = await db.security_alerts.count_documents({"created_at": {"$gte": cutoff_7d}})
            if siem_events > 0 or alert_count > 0:
                return "pass", f"{siem_events} SIEM events + {alert_count} security alerts in last 7 days"
            return "fail", "No SIEM events or security alerts in last 7 days"

        # ── CIS-15: Vendors / BAAs assessed ────────────────────────────────────
        if check_type == "vendors_assessed":
            vendor_count = await db.vendors.count_documents({})
            baa_count    = await db.baa_agreements.count_documents({"status": "active"})
            if vendor_count > 0 or baa_count > 0:
                return "pass", f"{vendor_count} vendors tracked, {baa_count} active BAA agreements"
            return "fail", "No vendor assessments or BAA agreements"

        # ── CIS-16: SAST/DAST active ───────────────────────────────────────────
        if check_type == "sast_dast_active":
            dast_count = await db.dast_scans.count_documents({})
            sast_count = await db.sast_findings.count_documents({})
            if dast_count > 0 and sast_count > 0:
                return "pass", f"{sast_count} SAST findings, {dast_count} DAST scans"
            if dast_count > 0 or sast_count > 0:
                return "partial", f"{sast_count} SAST findings, {dast_count} DAST scans (only one active)"
            return "fail", "No SAST or DAST scan results found"

        # ── CIS-17: Playbooks / IR plans ──────────────────────────────────────
        if check_type == "playbooks_present":
            pb_count  = await db.playbooks.count_documents({})
            inc_count = await db.incidents.count_documents({})
            if pb_count > 0:
                return "pass", f"{pb_count} IR playbooks + {inc_count} incidents tracked"
            return "fail", "No incident response playbooks defined"

        # ── CIS-18: Recent pentest ─────────────────────────────────────────────
        if check_type == "pentest_recent":
            cutoff_1y = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
            count = await db.pentest_results.count_documents({"created_at": {"$gte": cutoff_1y}})
            dast  = await db.dast_scans.count_documents({"created_at": {"$gte": cutoff_1y}})
            if count > 0:
                return "pass", f"{count} penetration test results in last 12 months"
            if dast > 0:
                return "partial", f"No formal pentest but {dast} DAST scans in last 12 months"
            return "fail", "No penetration test results in last 12 months"

    except Exception as exc:
        return "not_applicable", f"Check error: {exc}"

    return "not_applicable", "Unknown check type"
