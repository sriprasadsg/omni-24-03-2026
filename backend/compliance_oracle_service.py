"""
Compliance Oracle Service

Analyzes unstructured policy text and extracts technical compliance rules.
Priority chain:
  1. Platform-configured LLM (Anthropic / OpenAI via infrastructure collection)
  2. Rule-based keyword extractor (deterministic, no random values)
"""
import asyncio
import os
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/api/compliance_oracle", tags=["Compliance Oracle"])

# ── Static rule library (keyword → TechnicalRule) ────────────────────────────
_RULE_LIBRARY = [
    {
        "keywords": ["encrypt", "encryption", "at rest", "aes"],
        "policy_id": "POL-001",
        "rule_name": "Enforce Storage Encryption at Rest",
        "technical_implementation": (
            "s3_bucket.server_side_encryption_configuration.rule"
            ".apply_server_side_encryption_by_default.sse_algorithm = 'AES256'"
        ),
        "severity": "High",
        "extracted": "Requirement: Data Encryption at Rest",
    },
    {
        "keywords": ["tls", "transit", "in-transit", "https", "ssl"],
        "policy_id": "POL-002",
        "rule_name": "Enforce TLS in Transit",
        "technical_implementation": "elb_listener.protocol = 'HTTPS'; certificate_arn required",
        "severity": "High",
        "extracted": "Requirement: Encryption in Transit (TLS)",
    },
    {
        "keywords": ["retention", "log retention", "audit log"],
        "policy_id": "POL-003",
        "rule_name": "Log Retention ≥ 90 Days",
        "technical_implementation": "cloudwatch_log_group.retention_in_days >= 90",
        "severity": "Medium",
        "extracted": "Requirement: Data Retention Policy",
    },
    {
        "keywords": ["mfa", "multi-factor", "two-factor", "2fa"],
        "policy_id": "POL-004",
        "rule_name": "Enforce MFA for All IAM Users",
        "technical_implementation": "aws_iam_account_password_policy.require_mfa = true",
        "severity": "Critical",
        "extracted": "Requirement: Multi-Factor Authentication",
    },
    {
        "keywords": ["least privilege", "minimum privilege", "need-to-know"],
        "policy_id": "POL-005",
        "rule_name": "Apply Least-Privilege IAM Policies",
        "technical_implementation": "iam_policy.effect = 'Allow'; actions scoped to required services only",
        "severity": "High",
        "extracted": "Requirement: Principle of Least Privilege",
    },
    {
        "keywords": ["patch", "vulnerability", "cve", "update"],
        "policy_id": "POL-006",
        "rule_name": "Automated Vulnerability Patching SLA",
        "technical_implementation": "patch_manager.patch_baseline.approval_delay_days <= 7 for Critical CVEs",
        "severity": "High",
        "extracted": "Requirement: Timely Vulnerability Remediation",
    },
    {
        "keywords": ["backup", "recovery", "rpo", "rto", "disaster"],
        "policy_id": "POL-007",
        "rule_name": "Automated Backup with Tested Recovery",
        "technical_implementation": "aws_backup.plan.rules.completion_window_minutes <= 60; RPO <= 1h",
        "severity": "High",
        "extracted": "Requirement: Business Continuity / Disaster Recovery",
    },
    {
        "keywords": ["access log", "audit trail", "cloudtrail", "siem"],
        "policy_id": "POL-008",
        "rule_name": "Enable Cloud Audit Trail",
        "technical_implementation": "aws_cloudtrail.is_multi_region_trail = true; s3_key_prefix set",
        "severity": "Medium",
        "extracted": "Requirement: Audit Logging",
    },
    {
        "keywords": ["password", "complexity", "expiry", "rotation"],
        "policy_id": "POL-009",
        "rule_name": "Strong Password Policy",
        "technical_implementation": (
            "iam_account_password_policy: min_length=14, require_symbols=true, max_age=90"
        ),
        "severity": "Medium",
        "extracted": "Requirement: Password / Credential Policy",
    },
    {
        "keywords": ["segregat", "segment", "vlan", "dmz", "firewall"],
        "policy_id": "POL-010",
        "rule_name": "Network Segmentation Controls",
        "technical_implementation": (
            "security_group.ingress: restrict to required CIDRs; no 0.0.0.0/0 on port 22/3389"
        ),
        "severity": "High",
        "extracted": "Requirement: Network Segmentation",
    },
]


class PolicyAnalysisRequest(BaseModel):
    policy_text: str


class TechnicalRule(BaseModel):
    policy_id: str
    rule_name: str
    technical_implementation: str
    severity: str


class AnalysisResult(BaseModel):
    summary: str
    extracted_policies: List[str]
    generated_rules: List[TechnicalRule]
    confidence_score: float


async def _llm_analyze(policy_text: str) -> AnalysisResult | None:
    """Try platform-configured LLM; return None if unavailable."""
    try:
        from database import get_database
        db = get_database()
        llm_cfg = await db.infrastructure.find_one({"type": "llm"}, {"_id": 0})
        provider = (llm_cfg or {}).get("provider", "anthropic").lower()
        api_key = (llm_cfg or {}).get("apiKey") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        prompt = (
            "You are a compliance engineer. Analyze the policy text below and extract:\n"
            "1. A one-sentence summary\n"
            "2. A JSON list of extracted policy requirements (strings)\n"
            "3. A JSON list of technical rules, each with fields: "
            "policy_id, rule_name, technical_implementation, severity (Critical/High/Medium/Low)\n\n"
            "Return ONLY valid JSON with keys: summary, extracted_policies, generated_rules\n\n"
            f"Policy text:\n{policy_text[:3000]}"
        )

        import json
        if provider in ("anthropic", "claude"):
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=os.getenv("ORACLE_MODEL", "cc/claude-haiku-4-5-20251001"),
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text
        elif provider == "openai":
            import openai
            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            raw = resp.choices[0].message.content
        else:
            return None

        data = json.loads(raw)
        rules = [TechnicalRule(**r) for r in data.get("generated_rules", [])]
        return AnalysisResult(
            summary=data.get("summary", ""),
            extracted_policies=data.get("extracted_policies", []),
            generated_rules=rules,
            confidence_score=0.92,
        )
    except Exception:
        return None


def _rule_based_analyze(policy_text: str) -> AnalysisResult:
    """
    Deterministic keyword extractor.
    Confidence is derived from match ratio — no random values.
    """
    text = policy_text.lower()
    extracted: List[str] = []
    rules: List[TechnicalRule] = []

    for entry in _RULE_LIBRARY:
        if any(kw in text for kw in entry["keywords"]):
            extracted.append(entry["extracted"])
            rules.append(TechnicalRule(
                policy_id=entry["policy_id"],
                rule_name=entry["rule_name"],
                technical_implementation=entry["technical_implementation"],
                severity=entry["severity"],
            ))

    if not extracted:
        extracted.append("No specific technical controls identified in this text.")

    # Confidence: scales with number of matched rules (max ~0.90 at 5+ matches)
    confidence = min(0.90, 0.50 + len(rules) * 0.08)

    return AnalysisResult(
        summary=(
            f"Analyzed {len(policy_text)} characters. "
            f"Identified {len(rules)} technical control requirement(s)."
        ),
        extracted_policies=extracted,
        generated_rules=rules,
        confidence_score=round(confidence, 2),
    )


@router.post("/analyze")
async def analyze_policy(request: PolicyAnalysisRequest):
    """
    Analyzes unstructured policy text and generates technical compliance rules.
    Uses platform LLM when configured; otherwise applies deterministic rule matching.
    """
    await asyncio.sleep(0)  # yield to event loop

    result = await _llm_analyze(request.policy_text)
    if result is not None:
        return result

    return _rule_based_analyze(request.policy_text)
