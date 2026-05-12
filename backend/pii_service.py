"""
PII Detection & Data Classification Service
Detects Personally Identifiable Information across 15+ pattern categories
and assigns a data sensitivity classification level.
"""
import re
import logging
from typing import Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

# ── Detection patterns ─────────────────────────────────────────────────────────
_PATTERNS: Dict[str, Dict[str, Any]] = {
    "EMAIL": {
        "pattern": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
        "classification": "confidential",
        "severity": "medium",
    },
    "SSN": {
        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
        "classification": "restricted",
        "severity": "high",
    },
    "CREDIT_CARD": {
        # Visa, MC, Amex, Discover
        "pattern": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})(?:[-\s]?\d{4})*\b",
        "classification": "restricted",
        "severity": "critical",
    },
    "CREDIT_CARD_SPACED": {
        "pattern": r"\b(?:\d{4}[-\s]){3}\d{4}\b",
        "classification": "restricted",
        "severity": "critical",
    },
    "PHONE_US": {
        "pattern": r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "classification": "confidential",
        "severity": "low",
    },
    "PHONE_INTL": {
        "pattern": r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b",
        "classification": "confidential",
        "severity": "low",
    },
    "PASSPORT": {
        "pattern": r"\b[A-Z]{1,2}\d{6,9}\b",
        "classification": "restricted",
        "severity": "high",
    },
    "DATE_OF_BIRTH": {
        # MM/DD/YYYY, DD-MM-YYYY, YYYY-MM-DD
        "pattern": r"\b(?:0[1-9]|1[0-2])[\/\-](?:0[1-9]|[12]\d|3[01])[\/\-](?:19|20)\d{2}\b|\b(?:19|20)\d{2}[\/\-](?:0[1-9]|1[0-2])[\/\-](?:0[1-9]|[12]\d|3[01])\b",
        "classification": "confidential",
        "severity": "medium",
    },
    "IP_ADDRESS": {
        "pattern": r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        "classification": "internal",
        "severity": "low",
    },
    "IBAN": {
        "pattern": r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b",
        "classification": "restricted",
        "severity": "high",
    },
    "DRIVERS_LICENSE": {
        # Generic US format — letter(s) + digits
        "pattern": r"\b[A-Z]{1,2}\d{5,8}\b",
        "classification": "restricted",
        "severity": "high",
    },
    "MEDICAL_RECORD": {
        # MRN patterns: MRN followed by alphanumeric
        "pattern": r"\bMRN[:\s]?[A-Z0-9]{5,12}\b",
        "classification": "restricted",
        "severity": "critical",
    },
    "NPI": {
        # National Provider Identifier (US healthcare) — 10 digits
        "pattern": r"\bNPI[:\s]?\d{10}\b",
        "classification": "restricted",
        "severity": "high",
    },
    "AWS_KEY": {
        "pattern": r"\bAKIA[0-9A-Z]{16}\b",
        "classification": "restricted",
        "severity": "critical",
    },
    "API_KEY_GENERIC": {
        # Generic high-entropy key-like strings
        "pattern": r"\b(?:api[_\-]?key|access[_\-]?token|secret)[_\-]?[=:\s]+['\"]?[A-Za-z0-9+/]{20,}['\"]?",
        "classification": "restricted",
        "severity": "critical",
    },
}

# Classification hierarchy (higher index = more sensitive)
_CLASSIFICATION_RANK = ["public", "internal", "confidential", "restricted", "top_secret"]


def _rank(classification: str) -> int:
    try:
        return _CLASSIFICATION_RANK.index(classification)
    except ValueError:
        return 0


class PIIService:
    """
    Detect and redact PII/sensitive data across 15+ pattern categories.
    Assigns a data sensitivity classification (public → restricted).
    """

    @staticmethod
    def scan(text: str) -> Dict[str, Any]:
        """
        Full PII scan: returns detections, redacted text, classification, and severity.
        """
        detections: List[Dict[str, str]] = []
        redacted = text
        highest_rank = 0
        max_severity = "none"
        _severity_rank = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

        for pii_type, meta in _PATTERNS.items():
            pattern = meta["pattern"]
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            for m in matches:
                detections.append({
                    "type": pii_type,
                    "value": m.group(),
                    "start": m.start(),
                    "end": m.end(),
                    "classification": meta["classification"],
                    "severity": meta["severity"],
                })
                if _rank(meta["classification"]) > highest_rank:
                    highest_rank = _rank(meta["classification"])
                if _severity_rank.get(meta["severity"], 0) > _severity_rank.get(max_severity, 0):
                    max_severity = meta["severity"]
            # Redact all matches
            redacted = re.sub(pattern, f"[{pii_type}_REDACTED]", redacted, flags=re.IGNORECASE)

        overall_classification = _CLASSIFICATION_RANK[highest_rank] if detections else "public"

        return {
            "has_pii": bool(detections),
            "detection_count": len(detections),
            "detections": detections,
            "redacted_text": redacted,
            "overall_classification": overall_classification,
            "max_severity": max_severity,
            "pii_types_found": list({d["type"] for d in detections}),
        }

    @staticmethod
    def redact(text: str) -> Tuple[str, List[str]]:
        """Legacy API — returns (redacted_text, list_of_redaction_labels)."""
        result = PIIService.scan(text)
        labels = [f"{d['type']}: {d['value']}" for d in result["detections"]]
        return result["redacted_text"], labels

    @staticmethod
    def contains_pii(text: str) -> bool:
        return PIIService.scan(text)["has_pii"]

    @staticmethod
    def classify_data(text: str) -> str:
        """Return the highest sensitivity classification found in the text."""
        return PIIService.scan(text)["overall_classification"]

    @staticmethod
    def get_pattern_catalog() -> List[Dict[str, str]]:
        """Return metadata about all registered PII pattern types."""
        return [
            {"type": k, "classification": v["classification"], "severity": v["severity"]}
            for k, v in _PATTERNS.items()
        ]
