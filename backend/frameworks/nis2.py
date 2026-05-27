"""NIS2 Directive (EU) 2022/2555 — Network and Information Security."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "nis2"
FRAMEWORK_NAME = "NIS2 Directive (EU)"
FRAMEWORK_VERSION = "2022/2555"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB

_INCIDENT_THEMES = {"incident", "incident handling", "incident reporting", "incident management"}
_SUPPLY_THEMES   = {"supply chain", "third party", "supplier", "vendor"}
_AUTH_THEMES     = {"authentication", "access control", "identity"}


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """DB eval enhanced with incident, supply-chain, and MFA checks."""
    results = await evaluate_from_db(db, "nis2")

    incident_count = await db.incidents.count_documents({})
    vendor_count   = await db.vendors.count_documents({})
    total_users    = await db.users.count_documents({})
    mfa_users      = await db.users.count_documents({"mfa_enabled": True})
    mfa_pct        = round(mfa_users / total_users * 100) if total_users else 0

    for r in results:
        theme = r.get("theme", "").lower()
        if any(t in theme for t in _INCIDENT_THEMES):
            r["incident_evidence"] = f"{incident_count} incidents recorded"
            if incident_count > 0 and r["status"] != "pass":
                r["status"] = "pass"
        if any(t in theme for t in _SUPPLY_THEMES):
            r["supply_evidence"] = f"{vendor_count} vendors tracked"
            if vendor_count > 0 and r["status"] != "pass":
                r["status"] = "pass"
        if any(t in theme for t in _AUTH_THEMES):
            r["mfa_evidence"] = f"MFA: {mfa_pct}% ({mfa_users}/{total_users})"
            if mfa_pct >= 90 and r["status"] != "pass":
                r["status"] = "pass"
            elif mfa_pct >= 50 and r["status"] not in ("pass",):
                r["status"] = "partial"
    return results
