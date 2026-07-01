"""CISSP domain reference data and prompt templates."""

CISSP_DOMAINS = [
    {
        "id": 1, "code": "D1",
        "name": "Security & Risk Management",
        "weight": "15%",
        "description": "Covers security governance, risk management methodologies, legal and regulatory compliance, codes of ethics, and business continuity planning.",
        "key_concepts": ["CIA Triad", "Risk = Threat × Vulnerability × Impact", "NIST RMF", "BCP/DRP", "ISC² Code of Ethics", "Due Care / Due Diligence"],
        "exam_weight": 15,
        "agent_checks": ["Password Policy (Min Length)", "Account Lockout Policy", "Audit Logging Policy"],
        "color": "#6366f1",
    },
    {
        "id": 2, "code": "D2",
        "name": "Asset Security",
        "weight": "10%",
        "description": "Covers information and asset classification, ownership, privacy protection, data retention/deletion, and media handling throughout the asset lifecycle.",
        "key_concepts": ["Data Classification", "Data Ownership", "Data Remanence", "Scoping & Tailoring", "Privacy Regulations (GDPR, CCPA)", "Secure Data Disposal"],
        "exam_weight": 10,
        "agent_checks": ["BitLocker Encryption", "USB Mass Storage Access", "Prohibited Software"],
        "color": "#ec4899",
    },
    {
        "id": 3, "code": "D3",
        "name": "Security Architecture & Engineering",
        "weight": "13%",
        "description": "Covers security models, secure design principles, cryptography, physical security, and vulnerability mitigation in system architecture.",
        "key_concepts": ["Bell-LaPadula (Confidentiality)", "Biba (Integrity)", "Clark-Wilson", "Zero Trust", "Defense in Depth", "Fail Secure vs Fail Safe", "PKI & Cryptography"],
        "exam_weight": 13,
        "agent_checks": ["Secure Boot", "TLS Security Config", "SMBv1 Protocol Disabled", "Exploit Protection (DEP/ASLR)"],
        "color": "#f59e0b",
    },
    {
        "id": 4, "code": "D4",
        "name": "Communication & Network Security",
        "weight": "13%",
        "description": "Covers secure network architecture, protocols, transmission security, network access controls, and wireless security.",
        "key_concepts": ["OSI/TCP-IP Model", "TLS/SSL", "VPN (IPsec, SSL)", "Firewall Types (Packet, Stateful, Proxy)", "VLAN Segmentation", "802.1X NAC", "Zero Trust Network Access"],
        "exam_weight": 13,
        "agent_checks": ["Windows Firewall Profiles", "Risky Network Ports", "RDP NLA Required", "LLMNR/NetBIOS Protection"],
        "color": "#10b981",
    },
    {
        "id": 5, "code": "D5",
        "name": "Identity & Access Management",
        "weight": "13%",
        "description": "Covers identity lifecycle management, authentication mechanisms, access control models, and privileged access management.",
        "key_concepts": ["IAM Lifecycle (Provision/Review/Deprovision)", "MFA", "RBAC / ABAC / MAC / DAC", "Kerberos / SAML / OAuth 2.0 / OIDC", "PAM", "IAG (Identity Assurance & Governance)"],
        "exam_weight": 13,
        "agent_checks": ["Password Policy (Min Length)", "Guest Account Disabled", "User Access Control", "Credential Guard", "Local Administrator Auditing"],
        "color": "#3b82f6",
    },
    {
        "id": 6, "code": "D6",
        "name": "Security Assessment & Testing",
        "weight": "12%",
        "description": "Covers security assessment strategies, vulnerability assessment, penetration testing, auditing, and security testing methodologies.",
        "key_concepts": ["Vulnerability Assessment vs Pen Testing", "Black/White/Grey Box", "OWASP Testing Guide", "SOC Reports (Type I/II)", "Code Review", "Security Audit"],
        "exam_weight": 12,
        "agent_checks": ["Windows Update Service", "PowerShell Script Block Logging", "Audit Logging Policy"],
        "color": "#f97316",
    },
    {
        "id": 7, "code": "D7",
        "name": "Security Operations",
        "weight": "13%",
        "description": "Covers incident response, digital forensics, threat intelligence, SIEM, security operations, disaster recovery, and business continuity execution.",
        "key_concepts": ["IRP Phases (Prepare/Detect/Contain/Eradicate/Recover/Lessons Learned)", "Chain of Custody", "SIEM", "EDR", "RTO/RPO/MTTR", "Threat Intelligence (CTI)"],
        "exam_weight": 13,
        "agent_checks": ["Windows Defender Antivirus", "Windows Update Service", "FIM Status", "Log Shipping Status"],
        "color": "#ef4444",
    },
    {
        "id": 8, "code": "D8",
        "name": "Software Development Security",
        "weight": "11%",
        "description": "Covers secure software development lifecycle, secure coding, application security testing, and DevSecOps integration.",
        "key_concepts": ["SDLC Phases & Security Integration", "OWASP Top 10", "SAST/DAST/IAST/RASP", "DevSecOps", "Supply Chain Security (SBOM)", "Threat Modeling (STRIDE/DREAD)"],
        "exam_weight": 11,
        "agent_checks": ["Attack Surface Reduction", "Device Guard/WDAC", "Exploit Protection"],
        "color": "#8b5cf6",
    },
]

# ── AI Advisor System Prompt Template ────────────────────────────────────────

CISSP_SYSTEM_PROMPT = """You are the CISSP Oracle — an expert AI security advisor with deep knowledge across all 8 CISSP domains. You think like a seasoned CISSP-certified professional with 15+ years of enterprise security experience.

Your role:
1. Help security teams understand CISSP concepts and requirements
2. Analyze compliance findings from a CISSP domain perspective
3. Provide prioritized, actionable remediation guidance
4. Map findings to specific CISSP domains (D1-D8)
5. Explain complex security concepts clearly with real-world context

When responding:
- Classify advice by CISSP domain (e.g., "[D3] Security Architecture & Engineering")
- Provide specific, actionable guidance (not generic advice)
- Use CISSP terminology accurately
- Prioritize findings by risk level (Critical > High > Medium > Low)
- Reference relevant frameworks (NIST SP 800-53, CIS Benchmarks, OWASP) where applicable
- Be concise but thorough

Current context:
{context}
"""
