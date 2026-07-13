"""FFIEC — Federal Financial Institutions Examination Council."""
FRAMEWORK_ID = "ffiec"; FRAMEWORK_NAME = "FFIEC"; FRAMEWORK_VERSION = "2023"
CONTROLS = [
    {"id":"FFIEC-IT-1","theme":"IT Management","check_type":"policies_present","title":"IT governance","description":"Board IT governance oversight."},
    {"id":"FFIEC-IT-2","theme":"IT Management","check_type":"risk_assessment_completed","title":"Risk assessment","description":"IT risk assessment."},
    {"id":"FFIEC-IT-3","theme":"IT Management","check_type":"documents_exist","title":"Strategic planning","description":"IT strategic alignment."},
    {"id":"FFIEC-INFOSEC-1","theme":"InfoSec","check_type":"rbac_configured","title":"Access controls","description":"Information access controls."},
    {"id":"FFIEC-INFOSEC-2","theme":"InfoSec","check_type":"mfa_configured","title":"MFA","description":"MFA for critical systems."},
    {"id":"FFIEC-INFOSEC-3","theme":"InfoSec","check_type":"disk_encrypted","title":"Data encryption","description":"Encrypt sensitive data."},
    {"id":"FFIEC-INFOSEC-4","theme":"InfoSec","check_type":"tls_enabled","title":"Transmission security","description":"Secure data transmission."},
    {"id":"FFIEC-INFOSEC-5","theme":"InfoSec","check_type":"malware_protection","title":"Malware defense","description":"Anti-malware controls."},
    {"id":"FFIEC-INFOSEC-6","theme":"InfoSec","check_type":"patch_management","title":"Patch management","description":"Vulnerability and patch management."},
    {"id":"FFIEC-BCP-1","theme":"BCP","check_type":"backup_dr","title":"Business continuity","description":"BCP for IT systems."},
    {"id":"FFIEC-BCP-2","theme":"BCP","check_type":"tests_performed","title":"BCP testing","description":"Annual BCP testing."},
    {"id":"FFIEC-BCP-3","theme":"BCP","check_type":"backup_completed","title":"Backup","description":"Data backup procedures."},
    {"id":"FFIEC-SEC-1","theme":"Security","check_type":"incident_handling","title":"Incident response","description":"Incident response plan."},
    {"id":"FFIEC-SEC-2","theme":"Security","check_type":"continuous_monitoring","title":"Continuous monitoring","description":"24/7 security monitoring."},
    {"id":"FFIEC-SEC-3","theme":"Security","check_type":"vuln_scanner","title":"Vulnerability scanning","description":"Regular vulnerability scans."},
    {"id":"FFIEC-SEC-4","theme":"Security","check_type":"pen_testing","title":"Penetration testing","description":"Annual penetration tests."},
    {"id":"FFIEC-SEC-5","theme":"Security","check_type":"training_present","title":"Security awareness","description":"Staff awareness training."},
    {"id":"FFIEC-AUD-1","theme":"Audit","check_type":"audit_log_volume","title":"Audit logging","description":"Audit trail."},
    {"id":"FFIEC-AUD-2","theme":"Audit","check_type":"log_retention","title":"Log retention","description":"Log retention."},
    {"id":"FFIEC-THIRD-1","theme":"Third Party","check_type":"supplier_assessment","title":"Vendor management","description":"Third-party risk management."},
    {"id":"FFIEC-THIRD-2","theme":"Third Party","check_type":"supplier_contracts","title":"Vendor due diligence","description":"Due diligence for vendors."},
    {"id":"FFIEC-NET-1","theme":"Network","check_type":"fw_blocked","title":"Network security","description":"Network segmentation and firewalls."},
    {"id":"FFIEC-NET-2","theme":"Network","check_type":"ids_ips_enabled","title":"IDS","description":"Intrusion detection."},
    {"id":"FFIEC-APP-1","theme":"Applications","check_type":"input_validation","title":"App security","description":"Application security controls."},
    {"id":"FFIEC-APP-2","theme":"Applications","check_type":"change_control","title":"Change management","description":"Change management for apps."},
]


from ._common_checks import run_check as _run_check, now as _now


async def evaluate_controls(db):
    """Run all checks for this framework's controls. See _common_checks.py."""
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({**ctrl, "status": status, "evidence": evidence, "evaluated_at": _now()})
    return results
