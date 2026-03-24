from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import time
import random

router = APIRouter(prefix="/api/compliance_oracle", tags=["Compliance Oracle"])

class PolicyAnalysisRequest(BaseModel):
    policy_text: str

class TechnicalRule(BaseModel):
    policy_id: str
    rule_name: str
    technical_implementation: str  # e.g., "bucket_policy: ..."
    severity: str

class AnalysisResult(BaseModel):
    summary: str
    extracted_policies: List[str]
    generated_rules: List[TechnicalRule]
    confidence_score: float

@router.post("/analyze")
async def analyze_policy(request: PolicyAnalysisRequest):
    """
    Analyzes unstructured policy text and generates technical compliance rules.
    """
    # Simulate LLM processing latency
    time.sleep(2.0)
    
    text = request.policy_text.lower()
    extracted = []
    rules = []
    
    # Mock NLP/LLM Logic
    if "encrypt" in text or "encryption" in text:
        extracted.append("Requirement: Data Encryption at Rest")
        rules.append(TechnicalRule(
            policy_id="POL-001",
            rule_name="Enforce S3 Encryption",
            technical_implementation="s3_bucket.server_side_encryption_configuration.rule.apply_server_side_encryption_by_default.sse_algorithm = 'AES256'",
            severity="High"
        ))
        
    if "retention" in text:
        extracted.append("Requirement: Data Retention Policy")
        rules.append(TechnicalRule(
            policy_id="POL-002",
            rule_name="Log Retention 90 Days",
            technical_implementation="cloudwatch_log_group.retention_in_days >= 90",
            severity="Medium"
        ))
        
    if "mfa" in text or "multi-factor" in text:
        extracted.append("Requirement: Multi-Factor Authentication")
        rules.append(TechnicalRule(
            policy_id="POL-003",
            rule_name="Enforce IAM MFA",
            technical_implementation="aws_iam_account_password_policy.require_mfa = true",
            severity="Critical"
        ))

    if not extracted:
        extracted.append("No specific technical controls extracted.")
        
    return AnalysisResult(
        summary=f"Analyzed {len(text)} chars. Identified {len(rules)} technical controls.",
        extracted_policies=extracted,
        generated_rules=rules,
        confidence_score=random.uniform(0.85, 0.99)
    )
