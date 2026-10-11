import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class DataGovernanceService:
    def __init__(self, db=None):
        self.db = db
        self.pii_patterns = {
            "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "ssn": r"\d{3}-\d{2}-\d{4}",
            "credit_card": r"\b(?:\d{4}[- ]?){3}\d{4}\b",
            "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        }

    def scan_for_pii(self, text: str) -> List[str]:
        """Detect PII types present in text."""
        return [pii_type for pii_type, pattern in self.pii_patterns.items()
                if re.search(pattern, str(text))]

    def classify_data(self, data: Dict[str, Any]) -> str:
        """Classify data record based on content."""
        pii_found = self.scan_for_pii(str(data.values()))
        if "ssn" in pii_found or "credit_card" in pii_found:
            return "RESTRICTED"
        if "email" in pii_found or "phone" in pii_found:
            return "CONFIDENTIAL"
        return "INTERNAL"

    async def get_data_catalog(self) -> List[Dict[str, Any]]:
        """Return the catalog entries stored in the DB (empty until some are added)."""
        if self.db is not None:
            try:
                return await self.db.data_catalog.find({}, {"_id": 0}).to_list(length=500)
            except Exception as exc:
                logger.warning("data_catalog DB query failed: %s", exc)
        return []

    async def add_catalog_entry(self, entry: Dict[str, Any]) -> None:
        """Persist a new catalog entry to DB."""
        if self.db is not None:
            try:
                await self.db.data_catalog.insert_one({k: v for k, v in entry.items() if k != "_id"})
                return
            except Exception as exc:
                logger.warning("data_catalog insert failed: %s", exc)


# Lightweight sync-compatible instance for callers that don't have a db ref yet.
# Callers with a db should instantiate DataGovernanceService(db) directly.
governance_service = DataGovernanceService()
