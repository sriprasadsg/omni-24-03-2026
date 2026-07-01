"""SOC 2 Type II — AICPA Trust Services Criteria with domain-specific DB evaluations."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

FRAMEWORK_ID = "soc2"
FRAMEWORK_NAME = "SOC 2 Type II"
FRAMEWORK_VERSION = "2017 (updated 2022)"

CONTROLS: List[Dict[str, Any]] = [
    # CC1 — Control Environment
    {"id": "CC1.1", "theme": "Control Environment", "check_type": "policies_present",
     "title": "Commitment to integrity and ethical values",
     "description": "The entity demonstrates a commitment to integrity and ethical values."},
    {"id": "CC1.2", "theme": "Control Environment", "check_type": "count_gt_zero",
     "check_collection": "compliance_policies",
     "title": "Board oversight",
     "description": "Board demonstrates independence and oversight of internal controls."},
    {"id": "CC1.3", "theme": "Control Environment", "check_type": "rbac_configured",
     "title": "Organizational structures",
     "description": "Management establishes structures, reporting lines, and authorities."},
    {"id": "CC1.4", "theme": "Control Environment", "check_type": "training_present",
     "title": "Commitment to competence",
     "description": "The entity attracts, develops, and retains competent individuals."},

    # CC2 — Communication and Information
    {"id": "CC2.1", "theme": "Communication & Information", "check_type": "audit_log_volume",
     "title": "Information for internal control",
     "description": "The entity obtains and uses relevant quality information to support internal control."},
    {"id": "CC2.2", "theme": "Communication & Information", "check_type": "incidents_communicated",
     "title": "Internal communication",
     "description": "The entity communicates information necessary for internal control functioning."},
    {"id": "CC2.3", "theme": "Communication & Information", "check_type": "count_gt_zero",
     "check_collection": "incident_communications",
     "title": "External communication",
     "description": "The entity communicates with external parties regarding internal control matters."},

    # CC3 — Risk Assessment
    {"id": "CC3.1", "theme": "Risk Assessment", "check_type": "count_gt_zero",
     "check_collection": "risks",
     "title": "Objectives specification",
     "description": "The entity specifies objectives to enable identification of risks."},
    {"id": "CC3.2", "theme": "Risk Assessment", "check_type": "vuln_assessment",
     "title": "Risk identification and analysis",
     "description": "The entity identifies and analyzes risks to achievement of objectives."},
    {"id": "CC3.3", "theme": "Risk Assessment", "check_type": "security_events_monitored",
     "title": "Fraud risk",
     "description": "The entity considers the potential for fraud in assessing risks."},
    {"id": "CC3.4", "theme": "Risk Assessment", "check_type": "change_monitoring",
     "title": "Change identification and analysis",
     "description": "The entity identifies and assesses changes that could impact internal control."},

    # CC4 — Monitoring Activities
    {"id": "CC4.1", "theme": "Monitoring Activities", "check_type": "vuln_scan_recent",
     "title": "Ongoing evaluations",
     "description": "The entity selects and performs ongoing or separate evaluations."},
    {"id": "CC4.2", "theme": "Monitoring Activities", "check_type": "count_gt_zero",
     "check_collection": "incidents",
     "title": "Communication of deficiencies",
     "description": "The entity evaluates and communicates internal control deficiencies."},

    # CC5 — Control Activities
    {"id": "CC5.1", "theme": "Control Activities", "check_type": "playbooks_present",
     "title": "Control activities to mitigate risks",
     "description": "The entity selects and develops control activities to mitigate risks."},
    {"id": "CC5.2", "theme": "Control Activities", "check_type": "count_gt_zero",
     "check_collection": "automation_policies",
     "title": "Technology controls",
     "description": "The entity selects and develops general controls over technology."},
    {"id": "CC5.3", "theme": "Control Activities", "check_type": "count_gt_zero",
     "check_collection": "compliance_policies",
     "title": "Policies and procedures",
     "description": "The entity deploys control activities through policies."},

    # CC6 — Logical and Physical Access Controls
    {"id": "CC6.1", "theme": "Logical & Physical Access", "check_type": "mfa_coverage",
     "title": "Logical access security measures",
     "description": "The entity implements logical access security to protect against threats."},
    {"id": "CC6.2", "theme": "Logical & Physical Access", "check_type": "jit_access",
     "title": "Access provisioning and deprovisioning",
     "description": "Prior to issuing credentials, users are registered and authorized."},
    {"id": "CC6.3", "theme": "Logical & Physical Access", "check_type": "rbac_configured",
     "title": "Role-based access",
     "description": "Access to data and system components authorized based on roles."},
    {"id": "CC6.6", "theme": "Logical & Physical Access", "check_type": "security_events_monitored",
     "title": "External threat management",
     "description": "The entity implements controls to prevent or detect external threats."},
    {"id": "CC6.7", "theme": "Logical & Physical Access", "check_type": "dlp_active",
     "title": "Transmission encryption",
     "description": "The entity restricts transmission and movement of information."},
    {"id": "CC6.8", "theme": "Logical & Physical Access", "check_type": "edr_deployment",
     "title": "Malware protection",
     "description": "The entity implements controls to prevent or detect malware."},

    # CC7 — System Operations
    {"id": "CC7.1", "theme": "System Operations", "check_type": "fim_active",
     "title": "Infrastructure vulnerabilities managed",
     "description": "The entity uses detection and monitoring to identify infrastructure changes."},
    {"id": "CC7.2", "theme": "System Operations", "check_type": "siem_active",
     "title": "Anomalies and security incidents evaluated",
     "description": "The entity monitors system components for anomalous behavior."},
    {"id": "CC7.3", "theme": "System Operations", "check_type": "count_gt_zero",
     "check_collection": "incidents",
     "title": "Security events evaluated",
     "description": "The entity evaluates security events to determine if they are incidents."},
    {"id": "CC7.4", "theme": "System Operations", "check_type": "playbooks_present",
     "title": "Security incidents responded to",
     "description": "The entity responds to identified security incidents via a defined program."},

    # CC8 — Change Management
    {"id": "CC8.1", "theme": "Change Management", "check_type": "change_monitoring",
     "title": "Changes to infrastructure authorized",
     "description": "The entity authorizes, designs, configures, tests, and implements changes."},

    # CC9 — Risk Mitigation
    {"id": "CC9.1", "theme": "Risk Mitigation", "check_type": "count_gt_zero",
     "check_collection": "risks",
     "title": "Risk mitigation activities",
     "description": "The entity identifies and develops risk mitigation activities."},
    {"id": "CC9.2", "theme": "Risk Mitigation", "check_type": "vendor_risk",
     "title": "Vendor/partner risk managed",
     "description": "The entity assesses risks from vendors and business partners."},

    # A — Availability
    {"id": "A1.1", "theme": "Availability", "check_type": "capacity_monitored",
     "title": "Availability capacity planning",
     "description": "The entity maintains and monitors current processing capacity."},
    {"id": "A1.2", "theme": "Availability", "check_type": "backup_recent",
     "title": "Environmental threats managed",
     "description": "Environmental protections, backups, and recovery infrastructure authorized."},
]


def _now():
    return datetime.now(timezone.utc).isoformat()


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({**ctrl, "status": status, "evidence": evidence, "evaluated_at": _now()})
    return results


async def _run_check(db, ctrl: Dict[str, Any]):
    check_type = ctrl.get("check_type", "count_gt_zero")
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    cutoff_7d  = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    try:
        # ── Generic collection count ────────────────────────────────────────────
        if check_type == "count_gt_zero":
            coll_name = ctrl.get("check_collection", "")
            count = await db[coll_name].count_documents({})
            return ("pass" if count > 0 else "fail"), f"{count} records found"

        # ── CC1.1 / CC5.3: Policies present ───────────────────────────────────
        if check_type == "policies_present":
            count = await db.compliance_policies.count_documents({})
            active = await db.compliance_policies.count_documents({"status": "active"})
            if count > 0:
                return "pass", f"{count} compliance policies ({active} active)"
            return "fail", "No compliance policies defined"

        # ── CC1.3 / CC6.3: RBAC configured ────────────────────────────────────
        if check_type == "rbac_configured":
            roles = await db.roles.count_documents({})
            users_with_role = await db.users.count_documents({"role": {"$exists": True, "$ne": None}})
            if roles > 0 and users_with_role > 0:
                return "pass", f"{roles} RBAC roles; {users_with_role} users assigned"
            if roles > 0:
                return "partial", f"{roles} roles defined but no users assigned"
            return "fail", "No RBAC configuration"

        # ── CC1.4: Training ────────────────────────────────────────────────────
        if check_type == "training_present":
            completions = await db.training_completions.count_documents({})
            recent = await db.training_completions.count_documents({"completed_at": {"$gte": cutoff_30d}})
            if completions > 0:
                return "pass", f"{completions} training completions ({recent} in last 30 days)"
            return "fail", "No security training records found"

        # ── CC2.1: Audit log volume ────────────────────────────────────────────
        if check_type == "audit_log_volume":
            total = await db.audit_logs.count_documents({})
            recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_7d}})
            if recent > 50:
                return "pass", f"{recent} audit entries in last 7 days ({total} total)"
            if recent > 0:
                return "partial", f"Low audit volume: {recent} entries in 7 days"
            return "fail", "No recent audit log activity"

        # ── CC2.2: Incidents communicated ──────────────────────────────────────
        if check_type == "incidents_communicated":
            total = await db.incidents.count_documents({})
            communicated = await db.incidents.count_documents({"communicated": True})
            if total > 0:
                pct = round(communicated / total * 100)
                status = "pass" if pct >= 80 else "partial"
                return status, f"{pct}% of incidents ({communicated}/{total}) have communication records"
            return "not_applicable", "No incidents recorded"

        # ── CC3.2: Vulnerability assessment ───────────────────────────────────
        if check_type == "vuln_assessment":
            vulns = await db.vulnerabilities.count_documents({})
            recent_scans = await db.agent_vulnerability_scans.count_documents({"scanned_at": {"$gte": cutoff_30d}})
            if recent_scans > 0:
                return "pass", f"{recent_scans} scans in 30 days; {vulns} total vulnerabilities tracked"
            if vulns > 0:
                return "partial", f"{vulns} vulnerabilities tracked but no recent scans"
            return "fail", "No vulnerability assessment evidence"

        # ── CC3.3 / CC6.6: Security events monitored ──────────────────────────
        if check_type == "security_events_monitored":
            events = await db.security_events.count_documents({"timestamp": {"$gte": cutoff_7d}})
            alerts = await db.security_alerts.count_documents({"created_at": {"$gte": cutoff_7d}})
            if events > 0 or alerts > 0:
                return "pass", f"{events} security events + {alerts} alerts in last 7 days"
            return "fail", "No security events or alerts in last 7 days"

        # ── CC3.4 / CC8.1: Change monitoring via audit logs ───────────────────
        if check_type == "change_monitoring":
            audit_recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_30d}})
            change_events = await db.audit_logs.count_documents({
                "timestamp": {"$gte": cutoff_30d},
                "action": {"$regex": "update|change|modify|delete|create", "$options": "i"}
            })
            if audit_recent > 0:
                return "pass", f"{change_events} change events in audit logs (30 days total: {audit_recent})"
            return "fail", "No audit log evidence of change monitoring"

        # ── CC4.1: Vulnerability scans recent ─────────────────────────────────
        if check_type == "vuln_scan_recent":
            agent_scans = await db.agent_vulnerability_scans.count_documents({"scanned_at": {"$gte": cutoff_30d}})
            formal_scans = await db.vulnerability_scans.count_documents({"created_at": {"$gte": cutoff_30d}})
            total = max(agent_scans, formal_scans)
            if total > 0:
                return "pass", f"{total} vulnerability scans in last 30 days"
            return "fail", "No vulnerability scans in last 30 days"

        # ── CC5.1 / CC7.4: Playbooks present ──────────────────────────────────
        if check_type == "playbooks_present":
            pb = await db.playbooks.count_documents({})
            incidents = await db.incidents.count_documents({})
            if pb > 0:
                return "pass", f"{pb} IR playbooks; {incidents} incidents tracked"
            return "fail", "No incident response playbooks defined"

        # ── CC6.1: MFA coverage ────────────────────────────────────────────────
        if check_type == "mfa_coverage":
            total = await db.users.count_documents({})
            mfa = await db.users.count_documents({"mfa_enabled": True})
            if total == 0:
                return "not_applicable", "No user records"
            pct = round(mfa / total * 100)
            if pct >= 90:
                return "pass", f"{pct}% of users have MFA ({mfa}/{total})"
            if pct >= 50:
                return "partial", f"MFA coverage at {pct}% ({mfa}/{total})"
            return "fail", f"MFA coverage critically low: {pct}%"

        # ── CC6.2: JIT / privileged access ────────────────────────────────────
        if check_type == "jit_access":
            jit = await db.jit_requests.count_documents({})
            if jit > 0:
                return "pass", f"{jit} JIT privilege access requests recorded"
            return "partial", "No JIT requests — validate if least-privilege is enforced"

        # ── CC6.7: DLP active (transmission control) ──────────────────────────
        if check_type == "dlp_active":
            dlp_policies = await db.dlp_policies.count_documents({})
            dlp_events = await db.dlp_events.count_documents({})
            if dlp_policies > 0:
                return "pass", f"{dlp_policies} DLP policies; {dlp_events} DLP events"
            return "fail", "No DLP policies configured"

        # ── CC6.8: EDR deployment ──────────────────────────────────────────────
        if check_type == "edr_deployment":
            agents = await db.agents.count_documents({})
            edr = await db.edr_agents.count_documents({})
            if agents == 0:
                return "fail", "No agents registered"
            pct = round(edr / agents * 100) if agents else 0
            if pct >= 80:
                return "pass", f"EDR on {pct}% of endpoints ({edr}/{agents})"
            if pct >= 50:
                return "partial", f"EDR on {pct}% of endpoints"
            return "fail", f"EDR coverage insufficient: {pct}%"

        # ── CC7.1: FIM active ──────────────────────────────────────────────────
        if check_type == "fim_active":
            fim_events = await db.fim_events.count_documents({"timestamp": {"$gte": cutoff_7d}})
            if fim_events > 0:
                return "pass", f"{fim_events} FIM events in last 7 days"
            # Fallback: check agent FIM watcher flag
            fim_agents = await db.agents.count_documents({"meta.real_time_fim.watcher_running": True})
            if fim_agents > 0:
                return "pass", f"{fim_agents} agents have FIM watcher running"
            return "fail", "No FIM activity detected"

        # ── CC7.2: SIEM active ─────────────────────────────────────────────────
        if check_type == "siem_active":
            siem = await db.siem_logs.count_documents({"timestamp": {"$gte": cutoff_7d}})
            alerts = await db.security_alerts.count_documents({"created_at": {"$gte": cutoff_7d}})
            if siem > 0 or alerts > 0:
                return "pass", f"{siem} SIEM events + {alerts} alerts in last 7 days"
            return "fail", "No SIEM activity in last 7 days"

        # ── CC9.2: Vendor risk ─────────────────────────────────────────────────
        if check_type == "vendor_risk":
            vendors = await db.vendors.count_documents({})
            baa = await db.baa_agreements.count_documents({"status": "active"})
            if vendors > 0 or baa > 0:
                return "pass", f"{vendors} vendors tracked, {baa} active agreements"
            return "fail", "No vendor or partner risk assessments"

        # ── A1.1: Capacity monitoring ──────────────────────────────────────────
        if check_type == "capacity_monitored":
            metrics = await db.agent_metrics.count_documents({})
            agents = await db.agents.count_documents({"status": "Online"})
            if metrics > 0 or agents > 0:
                return "pass", f"{agents} online agents; {metrics} metric records"
            return "fail", "No capacity monitoring data"

        # ── A1.2: Backup recent ────────────────────────────────────────────────
        if check_type == "backup_recent":
            count = await db.backups.count_documents({"created_at": {"$gte": cutoff_30d}})
            total = await db.backups.count_documents({})
            if count > 0:
                return "pass", f"{count} backups in last 30 days ({total} total)"
            return "fail", "No backups in last 30 days"

    except Exception as exc:
        return "fail", f"Check error: {exc}"

    return "not_applicable", "Unknown check type"
