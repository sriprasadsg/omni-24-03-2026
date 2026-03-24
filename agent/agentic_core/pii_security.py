
import re
import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)

class PIISecurityMiddleware:
    """
    Middleware for detecting and redacting IPII (Personally Identifiable Information)
    from data before it is sent to ANY LLM.
    Detects: Email, SSN, Credit Cards.
    """
    
    PATTERNS = {
        'EMAIL': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'SSN': r'\b\d{3}-\d{2}-\d{4}\b',
        'CREDIT_CARD': r'\b(?:\d{4}[-\s]?){3}\d{4}\b'
    }
    
    @staticmethod
    def sanitize(data: dict) -> dict:
        """
        Recursively redact PII from a dictionary or list.
        Returns a new sanitized object.
        """
        if isinstance(data, dict):
            return {k: PIISecurityMiddleware.sanitize(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [PIISecurityMiddleware.sanitize(item) for item in data]
        elif isinstance(data, str):
            return PIISecurityMiddleware.redact_text(data)
        else:
            return data

    @staticmethod
    def redact_text(text: str) -> str:
        """
        Redacts PII from text.
        """
        redacted_text = text
        for pii_type, pattern in PIISecurityMiddleware.PATTERNS.items():
            if re.search(pattern, redacted_text):
                # logger.warning(f"🛡️ PII Detected ({pii_type}). Redacting...")
                redacted_text = re.sub(pattern, f"[REDACTED_{pii_type}]", redacted_text)
        return redacted_text
