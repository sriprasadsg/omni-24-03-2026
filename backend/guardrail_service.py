import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from database import get_database
from tenant_context import get_tenant_id

# Regex patterns for PII
PII_PATTERNS = {
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d[ -]*?){13,16}\b",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b\+?1?\d{9,15}\b|(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b",
    "api_key": r"(?:api_key|secret|token|password)[\s:=]+['\"]?([A-Za-z0-9-_]{32,})['\"]?"
}

# Regex patterns for Prompt Injection
INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"system prompt override",
    r"you are now DAN",
    r"bypass security",
    r"ignore all constraints",
    r"reveal your system instructions",
    r"execute code"
]

class GuardrailResult:
    def __init__(self, passed: bool, findings: List[str], blocked_content: Optional[str] = None):
        self.passed = passed
        self.findings = findings
        self.blocked_content = blocked_content

class GuardrailService:
    @staticmethod
    async def scan_and_log(text: str, source: str = "generic") -> GuardrailResult:
        """
        Scans text for security policy violations and logs the result to MongoDB.
        """
        findings = []
        tenant_id = get_tenant_id()
        
        # PII Check
        for pii_type, pattern in PII_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                findings.append(f"PII Detected: {pii_type}")
        
        # Injection Check
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                findings.append(f"Prompt Injection Detected: '{pattern}'")
        
        result = GuardrailResult(passed=len(findings) == 0, findings=findings)
        
        # Log to Database
        db = get_database()
        if db:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "tenantId": tenant_id or "system",
                "source": source,
                "passed": result.passed,
                "findings": findings,
                # For safety, we only log the first 100 chars of suspect content
                "content_preview": text[:100] + ("..." if len(text) > 100 else ""),
                "severity": "High" if not result.passed else "Low"
            }
            try:
                await db.ai_security_logs.insert_one(log_entry)
            except Exception as e:
                logging.error(f"Failed to log guardrail result: {e}")
                
        return result

    @staticmethod
    def mask_pii(text: str) -> str:
        """
        Masks PII in text with placeholders.
        """
        masked_text = text
        for pii_type, pattern in PII_PATTERNS.items():
            masked_text = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", masked_text, flags=re.IGNORECASE)
        return masked_text

guardrail_service = GuardrailService()
