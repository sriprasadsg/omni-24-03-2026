from typing import List, Dict, Any

M365_CHECKS: List[Dict[str, Any]] = [
    {"id": "m365-01", "name": "MFA Enforcement", "description": "Ensure MFA is enforced for all admins", "provider": "microsoft365", "service": "Identity", "severity": "high", "frameworks": ["CIS"], "remediation": "Enable per-user MFA"},
    {"id": "m365-02", "name": "External Sharing", "description": "Restrict external sharing", "provider": "microsoft365", "service": "SharePoint", "severity": "medium", "frameworks": ["HIPAA"], "remediation": "Update sharing settings"},
]
