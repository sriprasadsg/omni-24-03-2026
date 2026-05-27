"""GDPR — General Data Protection Regulation (EU) 2016/679."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "gdpr"
FRAMEWORK_NAME = "General Data Protection Regulation (GDPR)"
FRAMEWORK_VERSION = "2018"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB

_PRIVACY_THEMES = {"data subject rights", "consent", "data protection", "privacy", "lawful basis"}


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """DB eval enhanced with DPA, consent, and privacy-record evidence checks."""
    results = await evaluate_from_db(db, "gdpr")

    dpa_count = await db.data_processing_agreements.count_documents({})
    gdpr_count = await db.gdpr_records.count_documents({})
    consent_count = await db.consent_records.count_documents({})

    for r in results:
        theme = r.get("theme", "").lower()
        if any(t in theme for t in _PRIVACY_THEMES):
            if consent_count > 0 or gdpr_count > 0:
                r["status"] = "pass"
                r["privacy_evidence"] = (
                    f"{consent_count} consent records; {gdpr_count} GDPR records"
                )
        if "data processing" in theme or "processor" in theme:
            if dpa_count > 0:
                r["status"] = "pass"
                r["dpa_evidence"] = f"{dpa_count} data processing agreements"
    return results
