"""Shared check-dispatch helpers for the framework modules added in phase 19
(ens, mas_trm, irap, iso_27017, iso_27018, bsi_c5, ffiec, owasp_top10, tisax,
aws_well_architected, rbi_csf, tic_3_0, kisa_isms, fedramp_high).

Mirrors the check_type -> MongoDB dispatch pattern established in
nist_800_53.py / soc2.py / pci_dss.py / hipaa.py / cis_controls.py: given a
control dict with a "check_type" key, run a real query against MongoDB and
return a (status, evidence) tuple. Percentage/ratio-based checks (MFA
coverage, RBAC, EDR/malware, TLS, pen-testing, ...) reuse the exact
thresholds and collection names those files already established, so results
stay consistent for any check_type shared across multiple frameworks.

check_types that are unique to a single new framework (mostly FedRAMP High's
NIST 800-53 High-baseline-specific controls) and have no established
multi-signal precedent elsewhere in this file family fall back to a generic
"does at least one matching document exist" presence check -- the same shape
as the pre-existing `count_gt_zero` check_type, just with the
collection/filter baked in per check_type instead of supplied via
`check_collection`. Anything not mapped at all falls through to
"not_applicable", matching every existing `_run_check`'s final fallback.

Extracted here (rather than duplicated 14x) per the phase 19 code review
(CR-02): most check_type values used by these new frameworks already exist
elsewhere in this file family, and duplicating percentage-threshold logic 14
times would make future threshold changes error-prone. Pre-existing modules
(nist_800_53.py, soc2.py, etc.) are untouched -- they keep their own private
_run_check and are not migrated to this helper, to avoid any risk of
regressing working code during this fix pass.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Tuple


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoffs() -> Tuple[str, str, str]:
    n = datetime.now(timezone.utc)
    return (
        (n - timedelta(days=7)).isoformat(),
        (n - timedelta(days=30)).isoformat(),
        (n - timedelta(days=365)).isoformat(),
    )


# Generic "at least one matching document exists" checks for check_types that
# are unique to a single new framework and have no established multi-signal
# precedent elsewhere in this file family. check_type -> (collection, filter).
_PRESENCE_CHECKS: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "documents_exist":                ("compliance_policies", {}),
    "contracts_signed":               ("vendors", {"contract_signed": True}),
    "assessments_performed":          ("cissp_assessments", {"status": "completed"}),
    "tests_performed":                ("dr_runbooks", {}),
    "kms_configured":                 ("encryption_keys", {}),
    "crypto_module":                  ("encryption_keys", {}),
    "fips_crypto":                    ("encryption_keys", {"fips_validated": True}),
    "inventory":                      ("assets", {}),
    "data_classification":            ("data_classifications", {}),
    "privacy_policy":                 ("compliance_policies", {"category": "privacy"}),
    "media_sanitization":             ("media_sanitization_logs", {}),
    "disposal_verified":              ("media_sanitization_logs", {}),
    "consent_records":                ("consents", {}),
    "consent_withdrawal":             ("consents", {"withdrawn": True}),
    "network_segmentation":           ("network_segments", {}),
    "vlan_segmentation":              ("network_segments", {}),
    "ddos_protection":                ("network_topology", {"ddos_protection": True}),
    "cctv_present":                   ("physical_security_devices", {}),
    "physical_access_control":        ("physical_security_devices", {}),
    "physical_access_monitoring":     ("physical_security_devices", {}),
    "physical_access_audit":          ("physical_access_logs", {}),
    "device_auth":                    ("devices", {"certificate_id": {"$exists": True}}),
    "logs_shipped":                   ("siem_logs", {}),
    "security_alerts":                ("security_alerts", {}),
    "incident_monitoring":            ("security_alerts", {}),
    "alert_configured":               ("security_alerts", {}),
    "supplier_monitoring":            ("vendors", {"last_reviewed": {"$exists": True}}),
    "system_security_plan":           ("compliance_policies", {"category": "system_security_plan"}),
    "sysdoc_present":                 ("compliance_policies", {}),
    "config_plan":                    ("compliance_policies", {"category": "configuration_management"}),
    "plan_of_action":                 ("compliance_policies", {"category": "poam"}),
    "backup_present":                 ("backups", {}),
    "communications_redundancy":      ("network_topology", {"redundant": True}),
    "storage_capacity":               ("agent_metrics", {}),
    "maintenance_tools":              ("playbooks", {"category": "maintenance"}),
    "ir_resources":                   ("playbooks", {}),
    "mobile_device_policy":           ("compliance_policies", {"category": "mobile_device"}),
    "third_party_access":             ("vendors", {}),
    "remote_access":                  ("compliance_policies", {"category": "remote_access"}),
    "remote_maintenance":             ("compliance_policies", {"category": "remote_maintenance"}),
    "maintenance_personnel":          ("employees", {"maintenance_authorized": True}),
    "session_lock":                   ("compliance_policies", {"category": "session_lock"}),
    "session_authenticity":           ("compliance_policies", {"category": "session_authenticity"}),
    "lockout_policy":                 ("compliance_policies", {"category": "lockout_policy"}),
    "password_policy":                ("compliance_policies", {"category": "password_policy"}),
    "ntp_configured":                 ("compliance_policies", {"category": "ntp"}),
    "dns_security":                   ("compliance_policies", {"category": "dns_security"}),
    "spam_protection":                ("edr_agents", {}),
    "wireless_restricted":            ("compliance_policies", {"category": "wireless"}),
    "mobile_code":                    ("compliance_policies", {"category": "mobile_code"}),
    "memory_protection":              ("security_baselines", {"category": "memory_protection"}),
    "process_isolation":              ("security_baselines", {"category": "process_isolation"}),
    "shared_resource_protection":     ("security_baselines", {"category": "shared_resource"}),
    "least_functionality":            ("security_baselines", {}),
    "application_partitioning":       ("security_baselines", {"category": "app_partitioning"}),
    "internal_system_connections":    ("network_topology", {}),
    "system_interconnections":        ("network_topology", {}),
    "collaborative_computing":        ("compliance_policies", {"category": "collaborative_computing"}),
    "permitted_actions":              ("compliance_policies", {"category": "permitted_actions"}),
    "information_handling":           ("compliance_policies", {"category": "information_handling"}),
    "media_access":                   ("media_sanitization_logs", {}),
    "media_labeling":                 ("data_classifications", {}),
    "media_storage":                  ("compliance_policies", {"category": "media_storage"}),
    "media_transport":                ("compliance_policies", {"category": "media_transport"}),
    "media_usage":                    ("compliance_policies", {"category": "media_usage"}),
    "termination_procedures":         ("compliance_policies", {"category": "termination"}),
    "transfer_procedures":            ("compliance_policies", {"category": "transfer"}),
    "user_installed_software":        ("agents", {"restrict_user_installs": True}),
    "software_usage":                 ("compliance_policies", {"category": "software_usage"}),
    "identifier_mgmt":                ("users", {}),
    "concurrent_sessions":            ("compliance_policies", {"category": "concurrent_sessions"}),
    "banner_present":                 ("compliance_policies", {"category": "banner"}),
    "feedback_disabled":              ("compliance_policies", {"category": "auth_feedback"}),
    "error_handling":                 ("compliance_policies", {"category": "error_handling"}),
    "categorization":                 ("assets", {"risk_category": {"$exists": True}}),
    "impact_analysis":                ("risks", {}),
    "allocation_of_resources":        ("compliance_policies", {"category": "resource_allocation"}),
    "acquisition_procurement":        ("vendors", {}),
    "system_development_lifecycle":   ("compliance_policies", {"category": "sdlc"}),
    "system_recovery":                ("dr_runbooks", {}),
    "scheduled_maintenance":          ("compliance_policies", {"category": "maintenance"}),
    "security_function_verification": ("agent_vulnerability_scans", {}),
    "audit_generation":               ("audit_logs", {}),
    "audit_log_content":              ("audit_logs", {}),
    "audit_protection":               ("audit_logs", {}),
    "audit_reduction":                ("audit_logs", {}),
    "audit_review":                   ("audit_logs", {}),
    "access_restrictions_for_change": ("audit_logs", {"action": {"$regex": "change|update|modify", "$options": "i"}}),
    "configuration_settings":         ("security_baselines", {}),
    # New check_types introduced by WR-02 (fixing check_type/title mismatches):
    "internal_audit_evidence":        ("cissp_assessments", {"status": "completed"}),
    "pii_disclosure_controlled":      ("data_classifications", {"category": "PII", "access_restricted": True}),
}


async def run_check(db, ctrl: Dict[str, Any]) -> Tuple[str, str]:
    """Shared _run_check body -- see module docstring."""
    check_type = ctrl.get("check_type", "count_gt_zero")
    cutoff_7d, cutoff_30d, cutoff_1y = _cutoffs()

    try:
        if check_type == "count_gt_zero":
            coll = ctrl.get("check_collection", "")
            count = await db[coll].count_documents({})
            return ("pass" if count > 0 else "fail"), f"{count} records found"

        if check_type == "policies_present":
            count = await db.compliance_policies.count_documents({})
            active = await db.compliance_policies.count_documents({"status": "active"})
            if count > 0:
                return "pass", f"{count} compliance policies ({active} active)"
            return "fail", "No compliance policies defined"

        if check_type == "training_present":
            completions = await db.training_completions.count_documents({})
            recent = await db.training_completions.count_documents({"completed_at": {"$gte": cutoff_30d}})
            if completions > 0:
                return "pass", f"{completions} training completions ({recent} in last 30 days)"
            return "fail", "No security training records found"

        if check_type in ("mfa_coverage", "mfa_configured"):
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

        if check_type in ("rbac_configured", "access_control_system", "least_privilege"):
            roles = await db.roles.count_documents({})
            assigned = await db.users.count_documents({"role": {"$exists": True, "$ne": None}})
            if roles > 0 and assigned > 0:
                return "pass", f"{roles} RBAC roles; {assigned} users assigned"
            if roles > 0:
                return "partial", f"{roles} roles defined but no users assigned"
            return "fail", "No RBAC configuration"

        if check_type == "separation_of_duties":
            roles = await db.roles.count_documents({})
            distinct_roles = [r for r in await db.users.distinct("role") if r]
            if roles >= 2 and len(distinct_roles) >= 2:
                return "pass", f"{roles} roles defined with {len(distinct_roles)} distinct role assignments"
            if roles > 0:
                return "partial", f"{roles} roles defined but insufficient separation evidenced"
            return "fail", "No role separation configured"

        if check_type == "audit_log_volume":
            total = await db.audit_logs.count_documents({})
            recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_7d}})
            if recent > 50:
                return "pass", f"{recent} audit entries in last 7 days ({total} total)"
            if recent > 0:
                return "partial", f"Low audit volume: {recent} entries in 7 days"
            return "fail", "No recent audit log activity"

        if check_type in ("security_events_monitored", "continuous_monitoring"):
            events = await db.security_events.count_documents({"timestamp": {"$gte": cutoff_7d}})
            alerts = await db.security_alerts.count_documents({"created_at": {"$gte": cutoff_7d}})
            if events > 0 or alerts > 0:
                return "pass", f"{events} security events + {alerts} alerts in last 7 days"
            return "fail", "No security events or alerts in last 7 days"

        if check_type in ("change_monitoring", "change_control"):
            recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_30d}})
            changes = await db.audit_logs.count_documents({
                "timestamp": {"$gte": cutoff_30d},
                "action": {"$regex": "update|change|modify|delete|create", "$options": "i"},
            })
            if recent > 0:
                return "pass", f"{changes} change events in audit logs (30-day total: {recent})"
            return "fail", "No audit log evidence of change monitoring"

        if check_type in ("playbooks_present", "incident_handling"):
            pb = await db.playbooks.count_documents({})
            incidents = await db.incidents.count_documents({})
            if pb > 0:
                return "pass", f"{pb} IR playbooks; {incidents} incidents tracked"
            return "fail", "No incident response playbooks defined"

        if check_type == "incident_reporting":
            reported = await db.incidents.count_documents({"reported": True})
            total = await db.incidents.count_documents({})
            if reported > 0:
                return "pass", f"{reported}/{total} incidents have reporting records"
            if total > 0:
                return "partial", f"{total} incidents tracked but none marked as reported"
            return "fail", "No incident reporting evidence"

        if check_type in ("vuln_scan_recent", "vuln_scanner"):
            agent_scans = await db.agent_vulnerability_scans.count_documents({"scanned_at": {"$gte": cutoff_30d}})
            formal_scans = await db.vulnerability_scans.count_documents({"created_at": {"$gte": cutoff_30d}})
            total = max(agent_scans, formal_scans)
            if total > 0:
                return "pass", f"{total} vulnerability scans in last 30 days"
            return "fail", "No vulnerability scans in last 30 days"

        if check_type in ("pentest_or_vuln_scan", "pen_testing"):
            pentest = await db.pentest_results.count_documents({"created_at": {"$gte": cutoff_1y}})
            vuln_scan = await db.vulnerability_scans.count_documents({"created_at": {"$gte": cutoff_30d}})
            if pentest > 0:
                return "pass", f"{pentest} penetration tests in last 12 months"
            if vuln_scan > 0:
                return "partial", f"No formal pentest; {vuln_scan} vulnerability scans in 30 days"
            return "fail", "No penetration test or recent vulnerability scans"

        if check_type in ("backup_recent", "backup_completed"):
            count = await db.backups.count_documents({"created_at": {"$gte": cutoff_30d}})
            total = await db.backups.count_documents({})
            if count > 0:
                return "pass", f"{count} backups in last 30 days ({total} total)"
            return "fail", "No backups in last 30 days"

        if check_type == "backup_dr":
            dr_runbooks = await db.dr_runbooks.count_documents({})
            recent_backups = await db.backups.count_documents({"created_at": {"$gte": cutoff_30d}})
            if dr_runbooks > 0:
                return "pass", f"{dr_runbooks} DR runbooks + {recent_backups} recent backups"
            if recent_backups > 0:
                return "partial", f"No DR runbooks; {recent_backups} recent backups present"
            return "fail", "No contingency plans or disaster recovery procedures"

        if check_type == "risk_assessment_completed":
            risks = await db.risks.count_documents({})
            if risks > 0:
                return "pass", f"{risks} risk assessment records"
            return "fail", "No risk assessment records"

        if check_type == "background_checks":
            checked = await db.employees.count_documents({"background_check_completed": True})
            total = await db.employees.count_documents({})
            if checked > 0:
                return "pass", f"{checked}/{total} employees have completed background checks"
            return "fail", "No personnel background check records"

        if check_type in ("tls_enforced", "tls_enabled"):
            tls_doc = await db.network_topology.find_one({"tls_enforced": True})
            if tls_doc:
                count = await db.network_topology.count_documents({"tls_enforced": True})
                return "pass", f"{count} network devices have TLS enforcement documented"
            tls_certs = await db.tls_certificates.count_documents({})
            if tls_certs > 0:
                return "partial", f"{tls_certs} TLS certs present but no per-device enforcement flag"
            return "fail", "No TLS enforcement documentation found"

        if check_type == "disk_encrypted":
            enc = await db.assets.count_documents({"encrypted": True})
            total = await db.assets.count_documents({})
            if enc > 0:
                return "pass", f"{enc}/{total} assets have disk encryption enabled"
            return "fail", "No assets with disk encryption recorded"

        if check_type == "fw_blocked":
            fw = await db.network_topology.count_documents({"firewall_rules": {"$exists": True, "$ne": []}})
            blocked = await db.security_alerts.count_documents({"action": "blocked", "created_at": {"$gte": cutoff_30d}})
            if fw > 0 or blocked > 0:
                return "pass", f"{fw} network devices with firewall rules; {blocked} blocked events in 30 days"
            return "fail", "No firewall rules or blocked-traffic evidence found"

        if check_type == "ids_ips_enabled":
            events = await db.security_alerts.count_documents({"created_at": {"$gte": cutoff_7d}})
            if events > 0:
                return "pass", f"{events} IDS/IPS alerts in last 7 days"
            return "fail", "No IDS/IPS alert activity in last 7 days"

        if check_type == "malware_protection":
            agents = await db.agents.count_documents({})
            edr = await db.edr_agents.count_documents({})
            if agents == 0:
                return "fail", "No agents registered"
            pct = round(edr / agents * 100) if agents else 0
            if pct >= 80:
                return "pass", f"Anti-malware on {pct}% of endpoints ({edr}/{agents})"
            if pct >= 50:
                return "partial", f"Anti-malware on {pct}% of endpoints"
            return "fail", f"Anti-malware coverage insufficient: {pct}%"

        if check_type == "patch_management":
            recent = await db.agent_vulnerability_scans.count_documents({"scanned_at": {"$gte": cutoff_30d}})
            patched = await db.agents.count_documents({"hardening_applied": True})
            if recent > 0 or patched > 0:
                return "pass", f"{recent} recent vuln scans; {patched} agents show hardening/patches applied"
            return "fail", "No patch management evidence found"

        if check_type == "supplier_assessment":
            vendors = await db.vendors.count_documents({})
            assessed = await db.vendors.count_documents({"last_reviewed": {"$exists": True}})
            if assessed > 0:
                return "pass", f"{assessed}/{vendors} vendors have documented assessments"
            if vendors > 0:
                return "partial", f"{vendors} vendors tracked but none show assessment records"
            return "fail", "No vendor/supplier assessment records"

        if check_type == "supplier_contracts":
            contracts = await db.vendors.count_documents({"contract_signed": True})
            vendors = await db.vendors.count_documents({})
            if contracts > 0:
                return "pass", f"{contracts}/{vendors} vendors have signed contracts on file"
            return "fail", "No vendor contracts on record"

        if check_type == "baseline_config":
            count = await db.security_baselines.count_documents({})
            if count > 0:
                return "pass", f"{count} security baselines defined"
            return "fail", "No hardening/security baselines defined"

        if check_type == "log_retention":
            oldest = await db.audit_logs.count_documents({"timestamp": {"$lte": cutoff_1y}})
            total = await db.audit_logs.count_documents({})
            if total > 0:
                return "pass", f"{total} audit log entries retained ({oldest} older than 1 year)"
            return "fail", "No audit log retention evidence"

        if check_type == "input_validation":
            sast = await db.sast_findings.count_documents({})
            dast = await db.dast_scans.count_documents({"created_at": {"$gte": cutoff_30d}})
            if sast > 0 or dast > 0:
                return "pass", f"{sast} SAST findings + {dast} DAST scans in 30 days"
            return "fail", "No SAST/DAST evidence of input validation testing"

        if check_type == "integrity_monitoring":
            fim = await db.fim_events.count_documents({"timestamp": {"$gte": cutoff_7d}})
            if fim > 0:
                return "pass", f"{fim} FIM/integrity events in last 7 days"
            fim_agents = await db.agents.count_documents({"meta.real_time_fim.watcher_running": True})
            if fim_agents > 0:
                return "pass", f"{fim_agents} agents monitoring integrity (FIM active)"
            return "fail", "No file/software integrity monitoring evidence"

        if check_type == "device_compliance":
            compliant = await db.devices.count_documents({"compliant": True})
            total = await db.devices.count_documents({})
            if total == 0:
                return "not_applicable", "No managed devices registered"
            pct = round(compliant / total * 100)
            if pct >= 90:
                return "pass", f"{pct}% of devices compliant ({compliant}/{total})"
            if pct >= 50:
                return "partial", f"{pct}% of devices compliant"
            return "fail", f"Device compliance critically low: {pct}%"

        if check_type == "access_keys_rotated":
            total = await db.api_keys.count_documents({})
            rotated = await db.api_keys.count_documents({"rotated_at": {"$gte": cutoff_1y}})
            if total == 0:
                return "not_applicable", "No API/access keys tracked"
            pct = round(rotated / total * 100)
            if pct >= 90:
                return "pass", f"{pct}% of keys rotated within the last year"
            if pct >= 50:
                return "partial", f"{pct}% of keys rotated within the last year"
            return "fail", f"Only {pct}% of keys rotated within the last year"

        if check_type == "iam_no_wildcards":
            total = await db.iam_policies.count_documents({})
            if total == 0:
                return "not_applicable", "No IAM policies tracked"
            wildcard = await db.iam_policies.count_documents({"$or": [{"actions": "*"}, {"resources": "*"}]})
            if wildcard == 0:
                return "pass", f"0/{total} IAM policies use wildcard actions/resources"
            return "fail", f"{wildcard}/{total} IAM policies use wildcard actions/resources"

        if check_type in _PRESENCE_CHECKS:
            coll, filt = _PRESENCE_CHECKS[check_type]
            count = await db[coll].count_documents(filt)
            if count > 0:
                return "pass", f"{count} matching records in {coll}"
            return "fail", f"No matching records found in {coll}"

    except Exception as exc:
        return "fail", f"Check error: {exc}"

    return "not_applicable", "Unknown check type"
