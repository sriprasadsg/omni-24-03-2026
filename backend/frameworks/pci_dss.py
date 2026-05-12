"""PCI-DSS v4.0 compliance framework checks."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

FRAMEWORK_ID = "pci_dss"
FRAMEWORK_NAME = "PCI-DSS v4.0"
FRAMEWORK_VERSION = "4.0"

CONTROLS: List[Dict[str, Any]] = [
    # Requirement 1 — Network Security Controls
    {"id": "PCI-1.1", "theme": "Network Security",
     "title": "Network security controls established",
     "description": "Processes for installing and maintaining network security controls are defined.",
     "check_type": "network_topology_present"},
    {"id": "PCI-1.2", "theme": "Network Security",
     "title": "Network controls restrict inbound/outbound traffic",
     "description": "Network access controls restrict traffic to what is necessary.",
     "check_type": "firewall_rules_present"},
    {"id": "PCI-1.3", "theme": "Network Security",
     "title": "CDE network access restricted",
     "description": "Network access to and from the cardholder data environment is restricted.",
     "check_type": "network_segments_exist"},

    # Requirement 2 — Secure Configurations
    {"id": "PCI-2.1", "theme": "Secure Configuration",
     "title": "Secure configuration standards maintained",
     "description": "Secure configuration standards exist and are kept current.",
     "check_type": "hardening_baselines"},
    {"id": "PCI-2.2", "theme": "Secure Configuration",
     "title": "System components configured securely",
     "description": "System components are configured and managed securely.",
     "check_type": "hardening_applied_pct"},

    # Requirement 3 — Protect Stored Account Data
    {"id": "PCI-3.1", "theme": "Data Protection",
     "title": "Stored account data protection processes",
     "description": "Processes for protecting stored account data are defined.",
     "check_type": "dlp_policies_exist"},
    {"id": "PCI-3.4", "theme": "Data Protection",
     "title": "PAN protected in storage",
     "description": "Primary account numbers are secured with strong cryptography.",
     "check_type": "dlp_encryption_enabled"},
    {"id": "PCI-3.5", "theme": "Data Protection",
     "title": "PAN secured with cryptography",
     "description": "PAN is secured wherever stored.",
     "check_type": "dlp_events_present"},

    # Requirement 4 — Protect Cardholder Data with Cryptography
    {"id": "PCI-4.1", "theme": "Transmission Security",
     "title": "Secure transmission processes",
     "description": "Processes to protect cardholder data during transmission.",
     "check_type": "tls_monitoring"},
    {"id": "PCI-4.2", "theme": "Transmission Security",
     "title": "PAN secured during transmission",
     "description": "PAN is protected with strong cryptography during transmission.",
     "check_type": "tls_enforced"},

    # Requirement 5 — Protect Systems Against Malware
    {"id": "PCI-5.1", "theme": "Anti-Malware",
     "title": "Malware protection processes",
     "description": "Processes to protect all systems against malware.",
     "check_type": "edr_deployed"},
    {"id": "PCI-5.3", "theme": "Anti-Malware",
     "title": "Anti-malware mechanisms enabled",
     "description": "Anti-malware mechanisms are active, maintained, and monitored.",
     "check_type": "edr_active_pct"},

    # Requirement 6 — Develop and Maintain Secure Systems
    {"id": "PCI-6.2", "theme": "Secure Development",
     "title": "Bespoke software developed securely",
     "description": "Bespoke and custom software is developed securely.",
     "check_type": "sast_present"},
    {"id": "PCI-6.3", "theme": "Secure Development",
     "title": "Security vulnerabilities identified and addressed",
     "description": "Security vulnerabilities are identified and protected against.",
     "check_type": "vuln_tracked"},
    {"id": "PCI-6.4", "theme": "Secure Development",
     "title": "Web-facing applications protected",
     "description": "Public-facing web applications are protected against attacks.",
     "check_type": "dast_recent"},

    # Requirement 7 — Restrict Access by Business Need
    {"id": "PCI-7.1", "theme": "Access Control",
     "title": "Access control processes",
     "description": "Processes to restrict access to system components by business need.",
     "check_type": "rbac_present"},
    {"id": "PCI-7.2", "theme": "Access Control",
     "title": "Access to CDE restricted",
     "description": "Access to system components and data is appropriately defined.",
     "check_type": "jit_access"},

    # Requirement 8 — Identify Users and Authenticate Access
    {"id": "PCI-8.2", "theme": "Identity Management",
     "title": "User IDs and authentication managed",
     "description": "User identification and authentication are managed.",
     "check_type": "users_managed"},
    {"id": "PCI-8.4", "theme": "Identity Management",
     "title": "MFA implemented for CDE access",
     "description": "Multi-factor authentication is used for all access to the CDE.",
     "check_type": "mfa_coverage"},
    {"id": "PCI-8.6", "theme": "Identity Management",
     "title": "System/application accounts managed",
     "description": "System and application accounts are managed.",
     "check_type": "service_accounts_tracked"},

    # Requirement 10 — Log and Monitor All Access
    {"id": "PCI-10.2", "theme": "Logging & Monitoring",
     "title": "Audit logs implemented",
     "description": "Audit logs that capture required data elements are implemented.",
     "check_type": "audit_logs_present"},
    {"id": "PCI-10.3", "theme": "Logging & Monitoring",
     "title": "Audit logs protected",
     "description": "Audit logs are protected from destruction and unauthorized modifications.",
     "check_type": "audit_logs_volume"},
    {"id": "PCI-10.4", "theme": "Logging & Monitoring",
     "title": "Audit logs reviewed",
     "description": "Audit logs are reviewed to identify anomalies.",
     "check_type": "siem_active"},

    # Requirement 11 — Test Security of Systems
    {"id": "PCI-11.3", "theme": "Security Testing",
     "title": "Penetration testing performed",
     "description": "External and internal penetration testing is regularly performed.",
     "check_type": "pentest_or_vuln_scan"},
    {"id": "PCI-11.5", "theme": "Security Testing",
     "title": "Network intrusions detected",
     "description": "Network intrusions and unexpected file changes are detected.",
     "check_type": "fim_active"},

    # Requirement 12 — Organizational Policies
    {"id": "PCI-12.1", "theme": "Policies",
     "title": "Information security policy",
     "description": "A comprehensive information security policy is known and current.",
     "check_type": "compliance_policies_present"},
    {"id": "PCI-12.10", "theme": "Policies",
     "title": "Incident response plan",
     "description": "Suspected and confirmed security incidents are responded to immediately.",
     "check_type": "ir_plan_present"},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({**ctrl, "status": status, "evidence": evidence, "evaluated_at": _now()})
    return results


async def _run_check(db, ctrl: Dict[str, Any]):
    check_type = ctrl["check_type"]
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    cutoff_7d  = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cutoff_1y  = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()

    try:
        # ── PCI-1.1: Network topology documented ──────────────────────────────
        if check_type == "network_topology_present":
            count = await db.network_topology.count_documents({})
            agents = await db.agents.count_documents({})
            if count > 0 or agents > 0:
                return "pass", f"{count} network devices + {agents} managed endpoints documented"
            return "fail", "No network topology data found"

        # ── PCI-1.2: Firewall rules configured ────────────────────────────────
        if check_type == "firewall_rules_present":
            topo_with_fw = await db.network_topology.count_documents(
                {"firewall_rules": {"$exists": True, "$ne": []}}
            )
            total_topo = await db.network_topology.count_documents({})
            if topo_with_fw > 0:
                return "pass", f"{topo_with_fw}/{total_topo} network devices have firewall rules documented"
            if total_topo > 0:
                return "partial", "Network topology exists but no firewall rules documented"
            return "fail", "No network topology or firewall configuration found"

        # ── PCI-1.3: Network segments defined ────────────────────────────────
        if check_type == "network_segments_exist":
            seg_count = await db.network_segments.count_documents({})
            vlan_count = await db.network_topology.count_documents({"vlan_id": {"$exists": True}})
            if seg_count > 0 or vlan_count > 0:
                return "pass", f"{seg_count} network segments + {vlan_count} VLAN-tagged devices"
            return "fail", "No network segmentation data found"

        # ── PCI-2.1: Hardening baselines exist ────────────────────────────────
        if check_type == "hardening_baselines":
            count = await db.security_baselines.count_documents({})
            if count > 0:
                return "pass", f"{count} hardening baselines defined"
            # CISSP assessments as proxy
            cissp = await db.cissp_assessments.count_documents({"status": "completed"})
            if cissp > 0:
                return "partial", f"No formal baselines; {cissp} CISSP assessments as compensating control"
            return "fail", "No hardening baselines or security assessments"

        # ── PCI-2.2: Hardening applied to systems ─────────────────────────────
        if check_type == "hardening_applied_pct":
            total = await db.agents.count_documents({})
            hardened = await db.agents.count_documents({"hardening_applied": True})
            if total == 0:
                return "not_applicable", "No agents registered"
            pct = round(hardened / total * 100)
            if pct >= 90:
                return "pass", f"{pct}% of agents have hardening applied ({hardened}/{total})"
            if pct >= 50:
                return "partial", f"Only {pct}% of agents hardened ({hardened}/{total})"
            return "fail", f"{pct}% agents hardened — below 50% threshold"

        # ── PCI-3.1: DLP policies ─────────────────────────────────────────────
        if check_type == "dlp_policies_exist":
            dlp = await db.dlp_policies.count_documents({})
            if dlp > 0:
                return "pass", f"{dlp} DLP policies configured"
            return "fail", "No DLP policies configured"

        # ── PCI-3.4: Encryption enabled ───────────────────────────────────────
        if check_type == "dlp_encryption_enabled":
            enc_dlp = await db.dlp_policies.count_documents({"encryption_enabled": True})
            if enc_dlp > 0:
                return "pass", f"{enc_dlp} DLP policies have encryption enabled"
            total_dlp = await db.dlp_policies.count_documents({})
            if total_dlp > 0:
                return "partial", f"{total_dlp} DLP policies exist but none have encryption flag"
            return "fail", "No DLP policies with encryption found"

        # ── PCI-3.5: DLP events (active scanning) ─────────────────────────────
        if check_type == "dlp_events_present":
            events = await db.dlp_events.count_documents({})
            recent = await db.sensitive_data_findings.count_documents({"created_at": {"$gte": cutoff_30d}})
            if events > 0 or recent > 0:
                return "pass", f"{events} DLP events + {recent} sensitive data findings in 30d"
            return "fail", "No DLP scan activity found"

        # ── PCI-4.1: TLS monitoring active ────────────────────────────────────
        if check_type == "tls_monitoring":
            net_count = await db.network_topology.count_documents({})
            siem = await db.siem_logs.count_documents({"timestamp": {"$gte": cutoff_7d}})
            if net_count > 0:
                return "pass", f"Network topology monitored; {siem} SIEM events in last 7 days"
            return "fail", "No network monitoring data"

        # ── PCI-4.2: TLS enforced ─────────────────────────────────────────────
        if check_type == "tls_enforced":
            tls_doc = await db.network_topology.find_one({"tls_enforced": True})
            if tls_doc:
                count = await db.network_topology.count_documents({"tls_enforced": True})
                return "pass", f"{count} network devices have TLS enforcement documented"
            # Check security baselines for TLS config
            tls_baseline = await db.security_baselines.find_one({"tls_version": {"$exists": True}})
            if tls_baseline:
                return "partial", "No per-device TLS flag but TLS baseline configuration exists"
            return "fail", "No TLS enforcement documentation found"

        # ── PCI-5.1: EDR deployed ─────────────────────────────────────────────
        if check_type == "edr_deployed":
            edr = await db.edr_agents.count_documents({})
            agents = await db.agents.count_documents({})
            if edr > 0:
                pct = round(edr / agents * 100) if agents else 0
                return "pass", f"EDR deployed on {edr} endpoints ({pct}% of {agents} agents)"
            return "fail", "No EDR agents found"

        # ── PCI-5.3: EDR ≥90% coverage ───────────────────────────────────────
        if check_type == "edr_active_pct":
            total = await db.agents.count_documents({})
            edr = await db.edr_agents.count_documents({})
            if total == 0:
                return "not_applicable", "No agents registered"
            pct = round(edr / total * 100)
            if pct >= 90:
                return "pass", f"EDR active on {pct}% of agents"
            if pct >= 50:
                return "partial", f"EDR on {pct}% of agents (target: 90%)"
            return "fail", f"EDR on only {pct}% of agents"

        # ── PCI-6.2: SAST findings ────────────────────────────────────────────
        if check_type == "sast_present":
            sast = await db.sast_findings.count_documents({})
            if sast > 0:
                return "pass", f"{sast} SAST findings tracked (secure SDLC active)"
            repos = await db.code_repositories.count_documents({})
            if repos > 0:
                return "partial", f"{repos} code repositories registered but no SAST scans"
            return "fail", "No SAST scan results found"

        # ── PCI-6.3: Vulnerability tracking ──────────────────────────────────
        if check_type == "vuln_tracked":
            vuln = await db.vulnerabilities.count_documents({})
            scan = await db.vulnerability_scans.count_documents({})
            sbom_vuln = await db.software_components.count_documents({"vulnerabilities.0": {"$exists": True}})
            total = vuln + sbom_vuln
            if total > 0:
                return "pass", f"{vuln} CVEs in vuln DB + {sbom_vuln} vulnerable SBOM components tracked"
            if scan > 0:
                return "partial", f"{scan} scans run but no vulnerabilities catalogued"
            return "fail", "No vulnerability tracking data"

        # ── PCI-6.4: DAST recent ──────────────────────────────────────────────
        if check_type == "dast_recent":
            dast = await db.dast_scans.count_documents({"created_at": {"$gte": cutoff_30d}})
            if dast > 0:
                return "pass", f"{dast} DAST scans in last 30 days"
            total_dast = await db.dast_scans.count_documents({})
            if total_dast > 0:
                return "partial", f"{total_dast} DAST scans total but none in last 30 days"
            return "fail", "No DAST scans found"

        # ── PCI-7.1: RBAC configured ──────────────────────────────────────────
        if check_type == "rbac_present":
            roles = await db.roles.count_documents({})
            users = await db.users.count_documents({"role": {"$exists": True, "$ne": None}})
            if roles > 0 and users > 0:
                return "pass", f"{roles} RBAC roles + {users} users with role assignments"
            if roles > 0:
                return "partial", f"{roles} roles defined but no user role assignments"
            return "fail", "No RBAC configuration"

        # ── PCI-7.2: JIT / just-in-time access ───────────────────────────────
        if check_type == "jit_access":
            jit = await db.jit_requests.count_documents({})
            if jit > 0:
                return "pass", f"{jit} JIT access requests tracked"
            # Approval workflows as compensating control
            approvals = await db.approvals.count_documents({})
            if approvals > 0:
                return "partial", f"No JIT records; {approvals} approval workflows as compensating control"
            return "fail", "No JIT access or approval workflow data"

        # ── PCI-8.2: User accounts managed ───────────────────────────────────
        if check_type == "users_managed":
            users = await db.users.count_documents({})
            if users > 0:
                return "pass", f"{users} user accounts managed in the system"
            return "fail", "No user accounts found"

        # ── PCI-8.4: MFA ≥90% for privileged accounts ─────────────────────────
        if check_type == "mfa_coverage":
            total = await db.users.count_documents({})
            mfa = await db.users.count_documents({"mfa_enabled": True})
            if total == 0:
                return "not_applicable", "No users found"
            pct = round(mfa / total * 100)
            if pct >= 90:
                return "pass", f"{pct}% of users have MFA enabled ({mfa}/{total})"
            if pct >= 50:
                return "partial", f"MFA on {pct}% of users — PCI requires ≥90%"
            return "fail", f"MFA on only {pct}% of users"

        # ── PCI-8.6: Service accounts tracked ────────────────────────────────
        if check_type == "service_accounts_tracked":
            sa = await db.users.count_documents({"service_account": True})
            api_keys = await db.api_keys.count_documents({})
            if sa > 0 or api_keys > 0:
                return "pass", f"{sa} service accounts + {api_keys} API keys managed"
            return "fail", "No service accounts or API keys tracked"

        # ── PCI-10.2: Audit logs ──────────────────────────────────────────────
        if check_type == "audit_logs_present":
            count = await db.audit_logs.count_documents({})
            if count > 0:
                return "pass", f"{count} audit log entries found"
            return "fail", "No audit logs found"

        # ── PCI-10.3: Audit log volume (integrity proxy) ──────────────────────
        if check_type == "audit_logs_volume":
            recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_30d}})
            if recent >= 100:
                return "pass", f"{recent} audit entries in last 30 days — volume sufficient"
            if recent > 0:
                return "partial", f"Only {recent} audit entries in 30 days — low volume indicates gaps"
            return "fail", "No audit log activity in last 30 days"

        # ── PCI-10.4: SIEM active ─────────────────────────────────────────────
        if check_type == "siem_active":
            siem = await db.siem_logs.count_documents({"timestamp": {"$gte": cutoff_7d}})
            alerts = await db.security_alerts.count_documents({"created_at": {"$gte": cutoff_7d}})
            if siem > 0 or alerts > 0:
                return "pass", f"{siem} SIEM events + {alerts} alerts in last 7 days"
            return "fail", "No SIEM activity in last 7 days"

        # ── PCI-11.3: Pentest or vulnerability scan ────────────────────────────
        if check_type == "pentest_or_vuln_scan":
            pentest = await db.pentest_results.count_documents({"created_at": {"$gte": cutoff_1y}})
            vuln_scan = await db.vulnerability_scans.count_documents({"created_at": {"$gte": cutoff_30d}})
            if pentest > 0:
                return "pass", f"{pentest} penetration tests in last 12 months"
            if vuln_scan > 0:
                return "partial", f"No formal pentest; {vuln_scan} vulnerability scans in 30 days"
            return "fail", "No penetration test or recent vulnerability scans"

        # ── PCI-11.5: FIM events (change detection) ───────────────────────────
        if check_type == "fim_active":
            fim = await db.fim_events.count_documents({})
            recent_fim = await db.fim_events.count_documents({"received_at": {"$gte": cutoff_30d}})
            if fim > 0:
                return "pass", f"FIM active — {fim} total events, {recent_fim} in last 30 days"
            # Check if real_time_fim capability is deployed
            agents_with_fim = await db.agents.count_documents(
                {"meta.real_time_fim.watcher_running": True}
            )
            if agents_with_fim > 0:
                return "partial", f"FIM running on {agents_with_fim} agents but no events recorded yet"
            return "fail", "No FIM events and no active FIM watchers"

        # ── PCI-12.1: Compliance policies ─────────────────────────────────────
        if check_type == "compliance_policies_present":
            policies = await db.compliance_policies.count_documents({})
            frameworks = await db.compliance_frameworks.count_documents({})
            if policies > 0 or frameworks > 0:
                return "pass", f"{policies} compliance policies + {frameworks} frameworks configured"
            return "fail", "No compliance policies documented"

        # ── PCI-12.10: IR plan (playbooks + incidents) ─────────────────────────
        if check_type == "ir_plan_present":
            playbooks = await db.playbooks.count_documents({})
            incidents = await db.incidents.count_documents({})
            if playbooks > 0:
                return "pass", f"{playbooks} IR playbooks + {incidents} incidents tracked"
            return "fail", "No incident response playbooks found"

    except Exception as exc:
        return "fail", f"Check error: {exc}"

    return "not_applicable", "Unknown check type"
