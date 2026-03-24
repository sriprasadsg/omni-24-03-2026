
import re
import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)

class PIIService:
    """
    Service for detecting and redacting IPII (Personally Identifiable Information).
    Detects: Email, SSN, Credit Cards.
    """
    
    PATTERNS = {
        'EMAIL': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'SSN': r'\b\d{3}-\d{2}-\d{4}\b',
        'CREDIT_CARD': r'\b(?:\d{4}[-\s]?){3}\d{4}\b' # Simple regex for demo
    }
    
    @staticmethod
    def redact(text: str) -> Tuple[str, List[str]]:
        """
        Redacts PII from text.
        Returns: (redacted_text, list_of_redactions_made)
        """
        redactions = []
        redacted_text = text
        
        for pii_type, pattern in PIIService.PATTERNS.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                original = match.group()
                redactions.append(f"{pii_type}: {original}")
                
        # Apply redactions
        for pii_type, pattern in PIIService.PATTERNS.items():
            redacted_text = re.sub(pattern, f"[REDACTED_{pii_type}]", redacted_text)
            
        if redactions:
            logger.info(f"Redacted {len(redactions)} PII items")
            
        return redacted_text, redactions

    @staticmethod
    def contains_pii(text: str) -> bool:
        """Check if text contains any PII"""
        for pattern in PIIService.PATTERNS.values():
            if re.search(pattern, text):
                return True
        return False
