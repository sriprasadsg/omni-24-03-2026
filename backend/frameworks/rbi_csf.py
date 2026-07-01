"""RBI CSF — Reserve Bank of India Cyber Security Framework."""
FRAMEWORK_ID = "rbi_csf"; FRAMEWORK_NAME = "RBI CSF"; FRAMEWORK_VERSION = "2022"
CONTROLS = [
    {"id":"RBI-GOV-1","theme":"Governance","check_type":"policies_present","title":"Board approved cyber security policy","description":"Board-approved cyber security policy in place."},
    {"id":"RBI-GOV-2","theme":"Governance","check_type":"documents_exist","title":"Cyber security committee","description":"Cyber security committee with senior management."},
    {"id":"RBI-RISK-1","theme":"Risk","check_type":"risk_assessment_completed","title":"Cyber risk assessment","description":"Regular cyber risk assessments."},
    {"id":"RBI-RISK-2","theme":"Risk","check_type":"pen_testing","title":"Penetration testing","description":"Annual VAPT by CERT-In empaneled auditors."},
    {"id":"RBI-PREV-1","theme":"Preventive","check_type":"fw_blocked","title":"Network segmentation","description":"Segregate network into zones."},
    {"id":"RBI-PREV-2","theme":"Preventive","check_type":"malware_protection","title":"Malware protection","description":"Anti-malware on all systems."},
    {"id":"RBI-PREV-3","theme":"Preventive","check_type":"patch_management","title":"Patch management","description":"Vulnerability management and patch process."},
    {"id":"RBI-PREV-4","theme":"Preventive","check_type":"rbac_configured","title":"Access controls","description":"Strong access controls and least privilege."},
    {"id":"RBI-PREV-5","theme":"Preventive","check_type":"disk_encrypted","title":"Data encryption","description":"Encrypt data at rest and in transit."},
    {"id":"RBI-DET-1","theme":"Detection","check_type":"ids_ips_enabled","title":"IDS/IPS","description":"Intrusion detection and prevention."},
    {"id":"RBI-DET-2","theme":"Detection","check_type":"audit_log_volume","title":"Log monitoring","description":"24x7 security monitoring and log analysis."},
    {"id":"RBI-DET-3","theme":"Detection","check_type":"continuous_monitoring","title":"SOC","description":"Security Operations Center."},
    {"id":"RBI-RESP-1","theme":"Response","check_type":"incident_handling","title":"Incident response","description":"Cyber incident response plan tested annually."},
    {"id":"RBI-RESP-2","theme":"Response","check_type":"incident_reporting","title":"Incident reporting to RBI","description":"Report incidents to RBI within timelines."},
    {"id":"RBI-REC-1","theme":"Recovery","check_type":"backup_dr","title":"BCP and DR","description":"Business continuity and DR plan tested annually."},
    {"id":"RBI-REC-2","theme":"Recovery","check_type":"backup_completed","title":"Data backups","description":"Regular offline backups of critical data."},
    {"id":"RBI-AUD-1","theme":"Audit","check_type":"assessments_performed","title":"IT audit","description":"Annual IT audit by independent auditor."},
    {"id":"RBI-AUD-2","theme":"Audit","check_type":"training_present","title":"Cyber security training","description":"Staff cybersecurity awareness training."},
    {"id":"RBI-3RD-1","theme":"Third Party","check_type":"supplier_assessment","title":"Third-party risk","description":"Vendor security assessment for critical vendors."},
    {"id":"RBI-3RD-2","theme":"Third Party","check_type":"contracts_signed","title":"Vendor due diligence","description":"Contractual security requirements for third parties."},
]
