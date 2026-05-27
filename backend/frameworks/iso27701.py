"""ISO/IEC 27701:2019 — Privacy Information Management System (extension to ISO 27001)."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "iso27701"
FRAMEWORK_NAME = "ISO/IEC 27701:2019"
FRAMEWORK_VERSION = "2019"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB

_PRIVACY_THEMES = {"privacy", "data subject", "consent", "pii", "personal data", "data protection"}
_DPA_THEMES     = {"data processing", "processor", "controller", "third party"}


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """DB eval enhanced with DPA, privacy-record, and consent checks."""
    results = await evaluate_from_db(db, "iso27701")

    dpa_count     = await db.data_processing_agreements.count_documents({})
    privacy_count = await db.privacy_records.count_documents({})
    if privacy_count == 0:
        privacy_count = await db.gdpr_records.count_documents({})
    consent_count = await db.consent_records.count_documents({})

    for r in results:
        theme = r.get("theme", "").lower()
        if any(t in theme for t in _PRIVACY_THEMES):
            r["privacy_evidence"] = (
                f"{privacy_count} privacy records; {consent_count} consent records"
            )
            if (privacy_count > 0 or consent_count > 0) and r["status"] != "pass":
                r["status"] = "pass"
        if any(t in theme for t in _DPA_THEMES):
            r["dpa_evidence"] = f"{dpa_count} data processing agreements"
            if dpa_count > 0 and r["status"] != "pass":
                r["status"] = "pass"
    return results
