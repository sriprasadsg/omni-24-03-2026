import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

class DataGovernanceService:
    def __init__(self):
        # Regex patterns for PII detection
        self.pii_patterns = {
            "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "ssn": r"\d{3}-\d{2}-\d{4}",
            "credit_card": r"\b(?:\d{4}[- ]?){3}\d{4}\b",
            "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"
        }
        
        # Simulated Data Catalog
        self.catalog = [
            {"name": "customer_logs", "classification": "CONFIDENTIAL", "owner": "Ops Team", "retention_days": 90},
            {"name": "public_metrics", "classification": "PUBLIC", "owner": "Engineering", "retention_days": 365},
            {"name": "employee_records", "classification": "RESTRICTED", "owner": "HR", "retention_days": 2555},
            {"name": "security_events", "classification": "INTERNAL", "owner": "SecOps", "retention_days": 180}
        ]

    def scan_for_pii(self, text: str) -> List[str]:
        """Detect PII types present in text"""
        detected = []
        for pii_type, pattern in self.pii_patterns.items():
            if re.search(pattern, str(text)):
                detected.append(pii_type)
        return detected

    def classify_data(self, data: Dict[str, Any]) -> str:
        """Classify data record based on content"""
        # Convert dictionary values to string for scanning
        content_str = str(data.values())
        pii_found = self.scan_for_pii(content_str)
        
        if "ssn" in pii_found or "credit_card" in pii_found:
            return "RESTRICTED"
        elif "email" in pii_found or "phone" in pii_found:
            return "CONFIDENTIAL"
        else:
            return "INTERNAL" # Default to internal

    def get_data_catalog(self) -> List[Dict[str, Any]]:
        return self.catalog

    def add_catalog_entry(self, entry: Dict[str, Any]):
        self.catalog.append(entry)

# Global instance
governance_service = DataGovernanceService()
