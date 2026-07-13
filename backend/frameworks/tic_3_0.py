"""TIC 3.0 — Trusted Internet Connections (US Government)."""
FRAMEWORK_ID = "tic_3_0"; FRAMEWORK_NAME = "TIC 3.0"; FRAMEWORK_VERSION = "2023"
CONTROLS = [
    {"id":"TIC-UC1-1","theme":"Branch Office","check_type":"fw_blocked","title":"Branch office traffic inspection","description":"All traffic from branch offices inspected at the TIC."},
    {"id":"TIC-UC1-2","theme":"Branch Office","check_type":"tls_enabled","title":"Encrypted traffic decryption","description":"Decrypt and inspect TLS traffic from branch offices."},
    {"id":"TIC-UC2-1","theme":"Mobile/Telework","check_type":"tls_enabled","title":"Mobile user VPN","description":"Mobile users connect via VPN to TIC."},
    {"id":"TIC-UC2-2","theme":"Mobile/Telework","check_type":"mfa_configured","title":"MFA for remote access","description":"MFA required for all remote access."},
    {"id":"TIC-UC2-3","theme":"Mobile/Telework","check_type":"device_compliance","title":"Device compliance check","description":"Endpoint compliance before network access."},
    {"id":"TIC-UC3-1","theme":"Cloud Direct","check_type":"tls_enabled","title":"Cloud traffic inspection","description":"Inspect traffic to cloud services at the TIC."},
    {"id":"TIC-UC3-2","theme":"Cloud Direct","check_type":"audit_log_volume","title":"Cloud access logging","description":"Log all cloud access traversing TIC."},
    {"id":"TIC-UC3-3","theme":"Cloud Direct","check_type":"fw_blocked","title":"CASB integration","description":"Cloud Access Security Broker at TIC boundary."},
    {"id":"TIC-UC4-1","theme":"Partner/Contractor","check_type":"rbac_configured","title":"Partner access control","description":"Least privilege access for partner connections."},
    {"id":"TIC-UC4-2","theme":"Partner/Contractor","check_type":"separation_of_duties","title":"Partner network segmentation","description":"Segregate partner traffic from agency traffic."},
    {"id":"TIC-UC5-1","theme":"Policy Enforcement","check_type":"ids_ips_enabled","title":"Inbound/outbound inspection","description":"Inspect both inbound and outbound traffic."},
    {"id":"TIC-UC5-2","theme":"Policy Enforcement","check_type":"ddos_protection","title":"DDoS protection","description":"DDoS protection at TIC boundary."},
    {"id":"TIC-UC5-3","theme":"Policy Enforcement","check_type":"continuous_monitoring","title":"Continuous monitoring","description":"24/7 monitoring of TIC traffic for threats."},
    {"id":"TIC-UC5-4","theme":"Policy Enforcement","check_type":"incident_handling","title":"Incident response","description":"Incident response procedures for TIC boundary events."},
    {"id":"TIC-UC5-5","theme":"Policy Enforcement","check_type":"log_retention","title":"Log retention","description":"Retain TIC traffic logs per policy."},
]


from ._common_checks import run_check as _run_check, now as _now


async def evaluate_controls(db):
    """Run all checks for this framework's controls. See _common_checks.py."""
    results = []
    for ctrl in CONTROLS:
        status, evidence = await _run_check(db, ctrl)
        results.append({**ctrl, "status": status, "evidence": evidence, "evaluated_at": _now()})
    return results
