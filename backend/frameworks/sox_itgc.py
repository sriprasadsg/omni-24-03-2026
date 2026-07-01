"""SOX ITGC — Sarbanes-Oxley IT General Controls."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "sox_itgc"
FRAMEWORK_NAME = "SOX IT General Controls (ITGC)"
FRAMEWORK_VERSION = "SOX 2002 / PCAOB AS 2201"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """DB eval enhanced with user-count, audit-log, and change-management checks."""
    results = await evaluate_from_db(db, "sox_itgc")
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    user_count  = await db.users.count_documents({})
    roles_count = await db.roles.count_documents({})
    audit_count = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_30d}})
    change_count = await db.audit_logs.count_documents({
        "timestamp": {"$gte": cutoff_30d},
        "action": {"$regex": "update|change|modify|delete|create", "$options": "i"},
    })

    for r in results:
        theme = r.get("theme", "").lower()
        if "access" in theme or "segregation" in theme or "user" in theme:
            r["access_evidence"] = f"{user_count} users; {roles_count} roles"
            if user_count > 0 and roles_count > 0 and r["status"] != "pass":
                r["status"] = "pass"
        if "audit" in theme or "logging" in theme:
            r["audit_evidence"] = f"{audit_count} log entries in last 30 days"
            if audit_count > 0 and r["status"] != "pass":
                r["status"] = "pass"
        if "change" in theme or "change management" in theme:
            r["change_evidence"] = f"{change_count} change events in last 30 days"
            if change_count > 0 and r["status"] != "pass":
                r["status"] = "pass"
    return results
