"""ENS — Spanish Esquema Nacional de Seguridad."""
FRAMEWORK_ID = "ens"; FRAMEWORK_NAME = "ENS"; FRAMEWORK_VERSION = "RD 3/2010"
CONTROLS = [
    {"id":"ENS-mp1","theme":"Organization","check_type":"policies_present","title":"Organizational security","description":"Security organization defined."},
    {"id":"ENS-mp2","theme":"Organization","check_type":"training_present","title":"Security training","description":"Security awareness program."},
    {"id":"ENS-mp3","theme":"Risk","check_type":"risk_assessment_completed","title":"Risk analysis","description":"Periodic risk analysis."},
    {"id":"ENS-mp4","theme":"Risk","check_type":"pen_testing","title":"Audit","description":"Security audit performed."},
    {"id":"ENS-mp5","theme":"Personnel","check_type":"background_checks","title":"Personnel screening","description":"Screening of personnel."},
    {"id":"ENS-op1","theme":"Operations","check_type":"incident_handling","title":"Incident management","description":"Incident response procedure."},
    {"id":"ENS-op2","theme":"Operations","check_type":"backup_completed","title":"Backup and recovery","description":"Backup and restore procedure."},
    {"id":"ENS-op3","theme":"Operations","check_type":"continuous_monitoring","title":"Continuous monitoring","description":"Ongoing security monitoring."},
    {"id":"ENS-op4","theme":"Operations","check_type":"patch_management","title":"Patch management","description":"Apply security patches."},
    {"id":"ENS-op5","theme":"Operations","check_type":"audit_log_volume","title":"Logging","description":"Security event logging."},
    {"id":"ENS-op6","theme":"Operations","check_type":"logs_shipped","title":"Log retention","description":"Log retention at least 1 year."},
    {"id":"ENS-me1","theme":"Measures","check_type":"access_control_system","title":"Access control","description":"Logical access control."},
    {"id":"ENS-me2","theme":"Measures","check_type":"rbac_configured","title":"Least privilege","description":"Least privilege principle."},
    {"id":"ENS-me3","theme":"Measures","check_type":"mfa_configured","title":"Authentication","description":"Strong authentication."},
    {"id":"ENS-me4","theme":"Measures","check_type":"tls_enabled","title":"Communications security","description":"Encrypted communications."},
    {"id":"ENS-me5","theme":"Measures","check_type":"disk_encrypted","title":"Cryptography","description":"Encryption of data."},
    {"id":"ENS-me6","theme":"Measures","check_type":"malware_protection","title":"Malware protection","description":"Anti-malware deployed."},
    {"id":"ENS-me7","theme":"Measures","check_type":"fw_blocked","title":"Perimeter security","description":"Perimeter firewall."},
    {"id":"ENS-me8","theme":"Measures","check_type":"ids_ips_enabled","title":"Intrusion detection","description":"IDS/IPS deployed."},
    {"id":"ENS-me9","theme":"Measures","check_type":"vuln_scanner","title":"Vulnerability management","description":"Vulnerability scanning."},
    {"id":"ENS-me10","theme":"Measures","check_type":"baseline_config","title":"Secure configuration","description":"Baseline secure configurations."},
    {"id":"ENS-mar1","theme":"Continuity","check_type":"tests_performed","title":"Business continuity","description":"BCP tested."},
]


from ._common_checks import run_check as _run_check, now as _now


async def evaluate_controls(db):
    """Run all checks for this framework's controls. See _common_checks.py."""
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({**ctrl, "status": status, "evidence": evidence, "evaluated_at": _now()})
    return results
