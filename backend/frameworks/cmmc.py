"""CMMC 2.0 Level 2 — Cybersecurity Maturity Model Certification."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "cmmc_l2"
FRAMEWORK_NAME = "CMMC 2.0 Level 2"
FRAMEWORK_VERSION = "2.0"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """DB eval enhanced with MFA, vulnerability-scan, and access-control checks."""
    results = await evaluate_from_db(db, "cmmc_l2")
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    total_users = await db.users.count_documents({})
    mfa_users = await db.users.count_documents({"mfa_enabled": True})
    mfa_pct = round(mfa_users / total_users * 100) if total_users else 0

    vuln_scans = await db.agent_vulnerability_scans.count_documents(
        {"scanned_at": {"$gte": cutoff_30d}}
    )
    roles = await db.roles.count_documents({})
    users_with_role = await db.users.count_documents({"role": {"$exists": True, "$ne": None}})

    for r in results:
        theme = r.get("theme", "").lower()
        if "identification" in theme or "authentication" in theme:
            r["mfa_evidence"] = f"MFA: {mfa_pct}% ({mfa_users}/{total_users})"
            if mfa_pct >= 90 and r["status"] != "pass":
                r["status"] = "pass"
            elif mfa_pct >= 50 and r["status"] not in ("pass",):
                r["status"] = "partial"
        if "vulnerability" in theme or "risk assessment" in theme:
            r["vuln_evidence"] = f"{vuln_scans} scans in last 30 days"
            if vuln_scans > 0 and r["status"] != "pass":
                r["status"] = "pass"
        if "access control" in theme:
            r["ac_evidence"] = f"{roles} roles; {users_with_role} users assigned"
            if roles > 0 and users_with_role > 0 and r["status"] != "pass":
                r["status"] = "pass"
    return results
