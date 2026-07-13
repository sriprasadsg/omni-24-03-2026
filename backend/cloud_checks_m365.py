from typing import List, Dict, Any

M365_CHECKS = [
    {
        "id": "m365-admin-mfa-001",
        "name": "MFA enforced for admin roles",
        "description": "Ensure multi-factor authentication is enforced for all administrative roles.",
        "provider": "microsoft365",
        "service": "identity",
        "severity": "critical",
        "frameworks": ["NIST-IA-2", "PCI-DSS-8.3.1"],
        "remediation": "Configure Azure AD Conditional Access policies to enforce MFA for admin roles."
    },
    {
        "id": "m365-ca-coverage-002",
        "name": "Conditional Access covers all users",
        "description": "Verify Conditional Access policies are configured and cover all users for relevant scenarios.",
        "provider": "microsoft365",
        "service": "identity",
        "severity": "high",
        "frameworks": ["NIST-AC-2", "SOC2-CC6.1"],
        "remediation": "Review and expand Azure AD Conditional Access policies to ensure comprehensive user coverage."
    },
    {
        "id": "m365-mailbox-audit-003",
        "name": "Mailbox audit logging enabled",
        "description": "Ensure mailbox audit logging is enabled for all mailboxes to track access and actions.",
        "provider": "microsoft365",
        "service": "exchange",
        "severity": "medium",
        "frameworks": ["NIST-AU-12", "ISO27001-A.12.4.1"],
        "remediation": "Enable mailbox audit logging for all user and admin mailboxes in Exchange Online."
    },
    {
        "id": "m365-ext-sharing-004",
        "name": "External sharing restricted",
        "description": "Restrict external sharing capabilities in SharePoint and OneDrive to authorized domains or users.",
        "provider": "microsoft365",
        "service": "sharepoint",
        "severity": "high",
        "frameworks": ["NIST-AC-4", "GDPR-Article25"],
        "remediation": "Configure SharePoint Online and OneDrive external sharing settings to limit sharing to specific domains or disable it."
    },
    {
        "id": "m365-legacy-auth-005",
        "name": "Legacy authentication blocked",
        "description": "Block legacy authentication protocols to prevent credential theft attacks.",
        "provider": "microsoft365",
        "service": "identity",
        "severity": "critical",
        "frameworks": ["NIST-IA-2", "PCI-DSS-8.2.1"],
        "remediation": "Implement Conditional Access policies to block legacy authentication for Exchange Online and other services."
    },
    {
        "id": "m365-secure-score-006",
        "name": "Microsoft Secure Score baseline met",
        "description": "Ensure the organization's Microsoft Secure Score meets defined baseline targets.",
        "provider": "microsoft365",
        "service": "security",
        "severity": "medium",
        "frameworks": ["CIS-MS365-1.1", "ISO27001-A.15.2.1"],
        "remediation": "Review Secure Score recommendations and implement necessary security controls to improve score."
    }
]
