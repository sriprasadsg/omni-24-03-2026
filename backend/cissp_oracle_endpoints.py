"""
CISSP Oracle Endpoints
======================
Backend API for the CISSP AI Advisor / Oracle feature.

Endpoints:
  POST /api/cissp/oracle/chat        — CISSP-domain-aware AI chat advisor
  GET  /api/cissp/oracle/domains     — List all 8 CISSP domains with descriptions
  POST /api/cissp/oracle/assess      — Trigger full CISSP assessment via agent
  GET  /api/cissp/oracle/report/{id} — Get a stored CISSP assessment report
  GET  /api/cissp/oracle/knowledge   — Get CISSP knowledge reference cards
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/cissp", tags=["CISSP Oracle"])

# ── CISSP Domain Reference Knowledge Base ────────────────────────────────────

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

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/oracle/domains")
async def get_cissp_domains():
    """Return all 8 CISSP domains with descriptions, key concepts, and agent check mappings."""
    return {
        "success": True,
        "total_domains": len(CISSP_DOMAINS),
        "total_weight": "100%",
        "domains": CISSP_DOMAINS
    }


@router.get("/oracle/knowledge")
async def get_cissp_knowledge():
    """Return CISSP knowledge reference cards for each domain."""
    knowledge_cards = []
    for domain in CISSP_DOMAINS:
        knowledge_cards.append({
            "domain_id": domain["id"],
            "domain_name": domain["name"],
            "exam_weight": f"{domain['exam_weight']}%",
            "key_concepts": domain["key_concepts"],
            "common_questions_focus": get_domain_focus(domain["id"]),
            "quick_reference": get_domain_quick_ref(domain["id"]),
            "color": domain["color"],
        })
    return {"success": True, "knowledge_cards": knowledge_cards}


def get_domain_focus(domain_id: int) -> list:
    focus_map = {
        1: ["Risk calculation formulas", "BCP/DRP testing types", "Types of laws (civil, criminal, administrative)", "Data Remanence controls"],
        2: ["Data classification levels", "Data ownership roles (Owner/Custodian/User)", "Retention periods", "Secure disposal methods (Degaussing, Shredding)"],
        3: ["Security model rules (BLP, Biba, Clark-Wilson)", "Cryptography algorithms (symmetric vs asymmetric)", "PKI components", "Secure hardware trust levels"],
        4: ["OSI vs TCP/IP layer responsibilities", "Firewall types and placement", "VPN protocols (IPSec modes)", "Wireless security protocols (WPA3, EAP variants)"],
        5: ["Authentication factors (Type 1/2/3)", "Access control model characteristics", "SSO and federation protocols", "PAM controls"],
        6: ["Pen test phases (Recon/Scan/Exploit/Report)", "Vulnerability vs Penetration testing", "SOC 2 Type I vs II", "Code review techniques"],
        7: ["IR phases (PICERL)", "Forensic acquisition types", "Evidence handling (chain of custody)", "RTO vs RPO vs MTTR"],
        8: ["SDLC security integration points", "OWASP Top 10 vulnerabilities", "SAST vs DAST vs IAST", "Threat modeling methodologies (STRIDE)"],
    }
    return focus_map.get(domain_id, [])


def get_domain_quick_ref(domain_id: int) -> dict:
    ref_map = {
        1: {"Risk Formula": "Risk = Threat × Vulnerability × Impact", "ALE": "ALE = SLE × ARO", "SLE": "SLE = Asset Value × EF"},
        2: {"Classification Levels": "Top Secret > Secret > Confidential > Unclassified", "Data States": "At Rest, In Transit, In Use"},
        3: {"BLP Rule": "No Read Up, No Write Down (Confidentiality)", "Biba Rule": "No Read Down, No Write Up (Integrity)"},
        4: {"OSI Layer 7": "Application", "OSI Layer 3": "Network (IP)", "OSI Layer 2": "Data Link (MAC/Switch)"},
        5: {"Auth Factors": "Type1=Something you know, Type2=Something you have, Type3=Something you are", "AAA": "Authentication, Authorization, Accounting"},
        6: {"Black Box": "No prior knowledge", "White Box": "Full knowledge", "Grey Box": "Partial knowledge"},
        7: {"IR Phases": "PICERL: Preparation, Identification, Containment, Eradication, Recovery, Lessons Learned", "RTO": "Recovery Time Objective", "RPO": "Recovery Point Objective"},
        8: {"STRIDE": "Spoofing, Tampering, Repudiation, Information Disclosure, DoS, Elevation of Privilege", "OWASP #1": "Broken Access Control (2021)"},
    }
    return ref_map.get(domain_id, {})


@router.post("/oracle/chat")
async def cissp_oracle_chat(request: Dict[str, Any]):
    """
    CISSP Oracle AI chat endpoint.
    Accepts a user message and optionally recent compliance findings.
    Returns a domain-classified AI response with actionable guidance.
    """
    message = request.get("message", "").strip()
    findings = request.get("findings", [])
    domain_filter = request.get("domain_id")
    hostname = request.get("hostname", "current system")

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    # Build context from recent findings if provided
    context_parts = [f"System: {hostname}"]
    if findings:
        context_parts.append(f"Recent compliance findings: {len(findings)} items")
        for f in findings[:5]:
            context_parts.append(f"  - [{f.get('status','?')}] {f.get('check', f.get('name', 'Unknown'))}: {f.get('detail', '')}")

    if domain_filter:
        domain_info = next((d for d in CISSP_DOMAINS if d["id"] == domain_filter), None)
        if domain_info:
            context_parts.append(f"Focus domain: {domain_info['name']} ({domain_info['exam_weight']}% exam weight)")

    context = "\n".join(context_parts)

    # Try to use Ollama/local LLM first, fall back to rule-based response
    ai_response = await _generate_cissp_response(message, context, findings, domain_filter)

    return {
        "success": True,
        "response": ai_response["text"],
        "domain_classifications": ai_response.get("domains", []),
        "risk_level": ai_response.get("risk_level"),
        "recommendations": ai_response.get("recommendations", []),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _generate_cissp_response(message: str, context: str, findings: list, domain_filter: Optional[int]) -> dict:
    """Generate a CISSP-aware response. Tries Ollama LLM first, falls back to rule-based."""
    import httpx

    # 1. Try local LLM (Ollama)
    try:
        system_prompt = CISSP_SYSTEM_PROMPT.format(context=context)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3",
                    "prompt": f"{system_prompt}\n\nUser question: {message}",
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 800}
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                llm_text = data.get("response", "")
                if llm_text:
                    return {
                        "text": llm_text,
                        "domains": _classify_domains(message + " " + llm_text),
                        "risk_level": "See analysis",
                        "recommendations": [],
                        "source": "llm"
                    }
    except Exception:
        pass  # Fall back to rule-based

    # 2. Rule-based CISSP advisor (always works, no LLM needed)
    return _rule_based_cissp_response(message, findings, domain_filter)


def _classify_domains(text: str) -> list:
    """Detect which CISSP domains are referenced in text."""
    text_lower = text.lower()
    matched = []
    keywords = {
        1: ["risk", "governance", "policy", "bcp", "drp", "compliance", "regulatory"],
        2: ["asset", "data classification", "retention", "disposal", "media", "privacy"],
        3: ["encryption", "cryptography", "tls", "pki", "architecture", "secure design", "hardening"],
        4: ["firewall", "network", "vpn", "tls", "ipsec", "vlan", "wireless", "nat", "protocol"],
        5: ["identity", "authentication", "access control", "iam", "pam", "mfa", "rbac", "abac", "sso"],
        6: ["vulnerability", "penetration test", "pentest", "audit", "assessment", "scan", "sast", "dast"],
        7: ["incident", "forensics", "siem", "monitoring", "dr", "backup", "malware", "threat"],
        8: ["sdlc", "secure coding", "owasp", "devsecops", "application", "software", "supply chain"],
    }
    for domain_id, kws in keywords.items():
        if any(kw in text_lower for kw in kws):
            matched.append(domain_id)
    return matched[:3]  # max 3 domain classifications


def _rule_based_cissp_response(message: str, findings: list, domain_filter: Optional[int]) -> dict:
    """Generate contextual CISSP guidance without an LLM."""
    msg_lower = message.lower()
    response_parts = []
    domains_matched = _classify_domains(message)
    recommendations = []

    # Domain-specific guidance
    if any(kw in msg_lower for kw in ["firewall", "network", "port", "rdp"]):
        response_parts.append(
            "[D4] **Communication & Network Security**\n\n"
            "From a CISSP perspective, network security requires a layered defense (Defense-in-Depth):\n\n"
            "1. **Firewall Policy Review**: Ensure all firewall rules follow the principle of least privilege — deny all, permit by exception.\n"
            "2. **RDP Hardening**: RDP (port 3389) should be restricted to VPN-only access with NLA enforced (`UserAuthentication=1`). Consider moving to a jump server or PAM solution.\n"
            "3. **Port Exposure**: Listening on ports 23 (Telnet), 21 (FTP), or 135/139 violates CISSP D4 guidance. Use encrypted alternatives: SSH (22), SFTP, and restrict WMI/RPC.\n"
            "4. **Network Segmentation**: Apply VLAN-based microsegmentation. Workstations and servers should never be on the same broadcast domain.\n\n"
            "**CIS Benchmark Reference**: CIS Controls v8, Control 12 (Network Infrastructure Management)."
        )
        recommendations.append("Restrict RDP to VPN with NLA enforcement")
        recommendations.append("Disable Telnet/FTP — replace with SSH/SFTP")
        recommendations.append("Implement network segmentation with VLANs")

    elif any(kw in msg_lower for kw in ["password", "authentication", "mfa", "account", "identity", "access"]):
        response_parts.append(
            "[D5] **Identity & Access Management**\n\n"
            "CISSP Domain 5 principles for identity and access:\n\n"
            "1. **Authentication Strength**: Implement MFA for all privileged and remote access. NIST SP 800-63B recommends phishing-resistant MFA (FIDO2/WebAuthn).\n"
            "2. **Privileged Access**: Apply PAM solution. Local admin accounts should be managed (LAPS for Windows), have unique passwords per machine, and require just-in-time elevation.\n"
            "3. **Account Lifecycle**: Implement automated provisioning/de-provisioning. Terminated user accounts should be disabled within 24 hours (best: same day).\n"
            "4. **Access Review**: Conduct quarterly access certification reviews. Flag any accounts with excessive permissions (SoD violations).\n\n"
            "**Key CISSP Concept**: Need-to-know + Least Privilege = Minimal Attack Surface."
        )
        recommendations.append("Deploy MFA across all privileged accounts")
        recommendations.append("Implement Microsoft LAPS for local admin management")
        recommendations.append("Schedule quarterly access certification reviews")

    elif any(kw in msg_lower for kw in ["encryption", "bitlocker", "tls", "crypto", "cipher"]):
        response_parts.append(
            "[D3] **Security Architecture & Engineering — Cryptography**\n\n"
            "CISSP-level cryptographic guidance:\n\n"
            "1. **Data at Rest**: Enforce BitLocker with TPM+PIN mode on all endpoints. AES-256 is the CISSP standard. Enterprise managed via Microsoft BitLocker Administration and Monitoring (MBAM) or Intune.\n"
            "2. **Data in Transit**: Enforce TLS 1.2 minimum (TLS 1.3 preferred). Disable TLS 1.0/1.1, SSLv3. Remove RC4, 3DES, DES cipher suites.\n"
            "3. **Key Management**: Keys must be protected separately from encrypted data. Use HSM for critical keys. Implement key rotation schedule.\n"
            "4. **Certificate Management**: Monitor certificate expiry, use internal CA for internal services, enforce certificate pinning for critical APIs.\n\n"
            "**CISSP Principle**: Cryptography alone doesn't solve security. Key management is often the weakest link."
        )
        recommendations.append("Enable BitLocker with TPM+PIN on all endpoints")
        recommendations.append("Disable TLS 1.0/1.1 and weak cipher suites (RC4, 3DES)")
        recommendations.append("Implement centralized certificate lifecycle management")

    elif any(kw in msg_lower for kw in ["incident", "breach", "attack", "malware", "ransomware"]):
        response_parts.append(
            "[D7] **Security Operations — Incident Response**\n\n"
            "CISSP PICERL Incident Response Framework:\n\n"
            "1. **Preparation**: Maintain updated IR playbooks, contact lists, and forensic toolkits. Test IR procedures quarterly.\n"
            "2. **Identification**: Leverage SIEM alerts, IDS/IPS, EDR alerts, and user reports. Define incident severity thresholds (P1-P4).\n"
            "3. **Containment**: Isolate affected systems immediately. For ransomware: disconnect from network, do NOT power off (volatile memory evidence). Short-term containment → long-term containment.\n"
            "4. **Eradication**: Remove malware/attacker tooling, patch exploited vulnerabilities, reset all credentials.\n"
            "5. **Recovery**: Restore from clean backup, verify integrity before reconnection. Monitor for re-infection.\n"
            "6. **Lessons Learned**: Within 2 weeks, conduct post-incident review. Update playbooks, controls, and training.\n\n"
            "**CISSP Digital Forensics Note**: Always preserve chain of custody. Capture volatile data first (RAM → running processes → network connections → disk)."
        )
        recommendations.append("Test IR playbooks with tabletop exercises quarterly")
        recommendations.append("Deploy EDR solution with threat hunting capability")
        recommendations.append("Ensure clean, offline/immutable backups exist for ransomware recovery")

    elif any(kw in msg_lower for kw in ["audit", "log", "siem", "monitoring", "compliance check"]):
        response_parts.append(
            "[D6] **Security Assessment & Testing — Audit & Monitoring**\n\n"
            "CISSP perspective on security logging and audit:\n\n"
            "1. **Audit Policy**: Configure Windows audit policy to capture logon events, privilege use, object access, and policy changes. Tool: `auditpol /get /category:*`.\n"
            "2. **Log Retention**: NIST recommends 90 days online, 1 year archived. PCI DSS requires 12 months. ISO 27001: organization-defined.\n"
            "3. **SIEM Integration**: Centralize logs. Correlate events across endpoints, network, and application layers. Alert on lateral movement, privilege escalation, and data exfiltration indicators.\n"
            "4. **PowerShell Logging**: Enable Script Block Logging and Module Logging (critical for threat hunting PowerShell-based attacks).\n\n"
            "**CISSP D6 Key Test**: Security awareness doesn't equal security. Continuous monitoring and measurement is essential."
        )
        recommendations.append("Configure comprehensive Windows Audit Policy (logon, privilege, object access)")
        recommendations.append("Enable PowerShell Script Block and Module Logging")
        recommendations.append("Integrate logs into SIEM with 90-day retention minimum")

    elif any(kw in msg_lower for kw in ["vulnerability", "patch", "cve", "update", "hotfix"]):
        response_parts.append(
            "[D6] **Security Assessment & Testing — Vulnerability Management**\n\n"
            "CISSP-level vulnerability management program:\n\n"
            "1. **Scan Frequency**: Run authenticated vulnerability scans weekly for critical systems, monthly for others. Track MTTR (Mean Time to Remediate).\n"
            "2. **Patching SLA**: Critical (CVSS ≥9): 24-48 hours. High (CVSS 7-8.9): 7 days. Medium: 30 days. Low: 90 days.\n"
            "3. **Patch Prioritization**: Use CVSS + EPSS (Exploit Prediction Scoring) to focus on actively exploited vulnerabilities first.\n"
            "4. **Compensating Controls**: Where patching is not immediately possible, apply WAF rules, network isolation, or exploit mitigation as temporary compensating controls.\n\n"
            "**CISSP D3 Tie-in**: Vulnerability management is part of the ongoing security architecture maintenance cycle."
        )
        recommendations.append("Implement CVSS-based patching SLA (Critical: 24-48h)")
        recommendations.append("Use EPSS score alongside CVSS for exploitation likelihood prioritization")
        recommendations.append("Run authenticated vulnerability scans weekly on critical systems")

    else:
        # Generic CISSP guidance
        response_parts.append(
            "**CISSP Oracle Analysis**\n\n"
            "I'm your CISSP security advisor covering all 8 domains. Here are the top CISSP-aligned security recommendations for any enterprise:\n\n"
            "**[D1] Risk Management**: Maintain an active risk register. Calculate ALE = SLE × ARO for all significant risks.\n"
            "**[D3] Architecture**: Enforce least privilege, defense-in-depth, and fail-secure across all systems.\n"
            "**[D4] Network**: All traffic should be encrypted (TLS 1.2+). Segment networks. Disable legacy protocols.\n"
            "**[D5] IAM**: MFA everywhere. Quarterly access reviews. PAM for privileged accounts.\n"
            "**[D6] Assessment**: Monthly vulnerability scans + annual penetration tests. Review audit logs weekly.\n"
            "**[D7] Operations**: Tested IR plan. EDR on all endpoints. Immutable backups for ransomware protection.\n\n"
            "Ask me about a specific domain, finding, control, or security concept for detailed CISSP-level guidance."
        )
        recommendations.append("Conduct annual CISSP-framework security assessment")
        recommendations.append("Implement NIST Cybersecurity Framework as baseline")
        domains_matched = [1, 3, 4, 5, 6, 7]

    return {
        "text": "\n\n".join(response_parts),
        "domains": domains_matched,
        "risk_level": "See analysis",
        "recommendations": recommendations,
        "source": "rule_based"
    }


@router.post("/oracle/assess")
async def trigger_cissp_assessment(request: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    Trigger a CISSP 8-domain assessment for a specific hostname/asset.
    The assessment runs as a background task and results are stored in the DB.
    """
    from database import get_database
    hostname = request.get("hostname", "")
    if not hostname:
        # Try to get from DB
        db = get_database()
        agent = await db.agents.find_one({"status": "Online"}, {"hostname": 1})
        hostname = agent.get("hostname", "localhost") if agent else "localhost"

    assessment_id = f"cissp-{uuid.uuid4().hex[:8]}"

    async def _run_and_store(assessment_id: str, hostname: str):
        """Run CISSP assessment and store results in DB."""
        try:
            import asyncio
            from database import get_database

            loop = asyncio.get_event_loop()
            # Import and run the assessment
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'agent', 'capabilities'))

            from cissp_analysis import run_cissp_assessment
            result = await loop.run_in_executor(None, run_cissp_assessment)

            db = get_database()
            await db.cissp_assessments.update_one(
                {"id": assessment_id},
                {"$set": {
                    "id": assessment_id,
                    "hostname": hostname,
                    "status": "completed",
                    "result": result,
                    "completedAt": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True
            )
            print(f"[CISSP Oracle] Assessment {assessment_id} completed for {hostname}")
        except Exception as e:
            print(f"[CISSP Oracle] Assessment failed: {e}")

    background_tasks.add_task(_run_and_store, assessment_id, hostname)

    return {
        "success": True,
        "assessment_id": assessment_id,
        "hostname": hostname,
        "message": "CISSP 8-domain assessment started. Results available in ~60 seconds.",
        "status": "running"
    }


@router.get("/oracle/assess/{assessment_id}")
async def get_cissp_assessment(assessment_id: str):
    """Retrieve a stored CISSP assessment report by ID."""
    from database import get_database
    db = get_database()
    record = await db.cissp_assessments.find_one({"id": assessment_id}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return {"success": True, "assessment": record}


@router.get("/oracle/assessments")
async def list_cissp_assessments():
    """List all stored CISSP assessments."""
    from database import get_database
    db = get_database()
    cursor = db.cissp_assessments.find({}, {"_id": 0, "result.domains": 0}).sort("completedAt", -1).limit(20)
    records = await cursor.to_list(length=20)
    return {"success": True, "assessments": records, "count": len(records)}
