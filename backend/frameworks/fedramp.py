"""FedRAMP Moderate — Federal Risk and Authorization Management Program."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "fedramp_moderate"
FRAMEWORK_NAME = "FedRAMP Moderate"
FRAMEWORK_VERSION = "Rev 5"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """DB eval with additional MFA, audit-log, and vuln-scan checks."""
    results = await evaluate_from_db(db, "fedramp_moderate")
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    total_users = await db.users.count_documents({})
    mfa_users = await db.users.count_documents({"mfa_enabled": True})
    mfa_pct = round(mfa_users / total_users * 100) if total_users else 0

    audit_recent = await db.audit_logs.count_documents({"timestamp": {"$gte": cutoff_30d}})
    vuln_scans = await db.agent_vulnerability_scans.count_documents(
        {"scanned_at": {"$gte": cutoff_30d}}
    )

    for r in results:
        theme = r.get("theme", "").lower()
        if "identification" in theme or "authentication" in theme or "access control" in theme:
            if mfa_pct >= 90:
                r["status"] = "pass"
            elif mfa_pct >= 50:
                r["status"] = "partial"
            r["mfa_evidence"] = f"MFA coverage: {mfa_pct}% ({mfa_users}/{total_users})"
        if "audit" in theme or "accountability" in theme:
            r["audit_evidence"] = f"{audit_recent} audit log entries in last 30 days"
            if audit_recent > 0 and r["status"] != "pass":
                r["status"] = "partial"
        if "vulnerability" in theme or "risk assessment" in theme:
            r["vuln_evidence"] = f"{vuln_scans} vulnerability scans in last 30 days"
            if vuln_scans > 0 and r["status"] != "pass":
                r["status"] = "pass"
    return results
