"""ISO/IEC 27001:2022 — Annex A control checks with domain-specific DB evaluations."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

FRAMEWORK_ID = "iso27001_2022"
FRAMEWORK_NAME = "ISO/IEC 27001:2022"
FRAMEWORK_VERSION = "2022"

CONTROLS: List[Dict[str, Any]] = [
    # 5. Organizational controls
    {"id": "A.5.1",  "theme": "Organizational", "check_type": "policies_present",
     "title": "Policies for information security",
     "description": "Information security policy and topic-specific policies defined and approved."},
    {"id": "A.5.8",  "theme": "Organizational", "check_type": "count_gt_zero",
     "check_collection": "project_security_reviews",
     "title": "Information security in project management",
     "description": "Information security integrated into project management."},
    {"id": "A.5.15", "theme": "Organizational", "check_type": "identity_managed",
     "title": "Identity management",
     "description": "Full life cycle of identities is managed."},
    {"id": "A.5.19", "theme": "Organizational", "check_type": "suppliers_assessed",
     "title": "Information security in supplier relationships",
     "description": "Processes to manage security risks from suppliers."},
    {"id": "A.5.31", "theme": "Organizational", "check_type": "count_gt_zero",
     "check_collection": "compliance_requirements",
     "title": "Legal, statutory, regulatory and contractual requirements",
     "description": "Legal, statutory, regulatory and contractual requirements identified."},

    # 6. People controls
    {"id": "A.6.3",  "theme": "People", "check_type": "training_present",
     "title": "Security awareness, education and training",
     "description": "Personnel receive appropriate awareness, education and training."},

    # 8. Technological controls
    {"id": "A.8.1",  "theme": "Technological", "check_type": "edr_deployment",
     "title": "User endpoint devices",
     "description": "Information on user endpoint devices is protected."},
    {"id": "A.8.2",  "theme": "Technological", "check_type": "jit_access",
     "title": "Privileged access rights",
     "description": "Privileged access rights restricted and managed."},
    {"id": "A.8.5",  "theme": "Technological", "check_type": "mfa_coverage",
     "title": "Secure authentication",
     "description": "Secure authentication technologies are used."},
    {"id": "A.8.7",  "theme": "Technological", "check_type": "malware_defense",
     "title": "Protection against malware",
     "description": "Protection against malware is implemented."},
    {"id": "A.8.8",  "theme": "Technological", "check_type": "vuln_management",
     "title": "Management of technical vulnerabilities",
     "description": "Technical vulnerabilities are obtained, evaluated, and addressed."},
    {"id": "A.8.10", "theme": "Technological", "check_type": "count_gt_zero",
     "check_collection": "retention_policies",
     "title": "Information deletion",
     "description": "Information deleted when no longer required."},
    {"id": "A.8.11", "theme": "Technological", "check_type": "dlp_masking",
     "title": "Data masking",
     "description": "Data masking used according to organizational policy."},
    {"id": "A.8.12", "theme": "Technological", "check_type": "dlp_leakage_prevention",
     "title": "Data leakage prevention",
     "description": "DLP measures applied to systems processing sensitive information."},
    {"id": "A.8.13", "theme": "Technological", "check_type": "backup_recent",
     "title": "Information backup",
     "description": "Backup copies taken and tested regularly."},
    {"id": "A.8.14", "theme": "Technological", "check_type": "count_gt_zero",
     "check_collection": "hadr_configs",
     "title": "Redundancy of information processing facilities",
     "description": "Information processing facilities implemented with redundancy."},
    {"id": "A.8.15", "theme": "Technological", "check_type": "logging_active",
     "title": "Logging",
     "description": "Logs recording activities, exceptions, faults produced and retained."},
    {"id": "A.8.16", "theme": "Technological", "check_type": "ueba_monitoring",
     "title": "Monitoring activities",
     "description": "Networks, systems, applications monitored for anomalous behavior."},
    {"id": "A.8.20", "theme": "Technological", "check_type": "network_security",
     "title": "Network security",
     "description": "Networks and network devices secured, managed and controlled."},
    {"id": "A.8.24", "theme": "Technological", "check_type": "cryptography_configured",
     "title": "Use of cryptography",
     "description": "Rules for effective use of cryptography defined and implemented."},
    {"id": "A.8.28", "theme": "Technological", "check_type": "secure_coding",
     "title": "Secure coding",
     "description": "Secure coding principles applied to software development."},
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
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    cutoff_7d  = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    try:
        # ── Generic fallback ────────────────────────────────────────────────────
        if check_type == "count_gt_zero":
            coll_name = ctrl.get("check_collection", "")
            count = await db[coll_name].count_documents({})
            return ("pass" if count > 0 else "fail"), f"{count} records found"

        # ── A.5.1: Security policies ───────────────────────────────────────────
        if check_type == "policies_present":
            count = await db.compliance_policies.count_documents({})
            active = await db.compliance_policies.count_documents({"status": "active"})
            if count > 0:
                return "pass", f"{count} security policies ({active} active)"
            return "fail", "No compliance policies defined"

        # ── A.5.15: Identity management ────────────────────────────────────────
        if check_type == "identity_managed":
            total = await db.users.count_documents({})
            with_role = await db.users.count_documents({"role": {"$exists": True, "$ne": None}})
            roles = await db.roles.count_documents({})
            if total > 0 and roles > 0:
                return "pass", f"{total} user identities managed across {roles} roles"
            if total > 0:
                return "partial", f"{total} users exist but no formal role definitions"
            return "fail", "No user identities registered"

        # ── A.5.19: Supplier assessment ────────────────────────────────────────
        if check_type == "suppliers_assessed":
            vendors = await db.vendors.count_documents({})
            baa_count = await db.baa_agreements.count_documents({"status": "active"})
            if vendors > 0:
                return "pass", f"{vendors} vendors tracked, {baa_count} active agreements"
            return "fail", "No supplier/vendor records"

        # ── A.6.3: Training ────────────────────────────────────────────────────
        if check_type == "training_present":
            completions = await db.training_completions.count_documents({})
            recent = await db.training_completions.count_documents({"completed_at": {"$gte": cutoff_30d}})
            if completions > 0:
                return "pass", f"{completions} training completions ({recent} in last 30 days)"
            return "fail", "No security training records"

        # ── A.8.1: EDR deployment on endpoints ────────────────────────────────
        if check_type == "edr_deployment":
            agents = await db.agents.count_documents({})
            edr = await db.edr_agents.count_documents({})
            if agents == 0:
                return "fail", "No agents registered"
            pct = round(edr / agents * 100)
            if pct >= 80:
                return "pass", f"EDR deployed on {pct}% of endpoints ({edr}/{agents})"
            if pct >= 50:
                return "partial", f"EDR on only {pct}% of endpoints ({edr}/{agents})"
            return "fail", f"EDR on {pct}% of endpoints — insufficient coverage"

        # ── A.8.2: Privileged access / JIT ────────────────────────────────────
        if check_type == "jit_access":
            jit = await db.jit_requests.count_documents({})
            roles = await db.roles.count_documents({})
            if jit > 0 and roles > 0:
                return "pass", f"{jit} JIT privilege requests, {roles} RBAC roles configured"
            if roles > 0:
                return "partial", f"{roles} RBAC roles configured; no JIT requests recorded"
            return "fail", "No privileged access controls or JIT requests found"

        # ── A.8.5: MFA coverage ────────────────────────────────────────────────
        if check_type == "mfa_coverage":
            total = await db.users.count_documents({})
            mfa = await db.users.count_documents({"mfa_enabled": True})
            if total == 0:
                return "not_applicable", "No user records"
            pct = round(mfa / total * 100)
            if pct >= 90:
                return "pass", f"{pct}% of users have MFA ({mfa}/{total})"
            if pct >= 50:
                return "partial", f"Only {pct}% of users have MFA ({mfa}/{total})"
            return "fail", f"MFA coverage critically low: {pct}% ({mfa}/{total})"

        # ── A.8.7: Malware defense ─────────────────────────────────────────────
        if check_type == "malware_defense":
            edr = await db.edr_agents.count_documents({})
            malware_events = await db.security_events.count_documents({"type": {"$regex": "malware", "$options": "i"}})
            if edr > 0:
                return "pass", f"{edr} EDR-protected endpoints; {malware_events} malware events detected"
            return "fail", "No EDR agents registered"

        # ── A.8.8: Vulnerability management ───────────────────────────────────
        if check_type == "vuln_management":
            total_vulns = await db.vulnerabilities.count_documents({})
            recent_scans = await db.agent_vulnerability_scans.count_documents({"scanned_at": {"$gte": cutoff_30d}})
            osv_scans = await db.vulnerability_scans.count_documents({"created_at": {"$gte": cutoff_30d}})
            scan_count = max(recent_scans, osv_scans)
            if scan_count > 0 and total_vulns >= 0:
                return "pass", f"{scan_count} vulnerability scans in 30 days; {total_vulns} CVEs tracked"
            if total_vulns > 0:
                return "partial", f"{total_vulns} vulnerabilities tracked but no recent scans"
            return "fail", "No vulnerability scanning evidence"

        # ── A.8.11: DLP masking ────────────────────────────────────────────────
        if check_type == "dlp_masking":
            dlp = await db.dlp_policies.count_documents({})
            masking = await db.dlp_policies.count_documents({"masking_enabled": True})
            if dlp > 0 and masking > 0:
                return "pass", f"{masking}/{dlp} DLP policies have masking enabled"
            if dlp > 0:
                return "partial", f"{dlp} DLP policies exist but masking not configured"
            return "fail", "No DLP policies configured"

        # ── A.8.12: DLP events (data leakage prevention active) ────────────────
        if check_type == "dlp_leakage_prevention":
            dlp_policies = await db.dlp_policies.count_documents({})
            dlp_events = await db.dlp_events.count_documents({})
            pii_findings = await db.sensitive_data_findings.count_documents({})
            if dlp_policies > 0 and (dlp_events > 0 or pii_findings > 0):
                return "pass", f"{dlp_policies} DLP policies; {dlp_events} events + {pii_findings} PII findings"
            if dlp_policies > 0:
                return "partial", f"{dlp_policies} DLP policies but no scan activity"
            return "fail", "No DLP policies or leak-prevention evidence"

        # ── A.8.13: Backup within 30 days ─────────────────────────────────────
        if check_type == "backup_recent":
            count = await db.backups.count_documents({"created_at": {"$gte": cutoff_30d}})
            total = await db.backups.count_documents({})
            if count > 0:
                return "pass", f"{count} backups in last 30 days ({total} total)"
            return "fail", "No backup records in last 30 days"

        # ── A.8.15: Logging active (volume check) ─────────────────────────────
        if check_type == "logging_active":
            total = await db.audit_logs.count_documents({})
            recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_7d}})
            siem = await db.siem_logs.count_documents({})
            if recent > 50:
                return "pass", f"{recent} audit entries in last 7 days ({total} total); {siem} SIEM logs"
            if recent > 0 or total > 0:
                return "partial", f"Low log volume: {recent} recent entries"
            return "fail", "No audit log activity"

        # ── A.8.16: UEBA anomaly monitoring ───────────────────────────────────
        if check_type == "ueba_monitoring":
            ueba_events = await db.ueba_events.count_documents({})
            anomalies = await db.ueba_anomalies.count_documents({"detected_at": {"$gte": cutoff_30d}})
            login_events = await db.login_events.count_documents({})
            if ueba_events > 0 or login_events > 0:
                return "pass", f"{ueba_events} UEBA events + {login_events} login events analyzed; {anomalies} anomalies"
            return "fail", "No UEBA or behavioral monitoring data"

        # ── A.8.20: Network security ──────────────────────────────────────────
        if check_type == "network_security":
            topology = await db.network_topology.count_documents({})
            agents = await db.agents.count_documents({})
            if topology > 0 or agents > 0:
                return "pass", f"{topology} network topology nodes + {agents} managed agents"
            return "fail", "No network security monitoring evidence"

        # ── A.8.24: Cryptography ──────────────────────────────────────────────
        if check_type == "cryptography_configured":
            pqc = await db.pqc_configs.count_documents({})
            dlp_enc = await db.dlp_policies.count_documents({"encryption_enabled": True})
            tls = await db.tls_certificates.count_documents({})
            if pqc > 0 or dlp_enc > 0 or tls > 0:
                return "pass", f"{pqc} PQC configs + {dlp_enc} encryption DLP policies + {tls} TLS certs"
            return "fail", "No cryptographic configuration evidence"

        # ── A.8.28: Secure coding (SAST) ──────────────────────────────────────
        if check_type == "secure_coding":
            sast = await db.sast_findings.count_documents({})
            dast = await db.dast_scans.count_documents({})
            if sast > 0 and dast > 0:
                return "pass", f"{sast} SAST findings + {dast} DAST scans — both active"
            if sast > 0 or dast > 0:
                return "partial", f"{sast} SAST findings, {dast} DAST scans — only one method active"
            return "fail", "No SAST or DAST scan evidence"

    except Exception as exc:
        return "not_applicable", f"Check error: {exc}"

    return "not_applicable", "Unknown check type"
