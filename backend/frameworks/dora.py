"""DORA (EU) — Digital Operational Resilience Act 2022/2554."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "dora"
FRAMEWORK_NAME = "DORA (EU)"
FRAMEWORK_VERSION = "2022/2554"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB

_RESILIENCE_THEMES = {"ict resilience", "backup", "recovery", "business continuity", "availability"}
_IR_THEMES = {"incident", "incident management", "incident reporting"}


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """DB eval enhanced with backup-recency and incident-response checks."""
    results = await evaluate_from_db(db, "dora")
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    backup_count = await db.backups.count_documents({"created_at": {"$gte": cutoff_30d}})
    incident_count = await db.incidents.count_documents({})
    playbook_count = await db.playbooks.count_documents({})

    for r in results:
        theme = r.get("theme", "").lower()
        if any(t in theme for t in _RESILIENCE_THEMES):
            r["backup_evidence"] = f"{backup_count} backups in last 30 days"
            if backup_count > 0 and r["status"] != "pass":
                r["status"] = "pass"
        if any(t in theme for t in _IR_THEMES):
            r["ir_evidence"] = f"{incident_count} incidents; {playbook_count} playbooks"
            if playbook_count > 0 and r["status"] != "pass":
                r["status"] = "pass" if incident_count > 0 else "partial"
    return results
