"""HIPAA / HITECH compliance framework checks with domain-specific DB evaluations."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

FRAMEWORK_ID = "hipaa"
FRAMEWORK_NAME = "HIPAA / HITECH"
FRAMEWORK_VERSION = "2013/2021"

CONTROLS: List[Dict[str, Any]] = [
    # Administrative Safeguards — §164.308
    {"id": "HIPAA-164.308(a)(1)", "theme": "Administrative", "check_type": "policies_present",
     "title": "Security Management Process",
     "description": "Implement policies to prevent, detect, contain, and correct security violations."},
    {"id": "HIPAA-164.308(a)(2)", "theme": "Administrative", "check_type": "security_officer",
     "title": "Assigned Security Responsibility",
     "description": "Identify the security official responsible for HIPAA policy development."},
    {"id": "HIPAA-164.308(a)(3)", "theme": "Administrative", "check_type": "rbac_configured",
     "title": "Workforce Security",
     "description": "Implement policies to ensure workforce has appropriate access to ePHI."},
    {"id": "HIPAA-164.308(a)(4)", "theme": "Administrative", "check_type": "jit_access",
     "title": "Information Access Management",
     "description": "Implement policies for authorizing access to ePHI."},
    {"id": "HIPAA-164.308(a)(5)", "theme": "Administrative", "check_type": "training_present",
     "title": "Security Awareness and Training",
     "description": "Implement a security awareness program for all workforce members."},
    {"id": "HIPAA-164.308(a)(6)", "theme": "Administrative", "check_type": "incidents_tracked",
     "title": "Security Incident Procedures",
     "description": "Implement policies to address security incidents."},
    {"id": "HIPAA-164.308(a)(7)", "theme": "Administrative", "check_type": "contingency_plan",
     "title": "Contingency Plan",
     "description": "Establish policies for responding to emergencies that damage systems with ePHI."},
    {"id": "HIPAA-164.308(a)(8)", "theme": "Administrative", "check_type": "periodic_evaluation",
     "title": "Evaluation",
     "description": "Perform periodic technical and non-technical evaluation of security controls."},
    {"id": "HIPAA-164.308(b)(1)", "theme": "Administrative", "check_type": "baa_coverage",
     "title": "Business Associate Contracts",
     "description": "Obtain satisfactory assurances from business associates that ePHI will be protected."},

    # Physical Safeguards — §164.310
    {"id": "HIPAA-164.310(a)(1)", "theme": "Physical", "check_type": "facility_access",
     "title": "Facility Access Controls",
     "description": "Implement policies to limit physical access to ePHI systems."},
    {"id": "HIPAA-164.310(b)", "theme": "Physical", "check_type": "edr_deployment",
     "title": "Workstation Use",
     "description": "Implement policies for proper workstation use to protect ePHI."},
    {"id": "HIPAA-164.310(d)(1)", "theme": "Physical", "check_type": "device_inventory",
     "title": "Device and Media Controls",
     "description": "Implement policies for receipt and removal of hardware and software."},

    # Technical Safeguards — §164.312
    {"id": "HIPAA-164.312(a)(1)", "theme": "Technical", "check_type": "mfa_coverage",
     "title": "Access Control",
     "description": "Technical policies for ePHI access by authorized persons only."},
    {"id": "HIPAA-164.312(a)(2)(i)", "theme": "Technical", "check_type": "unique_user_ids",
     "title": "Unique User Identification",
     "description": "Assign unique user identifiers to track user access activity."},
    {"id": "HIPAA-164.312(a)(2)(iv)", "theme": "Technical", "check_type": "ephi_encryption",
     "title": "Encryption and Decryption",
     "description": "Implement mechanisms to encrypt and decrypt ePHI."},
    {"id": "HIPAA-164.312(b)", "theme": "Technical", "check_type": "audit_controls",
     "title": "Audit Controls",
     "description": "Hardware, software, and procedural mechanisms to record ePHI access."},
    {"id": "HIPAA-164.312(c)(1)", "theme": "Technical", "check_type": "fim_integrity",
     "title": "Integrity Controls",
     "description": "Protect ePHI from improper alteration or destruction."},
    {"id": "HIPAA-164.312(d)", "theme": "Technical", "check_type": "mfa_coverage",
     "title": "Person or Entity Authentication",
     "description": "Verify identity of persons seeking access to ePHI."},
    {"id": "HIPAA-164.312(e)(1)", "theme": "Technical", "check_type": "transmission_security",
     "title": "Transmission Security",
     "description": "Guard against unauthorized access to ePHI transmitted over networks."},

    # Breach Notification — §164.400-414
    {"id": "HIPAA-164.404", "theme": "Breach Notification", "check_type": "breach_notification",
     "title": "Individual Notification",
     "description": "Notify affected individuals following discovery of a breach of unsecured PHI."},
    {"id": "HIPAA-164.406", "theme": "Breach Notification", "check_type": "count_gt_zero",
     "check_collection": "incident_communications",
     "title": "Media Notification",
     "description": "Notify media outlets of breaches affecting more than 500 residents."},
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

        # ── 164.308(a)(1): Policies ────────────────────────────────────────────
        if check_type == "policies_present":
            count = await db.compliance_policies.count_documents({})
            active = await db.compliance_policies.count_documents({"status": "active"})
            if count > 0:
                return "pass", f"{count} security policies ({active} active)"
            return "fail", "No compliance policies defined"

        # ── 164.308(a)(2): Security officer ───────────────────────────────────
        if check_type == "security_officer":
            officer = await db.users.find_one(
                {"role": {"$regex": "security|ciso|infosec", "$options": "i"}}, {"_id": 0}
            )
            if officer:
                return "pass", f"Security role holder found: {officer.get('username', 'unknown')}"
            # Fallback: check for admin roles
            admin = await db.users.find_one(
                {"role": {"$in": ["admin", "super_admin", "Super Admin"]}}, {"_id": 0}
            )
            if admin:
                return "partial", "No dedicated security officer; admin role identified as fallback"
            return "fail", "No security officer or security role identified"

        # ── 164.308(a)(3): RBAC for workforce ─────────────────────────────────
        if check_type == "rbac_configured":
            roles = await db.roles.count_documents({})
            users_with_role = await db.users.count_documents({"role": {"$exists": True, "$ne": None}})
            if roles > 0 and users_with_role > 0:
                return "pass", f"{roles} RBAC roles; {users_with_role} workforce members assigned"
            if roles > 0:
                return "partial", f"{roles} roles defined but no users assigned"
            return "fail", "No workforce access control structure"

        # ── 164.308(a)(4): JIT/access management ──────────────────────────────
        if check_type == "jit_access":
            jit = await db.jit_requests.count_documents({})
            if jit > 0:
                return "pass", f"{jit} JIT access requests recorded — least-privilege enforced"
            roles = await db.roles.count_documents({})
            if roles > 0:
                return "partial", f"{roles} RBAC roles configured; JIT access requests not tracked"
            return "fail", "No information access management controls found"

        # ── 164.308(a)(5): Training ────────────────────────────────────────────
        if check_type == "training_present":
            completions = await db.training_completions.count_documents({})
            recent = await db.training_completions.count_documents({"completed_at": {"$gte": cutoff_30d}})
            if completions > 0:
                return "pass", f"{completions} training completions ({recent} in last 30 days)"
            return "fail", "No security awareness training records"

        # ── 164.308(a)(6): Incidents tracked ──────────────────────────────────
        if check_type == "incidents_tracked":
            incidents = await db.incidents.count_documents({})
            playbooks = await db.playbooks.count_documents({})
            if incidents > 0 or playbooks > 0:
                return "pass", f"{incidents} incidents tracked; {playbooks} IR playbooks"
            return "fail", "No incident tracking or IR procedures"

        # ── 164.308(a)(7): Contingency plan / DR ──────────────────────────────
        if check_type == "contingency_plan":
            dr_runbooks = await db.dr_runbooks.count_documents({})
            playbooks = await db.playbooks.count_documents({})
            backups = await db.backups.count_documents({"created_at": {"$gte": cutoff_30d}})
            if dr_runbooks > 0:
                return "pass", f"{dr_runbooks} DR runbooks + {backups} recent backups"
            if playbooks > 0 and backups > 0:
                return "partial", f"No DR runbooks; {playbooks} IR playbooks + {backups} backups present"
            return "fail", "No contingency plans or disaster recovery procedures"

        # ── 164.308(a)(8): Periodic evaluation ────────────────────────────────
        if check_type == "periodic_evaluation":
            agent_scans = await db.agent_vulnerability_scans.count_documents({"scanned_at": {"$gte": cutoff_30d}})
            formal_scans = await db.vulnerability_scans.count_documents({"created_at": {"$gte": cutoff_30d}})
            cissp_assessments = await db.cissp_assessments.count_documents({"status": "completed"})
            total_evals = max(agent_scans, formal_scans) + cissp_assessments
            if total_evals > 0:
                return "pass", f"{max(agent_scans, formal_scans)} vulnerability scans + {cissp_assessments} security assessments in 30 days"
            return "fail", "No periodic security evaluation records in last 30 days"

        # ── 164.308(b)(1): BAA coverage ───────────────────────────────────────
        if check_type == "baa_coverage":
            active_baa = await db.baa_agreements.count_documents({"status": "active"})
            vendors = await db.vendors.count_documents({})
            if active_baa > 0:
                return "pass", f"{active_baa} active BAA agreements covering {vendors} vendors"
            if vendors > 0:
                return "fail", f"{vendors} vendors tracked but no active BAA agreements"
            return "fail", "No business associate agreements on record"

        # ── 164.310(a)(1): Facility access (assets with location) ─────────────
        if check_type == "facility_access":
            total_assets = await db.assets.count_documents({})
            located = await db.assets.count_documents({"location": {"$exists": True, "$ne": None}})
            if total_assets > 0 and located > 0:
                pct = round(located / total_assets * 100)
                return "pass", f"{pct}% of assets ({located}/{total_assets}) have location recorded"
            if total_assets > 0:
                return "partial", f"{total_assets} assets but no location data"
            return "fail", "No asset inventory for facility access controls"

        # ── 164.310(b): EDR on workstations ───────────────────────────────────
        if check_type == "edr_deployment":
            agents = await db.agents.count_documents({})
            edr = await db.edr_agents.count_documents({})
            if agents == 0:
                return "fail", "No workstation agents registered"
            pct = round(edr / agents * 100)
            if pct >= 80:
                return "pass", f"EDR on {pct}% of workstations ({edr}/{agents})"
            if pct >= 50:
                return "partial", f"EDR on {pct}% of workstations — insufficient for ePHI protection"
            return "fail", f"EDR coverage critically low: {pct}% of workstations"

        # ── 164.310(d)(1): Device inventory ───────────────────────────────────
        if check_type == "device_inventory":
            assets = await db.assets.count_documents({})
            agents = await db.agents.count_documents({})
            if assets > 0 or agents > 0:
                return "pass", f"{assets} assets + {agents} agents in device inventory"
            return "fail", "No device or media inventory"

        # ── 164.312(a)(1) / (d): MFA coverage ─────────────────────────────────
        if check_type == "mfa_coverage":
            total = await db.users.count_documents({})
            mfa = await db.users.count_documents({"mfa_enabled": True})
            if total == 0:
                return "not_applicable", "No user records"
            pct = round(mfa / total * 100)
            if pct >= 90:
                return "pass", f"{pct}% of users have MFA ({mfa}/{total})"
            if pct >= 70:
                return "partial", f"MFA at {pct}% — HIPAA recommends 100% for ePHI access"
            return "fail", f"MFA coverage critically low: {pct}% — ePHI at risk"

        # ── 164.312(a)(2)(i): Unique user IDs ────────────────────────────────
        if check_type == "unique_user_ids":
            total = await db.users.count_documents({})
            with_id = await db.users.count_documents({"id": {"$exists": True, "$ne": None}})
            if total > 0 and with_id == total:
                return "pass", f"All {total} users have unique identifiers"
            if total > 0:
                return "partial", f"{with_id}/{total} users have unique identifiers"
            return "fail", "No user records found"

        # ── 164.312(a)(2)(iv): ePHI encryption ────────────────────────────────
        if check_type == "ephi_encryption":
            enc_dlp = await db.dlp_policies.count_documents({"encryption_enabled": True})
            total_dlp = await db.dlp_policies.count_documents({})
            tls_certs = await db.tls_certificates.count_documents({})
            if enc_dlp > 0 or tls_certs > 0:
                return "pass", f"{enc_dlp}/{total_dlp} DLP policies enforce encryption; {tls_certs} TLS certs"
            if total_dlp > 0:
                return "partial", f"{total_dlp} DLP policies but encryption not enabled"
            return "fail", "No encryption controls for ePHI"

        # ── 164.312(b): Audit controls / access logs ──────────────────────────
        if check_type == "audit_controls":
            total = await db.audit_logs.count_documents({})
            recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_7d}})
            if recent > 20:
                return "pass", f"{recent} audit entries in last 7 days ({total} total)"
            if recent > 0:
                return "partial", f"Low audit volume: {recent} entries in 7 days — may not meet HIPAA audit requirements"
            return "fail", "No audit log activity — ePHI access not being recorded"

        # ── 164.312(c)(1): FIM integrity controls ─────────────────────────────
        if check_type == "fim_integrity":
            fim_events = await db.fim_events.count_documents({"timestamp": {"$gte": cutoff_7d}})
            if fim_events > 0:
                return "pass", f"{fim_events} FIM integrity events in last 7 days"
            fim_agents = await db.agents.count_documents({"meta.real_time_fim.watcher_running": True})
            if fim_agents > 0:
                return "pass", f"{fim_agents} agents monitoring file integrity (FIM active)"
            return "fail", "No file integrity monitoring — ePHI files unprotected from alteration"

        # ── 164.312(e)(1): Transmission security ──────────────────────────────
        if check_type == "transmission_security":
            tls_certs = await db.tls_certificates.count_documents({})
            network_nodes = await db.network_topology.count_documents({})
            dlp_policies = await db.dlp_policies.count_documents({})
            if tls_certs > 0 or dlp_policies > 0:
                return "pass", f"{tls_certs} TLS certs + {dlp_policies} DLP policies protecting transmission"
            if network_nodes > 0:
                return "partial", f"{network_nodes} network nodes monitored but no TLS/DLP evidence"
            return "fail", "No transmission security controls identified"

        # ── 164.404: Breach notification ──────────────────────────────────────
        if check_type == "breach_notification":
            phi_incidents = await db.incidents.count_documents({"phi_breach_reported": {"$exists": True}})
            ir_playbooks = await db.playbooks.count_documents({})
            if phi_incidents > 0:
                reported = await db.incidents.count_documents({"phi_breach_reported": True})
                return "pass", f"{reported} PHI breach notifications sent"
            if ir_playbooks > 0:
                return "partial", f"No PHI breach incidents; {ir_playbooks} IR playbooks define notification procedures"
            return "fail", "No breach notification procedures or records"

    except Exception as exc:
        return "fail", f"Check error: {exc}"

    return "not_applicable", "Unknown check type"
