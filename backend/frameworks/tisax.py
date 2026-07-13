"""TISAX — Trusted Information Security Assessment Exchange (Automotive)."""
FRAMEWORK_ID = "tisax"; FRAMEWORK_NAME = "TISAX"; FRAMEWORK_VERSION = "2022"
CONTROLS = [
    {"id":"TISAX-1","theme":"Information Security","check_type":"policies_present","title":"ISMS","description":"Information Security Management System."},
    {"id":"TISAX-2","theme":"Information Security","check_type":"risk_assessment_completed","title":"Risk assessment","description":"Regular risk assessments."},
    {"id":"TISAX-3","theme":"Information Security","check_type":"training_present","title":"Security awareness","description":"Staff awareness program."},
    {"id":"TISAX-4","theme":"Access Control","check_type":"rbac_configured","title":"Access management","description":"Identity and access management."},
    {"id":"TISAX-5","theme":"Access Control","check_type":"mfa_configured","title":"Authentication","description":"Strong authentication."},
    {"id":"TISAX-6","theme":"Access Control","check_type":"least_privilege","title":"Least privilege","description":"Least privilege principle."},
    {"id":"TISAX-7","theme":"Cryptography","check_type":"kms_configured","title":"Key management","description":"Cryptographic key management."},
    {"id":"TISAX-8","theme":"Cryptography","check_type":"disk_encrypted","title":"Encryption","description":"Encryption of sensitive data."},
    {"id":"TISAX-9","theme":"Network","check_type":"fw_blocked","title":"Network security","description":"Firewalls and network segmentation."},
    {"id":"TISAX-10","theme":"Network","check_type":"tls_enabled","title":"Secure communications","description":"Secure communication channels."},
    {"id":"TISAX-11","theme":"Physical","check_type":"access_control_system","title":"Physical security","description":"Physical and environmental security."},
    {"id":"TISAX-12","theme":"Physical","check_type":"cctv_present","title":"Physical monitoring","description":"Physical access monitoring."},
    {"id":"TISAX-13","theme":"Incident","check_type":"incident_handling","title":"Incident management","description":"Security incident management."},
    {"id":"TISAX-14","theme":"Incident","check_type":"incident_reporting","title":"Incident reporting","description":"Notify affected parties."},
    {"id":"TISAX-15","theme":"Continuity","check_type":"backup_dr","title":"Business continuity","description":"Business continuity management."},
    {"id":"TISAX-16","theme":"Continuity","check_type":"backup_completed","title":"Backup","description":"Data backup."},
    {"id":"TISAX-17","theme":"Supplier","check_type":"supplier_assessment","title":"Supplier security","description":"Supplier security assessment."},
    {"id":"TISAX-18","theme":"Supplier","check_type":"supplier_contracts","title":"Supplier agreements","description":"Security requirements in supplier agreements."},
    {"id":"TISAX-19","theme":"Prototype","check_type":"access_control_system","title":"Prototype protection","description":"Protection of prototype data."},
    {"id":"TISAX-20","theme":"Prototype","check_type":"data_classification","title":"Data classification","description":"Classify prototype data."},
    {"id":"TISAX-21","theme":"Audit","check_type":"audit_log_volume","title":"Audit logging","description":"Audit logs."},
    {"id":"TISAX-22","theme":"Audit","check_type":"continuous_monitoring","title":"Monitoring","description":"Continuous monitoring."},
    {"id":"TISAX-23","theme":"Compliance","check_type":"assessments_performed","title":"Compliance","description":"Regulatory compliance."},
    {"id":"TISAX-24","theme":"Vulnerability","check_type":"vuln_scanner","title":"Vulnerability management","description":"Vulnerability scanning and patching."},
    {"id":"TISAX-25","theme":"Personnel","check_type":"background_checks","title":"Personnel","description":"Personnel screening."},
    {"id":"TISAX-26","theme":"Data Protection","check_type":"privacy_policy","title":"Data protection","description":"Data protection compliance."},
]


from ._common_checks import run_check as _run_check, now as _now


async def evaluate_controls(db):
    """Run all checks for this framework's controls. See _common_checks.py."""
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({**ctrl, "status": status, "evidence": evidence, "evaluated_at": _now()})
    return results
