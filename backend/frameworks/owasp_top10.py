"""OWASP Top 10 Web Application Security Risks 2021."""
FRAMEWORK_ID = "owasp_top10"; FRAMEWORK_NAME = "OWASP Top 10 2021"; FRAMEWORK_VERSION = "2021"
CONTROLS = [
    {"id":"OWASP-A01","theme":"Broken Access Control","check_type":"rbac_configured","title":"Broken Access Control","description":"Enforce access control on all resources."},
    {"id":"OWASP-A02","theme":"Cryptographic Failures","check_type":"tls_enabled","title":"Cryptographic Failures","description":"Protect data in transit and at rest."},
    {"id":"OWASP-A03","theme":"Injection","check_type":"input_validation","title":"Injection","description":"Sanitize and validate all inputs."},
    {"id":"OWASP-A04","theme":"Insecure Design","check_type":"change_control","title":"Insecure Design","description":"Threat modeling and secure design."},
    {"id":"OWASP-A05","theme":"Security Misconfiguration","check_type":"baseline_config","title":"Security Misconfiguration","description":"Secure default configurations."},
    {"id":"OWASP-A06","theme":"Vulnerable Components","check_type":"patch_management","title":"Vulnerable and Outdated Components","description":"Keep software dependencies updated."},
    {"id":"OWASP-A07","theme":"Auth Failures","check_type":"mfa_configured","title":"Identification and Authentication Failures","description":"Secure authentication mechanisms."},
    {"id":"OWASP-A08","theme":"Integrity Failures","check_type":"integrity_monitoring","title":"Software and Data Integrity Failures","description":"Verify software provenance and integrity."},
    {"id":"OWASP-A09","theme":"Logging Failures","check_type":"audit_log_volume","title":"Security Logging and Monitoring Failures","description":"Log and monitor security events."},
    {"id":"OWASP-A10","theme":"SSRF","check_type":"fw_blocked","title":"Server-Side Request Forgery","description":"Validate and restrict server-side requests."},
]
