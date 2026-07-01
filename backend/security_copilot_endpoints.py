"""AI Security Copilot — SOC analyst AI assistant. Routes at /api/security-copilot/."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from datetime import datetime, timezone
import logging
import uuid
import random

router = APIRouter(prefix="/api/security-copilot", tags=["Security Copilot"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SummarizeIncidentRequest(BaseModel):
    incident_id: str


class GenerateKQLRequest(BaseModel):
    question: str
    context: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    context_type: Optional[str] = "general"
    context_id: Optional[str] = None


class AnalyzeThreatRequest(BaseModel):
    indicator: str
    indicator_type: str  # ip | domain | url | hash | email
    context: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KQL_RULES = [
    (
        ["failed login", "failed logon", "failed authentication", "brute force login"],
        "SecurityEvent | where EventID == 4625 | where TimeGenerated > ago(1h)",
        "Filters Windows Security Event log for failed logon events in the last hour.",
        ["SecurityEvent"],
        "high",
    ),
    (
        ["impossible travel", "geo anomaly", "location anomaly"],
        "SigninLogs | where ResultType == 0 | summarize by UserPrincipalName, Location",
        "Aggregates successful sign-ins by user and location to surface impossible-travel patterns.",
        ["SigninLogs"],
        "high",
    ),
    (
        ["suspicious process", "malicious process", "powershell", "cmd", "wscript", "script execution"],
        (
            "DeviceProcessEvents | where InitiatingProcessCommandLine "
            "has_any ('powershell', 'cmd', 'wscript')"
        ),
        "Hunts for process events initiated by common scripting interpreters.",
        ["DeviceProcessEvents"],
        "high",
    ),
    (
        ["data exfiltration", "large upload", "data transfer", "data leak"],
        (
            "DeviceNetworkEvents | where RemotePort in (21, 22, 443) "
            "| where BytesSent > 10000000"
        ),
        "Identifies large outbound transfers on common exfiltration ports (FTP, SSH, HTTPS).",
        ["DeviceNetworkEvents"],
        "medium",
    ),
    (
        ["privilege escalation", "group added", "admin added", "elevated"],
        (
            "SecurityEvent | where EventID in (4728, 4732, 4756) "
            "| where TimeGenerated > ago(24h)"
        ),
        "Detects security group membership changes that may indicate privilege escalation.",
        ["SecurityEvent"],
        "high",
    ),
    (
        ["lateral movement", "pass the hash", "pass the ticket", "wmi", "psexec"],
        (
            "SecurityEvent | where EventID in (4648, 4624) "
            "| where LogonType in (3, 9) "
            "| where TimeGenerated > ago(6h)"
        ),
        "Detects network logon events typically associated with lateral movement techniques.",
        ["SecurityEvent"],
        "medium",
    ),
    (
        ["ransomware", "file encryption", "mass rename"],
        (
            "DeviceFileEvents | where ActionType == 'FileRenamed' "
            "| summarize count() by DeviceName, FolderPath "
            "| where count_ > 100"
        ),
        "Flags endpoints with high rates of file rename operations that may indicate ransomware.",
        ["DeviceFileEvents"],
        "high",
    ),
]

_KEYWORD_CHAT_RESPONSES = {
    "phishing": (
        "Phishing response steps: (1) Isolate affected mailboxes and block the sender domain. "
        "(2) Identify all recipients of the phishing email and check for credential submission. "
        "(3) Reset passwords for any accounts that clicked links or submitted credentials. "
        "(4) Scan endpoint devices used by affected users for malware. "
        "(5) Report the phishing domain to your threat-intel provider and update email filters. "
        "(6) Communicate with users about identifying phishing indicators."
    ),
    "ransomware": (
        "Ransomware containment steps: (1) Immediately isolate infected endpoints from the network. "
        "(2) Identify the ransomware strain and check for decryptors. "
        "(3) Preserve forensic images before any remediation. "
        "(4) Notify legal, compliance, and leadership per your IR plan. "
        "(5) Restore from clean backups after verifying backup integrity. "
        "(6) Conduct root-cause analysis to close the initial access vector."
    ),
    "lateral movement": (
        "Network isolation and lateral-movement containment: (1) Block the source account and "
        "endpoint from network access. (2) Review authentication logs to map all touched systems. "
        "(3) Reset credentials for all potentially compromised accounts. "
        "(4) Enable enhanced logging on AD and network devices. "
        "(5) Consider deploying network micro-segmentation to limit blast radius."
    ),
    "brute force": (
        "Brute-force account lockout guidance: (1) Enforce account lockout after 5 failed attempts. "
        "(2) Block or rate-limit the source IP at the firewall or WAF. "
        "(3) Enable MFA for all targeted accounts immediately. "
        "(4) Review VPN and remote-access logs for successful logins from the offending IP. "
        "(5) Alert account owners to change passwords if any attempt succeeded."
    ),
}


def _rule_based_kql(question: str):
    q = question.lower()
    for keywords, query, explanation, sources, confidence in _KQL_RULES:
        if any(kw in q for kw in keywords):
            return query, explanation, sources, confidence
    return None, None, None, None


def _keyword_chat_response(message: str):
    m = message.lower()
    for keyword, response in _KEYWORD_CHAT_RESPONSES.items():
        if keyword in m:
            return response
    return (
        "I'm your SOC analyst AI assistant. I can help you investigate security incidents, "
        "explain threat techniques, generate KQL queries, and provide remediation guidance. "
        "Please describe the security situation you need help with."
    )


def _score_indicator(indicator: str, indicator_type: str) -> int:
    base = 20 + random.randint(0, 30)
    ind_lower = indicator.lower()
    if indicator_type == "hash":
        if any(kw in ind_lower for kw in ("malware", "trojan", "ransom", "backdoor")):
            base = 85 + random.randint(0, 10)
        else:
            base = max(base, 15)
    elif indicator_type == "ip":
        # RFC 5737 test ranges → low score; common attack ranges → higher
        if ind_lower.startswith(("192.0.2.", "198.51.100.", "203.0.113.")):
            base = 10
        elif ind_lower.startswith(("185.", "45.33.", "198.199.")):
            base = min(65 + random.randint(0, 20), 95)
    elif indicator_type == "domain":
        if any(kw in ind_lower for kw in ("malware", "phish", "botnet", "c2", "evil")):
            base = 80 + random.randint(0, 15)
    elif indicator_type == "url":
        if any(kw in ind_lower for kw in (".exe", ".ps1", ".bat", "download", "payload")):
            base = 75 + random.randint(0, 20)
    elif indicator_type == "email":
        if any(kw in ind_lower for kw in ("noreply@", "no-reply@", "info@")):
            base = max(base, 35)
    return min(base, 100)


def _verdict(score: int) -> str:
    if score >= 70:
        return "malicious"
    if score >= 40:
        return "suspicious"
    return "clean"


def _mitre_for_indicator(indicator_type: str) -> list:
    mapping = {
        "ip":     ["T1071 - Application Layer Protocol", "T1041 - Exfiltration Over C2 Channel"],
        "domain": ["T1071.001 - Web Protocols", "T1566.002 - Spearphishing Link"],
        "url":    ["T1566.002 - Spearphishing Link", "T1204 - User Execution"],
        "hash":   ["T1204.002 - Malicious File", "T1027 - Obfuscated Files or Information"],
        "email":  ["T1566.001 - Spearphishing Attachment", "T1598 - Phishing for Information"],
    }
    return mapping.get(indicator_type, ["T1071 - Application Layer Protocol"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/summarize-incident")
async def summarize_incident(
    body: SummarizeIncidentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    tenant_filter = {"tenantId": current_user.tenant_id}

    incident = await db.security_incidents.find_one(
        {**tenant_filter, "id": body.incident_id}
    )
    if not incident:
        incident = await db.security_cases.find_one(
            {**tenant_filter, "id": body.incident_id}
        )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Fetch last 10 related events
    related_cursor = db.security_events.find(
        {**tenant_filter, "incidentId": body.incident_id}
    ).sort("timestamp", -1).limit(10)
    related_events = await related_cursor.to_list(length=10)

    title = incident.get("title", "Untitled Incident")
    severity = incident.get("severity", "unknown")
    description = incident.get("description", "No description provided.")
    affected_assets = incident.get("affected_assets", incident.get("affectedAssets", []))
    status = incident.get("status", "open")

    prompt = (
        f"Summarize this security incident: Title={title}, Severity={severity}, "
        f"Status={status}, Description={description}, "
        f"Affected Assets={affected_assets}. "
        f"Related events: {[e.get('description', e.get('message', '')) for e in related_events[:5]]}."
    )

    summary = description
    ai_available = False
    try:
        from ai_service import ai_service
        summary = await ai_service.generate_text(prompt, source="copilot_summarize")
        ai_available = True
    except Exception as exc:
        logger.warning("AI unavailable for incident summary: %s", exc)
        summary = (
            f"Security incident '{title}' with severity '{severity}' is currently '{status}'. "
            f"Description: {description} "
            f"Affected assets: {', '.join(str(a) for a in affected_assets) if affected_assets else 'none recorded'}. "
            f"{len(related_events)} related events found."
        )

    key_findings = [
        f"Severity level: {severity}",
        f"Current status: {status}",
        f"Affected assets: {len(affected_assets)} identified",
        f"Related events: {len(related_events)} correlated",
    ]
    if incident.get("mitre_technique") or incident.get("mitreTechnique"):
        key_findings.append(
            f"MITRE technique: {incident.get('mitre_technique') or incident.get('mitreTechnique')}"
        )

    recommended_actions = [
        "Contain affected endpoints and isolate from network",
        "Collect forensic artefacts before remediation",
        "Reset credentials for all impacted accounts",
        "Review and block identified IOCs at perimeter",
    ]

    risk_level = severity if severity in ("critical", "high", "medium", "low") else "medium"

    # Persist to copilot_history
    history_doc = {
        "id": uuid.uuid4().hex,
        "tenantId": current_user.tenant_id,
        "type": "summarize_incident",
        "incident_id": body.incident_id,
        "prompt": prompt,
        "summary": summary,
        "ai_used": ai_available,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.copilot_history.insert_one(history_doc)
    except Exception as exc:
        logger.warning("Failed to store copilot history: %s", exc)

    return {
        "incident_id": body.incident_id,
        "summary": summary,
        "key_findings": key_findings,
        "recommended_actions": recommended_actions,
        "risk_level": risk_level,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/generate-kql")
async def generate_kql(
    body: GenerateKQLRequest,
    current_user: TokenData = Depends(get_current_user),
):
    question = body.question.strip()
    kql_query, explanation, sources, confidence = _rule_based_kql(question)

    if kql_query is None:
        # Attempt AI generation
        try:
            from ai_service import ai_service
            ai_prompt = (
                "Generate a KQL (Kusto Query Language) query for Azure Sentinel/Microsoft Defender "
                f"that answers: '{question}'. "
                "Return ONLY the KQL query on a single line, then a blank line, then a one-sentence explanation."
            )
            raw = await ai_service.generate_text(ai_prompt, source="copilot_kql")
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            kql_query = lines[0] if lines else question
            explanation = lines[1] if len(lines) > 1 else "AI-generated query."
            sources = ["SecurityEvent", "DeviceEvents"]
            confidence = "medium"
        except Exception as exc:
            logger.warning("AI KQL generation failed: %s", exc)
            kql_query = f"// No matching KQL pattern found for: {question}"
            explanation = "No built-in rule matched this question and AI is unavailable."
            sources = []
            confidence = "low"

    return {
        "question": question,
        "kql_query": kql_query,
        "explanation": explanation,
        "estimated_data_sources": sources or [],
        "confidence": confidence or "low",
    }


@router.post("/chat")
async def chat(
    body: ChatRequest,
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    tenant_filter = {"tenantId": current_user.tenant_id}
    context_used = False
    incident_context = ""

    if body.context_type == "incident" and body.context_id:
        incident = await db.security_incidents.find_one(
            {**tenant_filter, "id": body.context_id}
        )
        if incident:
            incident_context = (
                f"\n\nIncident context: Title={incident.get('title')}, "
                f"Severity={incident.get('severity')}, "
                f"Status={incident.get('status')}, "
                f"Description={incident.get('description', '')}."
            )
            context_used = True

    system_prompt = (
        "You are a SOC analyst AI assistant for an enterprise security platform. "
        "Help investigate security incidents, explain threats, and provide remediation guidance."
    )
    full_prompt = f"{system_prompt}{incident_context}\n\nUser: {body.message}"

    response_text = ""
    try:
        from ai_service import ai_service
        response_text = await ai_service.generate_text(full_prompt, source="copilot_chat")
        response_type = "ai"
    except Exception as exc:
        logger.warning("AI chat unavailable: %s", exc)
        response_text = _keyword_chat_response(body.message)
        response_type = "rule_based"

    suggestions = [
        "What MITRE ATT&CK techniques are associated with this threat?",
        "How can I contain this incident quickly?",
        "What evidence should I collect for forensic analysis?",
    ]

    history_doc = {
        "id": uuid.uuid4().hex,
        "tenantId": current_user.tenant_id,
        "type": "chat",
        "message": body.message,
        "response": response_text,
        "context_type": body.context_type,
        "context_id": body.context_id,
        "response_type": response_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.copilot_history.insert_one(history_doc)
    except Exception as exc:
        logger.warning("Failed to store copilot chat history: %s", exc)

    return {
        "response": response_text,
        "context_used": context_used,
        "suggestions": suggestions,
        "response_type": response_type,
    }


@router.post("/analyze-threat")
async def analyze_threat(
    body: AnalyzeThreatRequest,
    current_user: TokenData = Depends(get_current_user),
):
    valid_types = {"ip", "domain", "url", "hash", "email"}
    if body.indicator_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"indicator_type must be one of: {', '.join(sorted(valid_types))}",
        )

    db = get_database()
    tenant_filter = {"tenantId": current_user.tenant_id}

    # Check threat_intel collection for known IOCs
    ioc_matches = []
    try:
        ioc_doc = await db.threat_intel.find_one(
            {**tenant_filter, "indicator": body.indicator}
        )
        if ioc_doc:
            ioc_matches.append({
                "source": ioc_doc.get("source", "internal"),
                "verdict": ioc_doc.get("verdict", "suspicious"),
                "tags": ioc_doc.get("tags", []),
            })
    except Exception as exc:
        logger.warning("IOC lookup failed: %s", exc)

    threat_score = _score_indicator(body.indicator, body.indicator_type)
    # Escalate score if we have a known-bad match
    if ioc_matches:
        threat_score = max(threat_score, 70)

    verdict = _verdict(threat_score)

    threat_categories = []
    if threat_score >= 70:
        threat_categories = ["Malware", "C2 Communication"] if body.indicator_type in ("ip", "domain") else ["Malicious File"]
    elif threat_score >= 40:
        threat_categories = ["Suspicious Activity"]

    context_analysis = (
        f"Indicator '{body.indicator}' of type '{body.indicator_type}' scored {threat_score}/100. "
    )
    if body.context:
        context_analysis += f"Provided context: {body.context}. "

    try:
        from ai_service import ai_service
        ai_prompt = (
            f"Briefly analyse this security indicator for a SOC analyst: "
            f"Indicator={body.indicator}, Type={body.indicator_type}, "
            f"Threat score={threat_score}/100, Verdict={verdict}. "
            f"Provide a 2-sentence context analysis."
        )
        context_analysis = await ai_service.generate_text(ai_prompt, source="copilot_threat")
    except Exception:
        pass

    recommended_actions = (
        [
            f"Block {body.indicator} at perimeter firewall and DNS",
            "Search endpoint logs for any connections to this indicator",
            "Submit to threat-intel sharing platforms (MISP, OpenCTI)",
            "Escalate to incident response if internal hosts are confirmed",
        ]
        if threat_score >= 40
        else [
            "Monitor for repeat occurrences",
            "Verify in a secondary threat-intel source",
        ]
    )

    history_doc = {
        "id": uuid.uuid4().hex,
        "tenantId": current_user.tenant_id,
        "type": "analyze_threat",
        "indicator": body.indicator,
        "indicator_type": body.indicator_type,
        "threat_score": threat_score,
        "verdict": verdict,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.copilot_history.insert_one(history_doc)
    except Exception as exc:
        logger.warning("Failed to store threat analysis history: %s", exc)

    return {
        "indicator": body.indicator,
        "indicator_type": body.indicator_type,
        "threat_score": threat_score,
        "verdict": verdict,
        "threat_categories": threat_categories,
        "ioc_matches": ioc_matches,
        "context_analysis": context_analysis,
        "recommended_actions": recommended_actions,
        "mitre_techniques": _mitre_for_indicator(body.indicator_type),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/history")
async def get_history(
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    cursor = db.copilot_history.find(
        {"tenantId": current_user.tenant_id}
    ).sort("created_at", -1).limit(20)
    interactions = await cursor.to_list(length=20)
    for item in interactions:
        item.pop("_id", None)
    return {"interactions": interactions}
