"""IRAP — Australian Government Information Security."""
FRAMEWORK_ID = "irap"; FRAMEWORK_NAME = "IRAP"; FRAMEWORK_VERSION = "2024"
CONTROLS = [
    {"id":"IRAP-GOV-1","theme":"Governance","check_type":"policies_present","title":"Security governance","description":"Establish security governance framework."},
    {"id":"IRAP-GOV-2","theme":"Governance","check_type":"risk_assessment_completed","title":"Risk management","description":"Implement risk management process."},
    {"id":"IRAP-GOV-3","theme":"Governance","check_type":"training_present","title":"Security awareness","description":"Security awareness program."},
    {"id":"IRAP-GOV-4","theme":"Governance","check_type":"documents_exist","title":"ISMS","description":"Information Security Management System."},
    {"id":"IRAP-AC-1","theme":"Access Control","check_type":"rbac_configured","title":"Access management","description":"User access management."},
    {"id":"IRAP-AC-2","theme":"Access Control","check_type":"mfa_configured","title":"MFA","description":"Multi-factor authentication for privileged access."},
    {"id":"IRAP-AC-3","theme":"Access Control","check_type":"least_privilege","title":"Least privilege","description":"Least privilege principle."},
    {"id":"IRAP-AC-4","theme":"Access Control","check_type":"separation_of_duties","title":"Separation of duties","description":"Segregation of duties."},
    {"id":"IRAP-CRY-1","theme":"Cryptography","check_type":"disk_encrypted","title":"Data at rest encryption","description":"Encrypt sensitive data at rest."},
    {"id":"IRAP-CRY-2","theme":"Cryptography","check_type":"tls_enabled","title":"Data in transit encryption","description":"Encrypt data in transit."},
    {"id":"IRAP-CRY-3","theme":"Cryptography","check_type":"kms_configured","title":"Key management","description":"Cryptographic key management."},
    {"id":"IRAP-PHY-1","theme":"Physical","check_type":"access_control_system","title":"Physical access","description":"Physical access controls."},
    {"id":"IRAP-PHY-2","theme":"Physical","check_type":"cctv_present","title":"Physical monitoring","description":"Physical security monitoring."},
    {"id":"IRAP-NET-1","theme":"Network","check_type":"fw_blocked","title":"Network segmentation","description":"Network segmentation and firewalls."},
    {"id":"IRAP-NET-2","theme":"Network","check_type":"ids_ips_enabled","title":"IDS/IPS","description":"Intrusion detection and prevention."},
    {"id":"IRAP-NET-3","theme":"Network","check_type":"vlan_segmentation","title":"Network access control","description":"Network access controls."},
    {"id":"IRAP-AUD-1","theme":"Audit","check_type":"audit_log_volume","title":"Audit logging","description":"Audit logging enabled."},
    {"id":"IRAP-AUD-2","theme":"Audit","check_type":"log_retention","title":"Log retention","description":"Audit log retention."},
    {"id":"IRAP-AUD-3","theme":"Audit","check_type":"logs_shipped","title":"SIEM integration","description":"Send logs to SIEM."},
    {"id":"IRAP-PER-1","theme":"Personnel","check_type":"background_checks","title":"Screening","description":"Personnel security screening."},
    {"id":"IRAP-PER-2","theme":"Personnel","check_type":"training_present","title":"Security training","description":"Security training."},
    {"id":"IRAP-IR-1","theme":"Incident Response","check_type":"incident_handling","title":"Incident management","description":"Incident response capability."},
    {"id":"IRAP-IR-2","theme":"Incident Response","check_type":"incident_reporting","title":"Incident reporting","description":"Incident notification."},
    {"id":"IRAP-BCP-1","theme":"Continuity","check_type":"backup_dr","title":"Business continuity","description":"BCP and DR plan."},
    {"id":"IRAP-BCP-2","theme":"Continuity","check_type":"tests_performed","title":"BCP testing","description":"Regular BCP testing."},
    {"id":"IRAP-VUL-1","theme":"Vulnerability","check_type":"vuln_scanner","title":"Vulnerability scanning","description":"Regular vulnerability scanning."},
    {"id":"IRAP-VUL-2","theme":"Vulnerability","check_type":"pen_testing","title":"Penetration testing","description":"Annual penetration testing."},
]


from ._common_checks import run_check as _run_check, now as _now


async def evaluate_controls(db):
    """Run all checks for this framework's controls. See _common_checks.py."""
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({**ctrl, "status": status, "evidence": evidence, "evaluated_at": _now()})
    return results
