"""
CISSP Framework Seeder
======================
Seeds the CISSP (Certified Information Systems Security Professional) compliance
framework into MongoDB with all 8 official domains and control objectives.

Run this script once, or re-run to update.
"""

from pymongo import MongoClient
from datetime import datetime

db = MongoClient("mongodb://localhost:27017")["omni_platform"]

CISSP_FRAMEWORK = {
    "id": "cissp",
    "name": "CISSP",
    "description": "Certified Information Systems Security Professional — 8 Domain Security Framework (ISC)²",
    "version": "2024",
    "status": "In Progress",
    "progress": 0,
    "controls": [
        # ── DOMAIN 1: Security & Risk Management ──────────────────────────────
        {"id": "CISSP-1.1", "name": "Security Governance", "category": "Security & Risk Management",
         "description": "Define, implement, monitor, and improve information security governance aligned to business objectives.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Document board-level IS policies and governance committee charter."},
        {"id": "CISSP-1.2", "name": "Legal & Regulatory Compliance", "category": "Security & Risk Management",
         "description": "Identify and comply with applicable laws, regulations, and contractual requirements (GDPR, HIPAA, SOX, etc.).",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Maintain a compliance register listing all applicable regulations."},
        {"id": "CISSP-1.3", "name": "Risk Assessment & Management", "category": "Security & Risk Management",
         "description": "Identify, analyze, and respond to information security risks using NIST, ISO 31000, or OCTAVE methodologies.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide most recent risk assessment report and risk register."},
        {"id": "CISSP-1.4", "name": "Business Continuity Planning", "category": "Security & Risk Management",
         "description": "Develop and test BCP/DR plans to ensure continuity of critical operations.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide BCP document, BIA, and most recent DR test results."},
        {"id": "CISSP-1.5", "name": "Security Policy & Standards", "category": "Security & Risk Management",
         "description": "Establish, communicate, and enforce information security policies, standards, and procedures.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide current IS policy documentation with version history."},
        {"id": "CISSP-1.6", "name": "Security Awareness & Training", "category": "Security & Risk Management",
         "description": "Implement role-based security awareness training for all personnel.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide training completion records for past 12 months."},

        # ── DOMAIN 2: Asset Security ─────────────────────────────────────────
        {"id": "CISSP-2.1", "name": "Asset Classification & Ownership", "category": "Asset Security",
         "description": "Classify information assets by value, sensitivity, and criticality; assign ownership.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide asset inventory with classification labels."},
        {"id": "CISSP-2.2", "name": "Data Privacy & Protection", "category": "Asset Security",
         "description": "Implement privacy-by-design controls and data protection measures aligned to applicable regulations.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide DPA agreements and data flow diagrams."},
        {"id": "CISSP-2.3", "name": "Data Retention & Disposal", "category": "Asset Security",
         "description": "Define and enforce data retention schedules and secure disposal procedures.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide retention policy and disposal certificates."},
        {"id": "CISSP-2.4", "name": "Media Protection", "category": "Asset Security",
         "description": "Protect physical and digital media throughout its lifecycle including transport and disposal.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Document media handling and transport procedures."},

        # ── DOMAIN 3: Security Architecture & Engineering ────────────────────
        {"id": "CISSP-3.1", "name": "Security Models & Frameworks", "category": "Security Architecture & Engineering",
         "description": "Apply security models (Bell-LaPadula, Biba, Clark-Wilson) and enterprise security architectures.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Document security architecture model used."},
        {"id": "CISSP-3.2", "name": "System Hardening & Secure Configuration", "category": "Security Architecture & Engineering",
         "description": "Harden OS, applications, and hardware against baseline configurations (CIS Benchmarks).",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-3.3", "name": "Cryptography Implementation", "category": "Security Architecture & Engineering",
         "description": "Apply appropriate cryptographic algorithms, key management, and PKI for data-at-rest and data-in-transit.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-3.4", "name": "Physical Security", "category": "Security Architecture & Engineering",
         "description": "Implement physical access controls, environmental protections, and secure facility design.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide physical access logs and CCTV policy."},
        {"id": "CISSP-3.5", "name": "Secure System Design Principles", "category": "Security Architecture & Engineering",
         "description": "Apply least privilege, defense-in-depth, fail-secure, and other secure design principles.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-3.6", "name": "Vulnerability Management", "category": "Security Architecture & Engineering",
         "description": "Identify, classify, remediate, and verify system vulnerabilities on a continuous basis.",
         "status": "Not Implemented", "lastReviewed": ""},

        # ── DOMAIN 4: Communication & Network Security ───────────────────────
        {"id": "CISSP-4.1", "name": "Network Architecture Security", "category": "Communication & Network Security",
         "description": "Design and implement secure network topologies with DMZ, segmentation, and layered defenses.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-4.2", "name": "Firewall & Perimeter Security", "category": "Communication & Network Security",
         "description": "Deploy and maintain firewalls, IDS/IPS, and perimeter security controls.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-4.3", "name": "Secure Communications Protocols", "category": "Communication & Network Security",
         "description": "Enforce TLS 1.2+, disable deprecated protocols (SSLv3, TLS 1.0), enforce strong ciphers.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-4.4", "name": "Network Access Control", "category": "Communication & Network Security",
         "description": "Implement NAC, VLAN segmentation, 802.1X, and zero-trust network access policies.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-4.5", "name": "Wireless Security", "category": "Communication & Network Security",
         "description": "Secure wireless networks with WPA3, certificate-based auth, and rogue AP detection.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide wireless security audit report."},
        {"id": "CISSP-4.6", "name": "VPN & Remote Access Security", "category": "Communication & Network Security",
         "description": "Secure remote access with MFA-enforced VPN, split tunneling policies, and endpoint compliance checks.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide VPN configuration and remote access policy."},

        # ── DOMAIN 5: Identity & Access Management ───────────────────────────
        {"id": "CISSP-5.1", "name": "Identity Management Lifecycle", "category": "Identity & Access Management",
         "description": "Manage digital identities across provisioning, review, and de-provisioning lifecycle.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-5.2", "name": "Authentication Mechanisms", "category": "Identity & Access Management",
         "description": "Implement strong MFA, passwordless, biometric, or certificate-based authentication.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-5.3", "name": "Authorization & Access Control Models", "category": "Identity & Access Management",
         "description": "Apply RBAC, ABAC, MAC, or DAC access control models with least privilege enforcement.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-5.4", "name": "Privileged Access Management (PAM)", "category": "Identity & Access Management",
         "description": "Control, monitor, and audit privileged accounts including local admin, service, and domain admin accounts.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-5.5", "name": "Federated Identity & SSO", "category": "Identity & Access Management",
         "description": "Implement SAML, OAuth 2.0, OIDC, or federation for single sign-on and cross-domain access.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide SSO/federation architecture diagram."},

        # ── DOMAIN 6: Security Assessment & Testing ──────────────────────────
        {"id": "CISSP-6.1", "name": "Security Assessment Strategy", "category": "Security Assessment & Testing",
         "description": "Define and execute security assessments including audits, vulnerability scans, and penetration tests.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide most recent pentest report."},
        {"id": "CISSP-6.2", "name": "Vulnerability Scanning", "category": "Security Assessment & Testing",
         "description": "Run authenticated vulnerability scans on all in-scope assets at least quarterly.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-6.3", "name": "Penetration Testing", "category": "Security Assessment & Testing",
         "description": "Conduct annual external and internal penetration tests against systems and applications.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide pentest scope, findings, and remediation evidence."},
        {"id": "CISSP-6.4", "name": "Audit Log Review", "category": "Security Assessment & Testing",
         "description": "Review and analyze security audit logs for anomalies, unauthorized access, and policy violations.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-6.5", "name": "Software Testing Security", "category": "Security Assessment & Testing",
         "description": "Integrate SAST, DAST, SCA, and code review into the secure SDLC pipeline.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide SAST/DAST scan results."},

        # ── DOMAIN 7: Security Operations ────────────────────────────────────
        {"id": "CISSP-7.1", "name": "Incident Response Management", "category": "Security Operations",
         "description": "Establish IR procedures covering detection, analysis, containment, eradication, recovery, and lessons learned.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide IR playbooks and most recent incident reports."},
        {"id": "CISSP-7.2", "name": "Security Monitoring (SIEM/SOC)", "category": "Security Operations",
         "description": "Maintain SIEM or SOC capability for 24/7 threat detection, correlation, and alerting.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-7.3", "name": "Patch & Change Management", "category": "Security Operations",
         "description": "Maintain a formalized patch and change management process with risk assessment and rollback procedures.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-7.4", "name": "Disaster Recovery Operations", "category": "Security Operations",
         "description": "Test and maintain DR capabilities with defined RTO/RPO objectives and failover procedures.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide last DR drill report with RTO/RPO measurements."},
        {"id": "CISSP-7.5", "name": "Malware & Threat Defense", "category": "Security Operations",
         "description": "Deploy anti-malware, EDR, and threat hunting capabilities with current signatures.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-7.6", "name": "Digital Forensics & Evidence Handling", "category": "Security Operations",
         "description": "Establish forensic investigation capabilities and evidence handling procedures (chain of custody).",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide forensic investigation SOP and chain of custody form."},

        # ── DOMAIN 8: Software Development Security ───────────────────────────
        {"id": "CISSP-8.1", "name": "Secure SDLC Integration", "category": "Software Development Security",
         "description": "Integrate security into all phases of the SDLC from requirements through decommission.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-8.2", "name": "Secure Coding Standards", "category": "Software Development Security",
         "description": "Enforce OWASP Top 10, CWE/SANS Top 25, and language-specific secure coding guidelines.",
         "status": "Not Implemented", "lastReviewed": "", "manual_evidence_instructions": "Provide secure coding policy and code review evidence."},
        {"id": "CISSP-8.3", "name": "Application Vulnerability Assessment", "category": "Software Development Security",
         "description": "Identify and remediate application vulnerabilities via SAST, DAST, IAST, and RASP.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-8.4", "name": "Third-Party & Supply Chain Security", "category": "Software Development Security",
         "description": "Assess and monitor software supply chain risks including OSS dependencies and vendor SLAs.",
         "status": "Not Implemented", "lastReviewed": ""},
        {"id": "CISSP-8.5", "name": "DevSecOps & Security Automation", "category": "Software Development Security",
         "description": "Automate security gates in CI/CD pipelines including IaC scanning, secrets detection, and container security.",
         "status": "Not Implemented", "lastReviewed": ""},
    ],
    "createdAt": datetime.utcnow().isoformat(),
    "updatedAt": datetime.utcnow().isoformat(),
}

# Upsert into DB
result = db.compliance_frameworks.update_one(
    {"id": "cissp"},
    {"$set": CISSP_FRAMEWORK},
    upsert=True
)

total = len(CISSP_FRAMEWORK["controls"])
domains = set(c["category"] for c in CISSP_FRAMEWORK["controls"])
print(f"[OK] CISSP framework seeded: {total} controls across {len(domains)} domains")
print(f"     Domains: {', '.join(sorted(domains))}")
print(f"     MongoDB: matched={result.matched_count} modified={result.modified_count} upserted={result.upserted_id is not None}")
