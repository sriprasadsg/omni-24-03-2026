"""SWIFT CSP — Customer Security Programme Controls Framework."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "swift_csp"
FRAMEWORK_NAME = "SWIFT Customer Security Programme (CSP)"
FRAMEWORK_VERSION = "CSCF v2024"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB

_MFA_THEMES       = {"authentication", "access control", "identity", "privileged access"}
_VULN_THEMES      = {"vulnerability", "patch", "scanning", "software integrity"}
_IR_THEMES        = {"incident", "incident response", "cyber incident"}
_VENDOR_THEMES    = {"vendor", "third party", "supplier", "outsourcing"}


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """DB eval enhanced with MFA, vuln-scan, IR playbook, and vendor-risk checks."""
    results = await evaluate_from_db(db, "swift_csp")
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    total_users  = await db.users.count_documents({})
    mfa_users    = await db.users.count_documents({"mfa_enabled": True})
    mfa_pct      = round(mfa_users / total_users * 100) if total_users else 0
    vuln_scans   = await db.agent_vulnerability_scans.count_documents(
        {"scanned_at": {"$gte": cutoff_30d}}
    )
    playbooks    = await db.playbooks.count_documents({})
    vendor_count = await db.vendors.count_documents({})

    for r in results:
        theme = r.get("theme", "").lower()
        if any(t in theme for t in _MFA_THEMES):
            r["mfa_evidence"] = f"MFA: {mfa_pct}% ({mfa_users}/{total_users})"
            if mfa_pct >= 90 and r["status"] != "pass":
                r["status"] = "pass"
            elif mfa_pct >= 50 and r["status"] not in ("pass",):
                r["status"] = "partial"
        if any(t in theme for t in _VULN_THEMES):
            r["vuln_evidence"] = f"{vuln_scans} vulnerability scans in last 30 days"
            if vuln_scans > 0 and r["status"] != "pass":
                r["status"] = "pass"
        if any(t in theme for t in _IR_THEMES):
            r["ir_evidence"] = f"{playbooks} IR playbooks"
            if playbooks > 0 and r["status"] != "pass":
                r["status"] = "pass"
        if any(t in theme for t in _VENDOR_THEMES):
            r["vendor_evidence"] = f"{vendor_count} vendors tracked"
            if vendor_count > 0 and r["status"] != "pass":
                r["status"] = "pass"
    return results
