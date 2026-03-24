import re
from typing import List, Dict, Tuple, Optional

# Regex patterns for PII
PII_PATTERNS = {
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d[ -]*?){13,16}\b",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b\+?1?\d{9,15}\b|(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b"
}

# Regex patterns for Prompt Injection (Basic)
INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"system prompt override",
    r"you are now DAN",
    r"bypass security",
    r"ignore all constraints"
]

class ValidationResult:
    def __init__(self, passed: bool, findings: List[str]):
        self.passed = passed
        self.findings = findings

def scan_text(text: str, block_pii: bool = True, block_injection: bool = True) -> ValidationResult:
    """
    Scans text for PII and Prompt Injection.
    Returns ValidationResult.
    """
    findings = []
    
    if block_pii:
        for pii_type, pattern in PII_PATTERNS.items():
            if re.search(pattern, text):
                findings.append(f"PII Detected: {pii_type}")
                
    if block_injection:
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                findings.append(f"Prompt Injection Detected: '{pattern}'")
                
    return ValidationResult(passed=len(findings) == 0, findings=findings)
