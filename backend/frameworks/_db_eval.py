"""Shared DB-driven framework evaluator — reads seeded compliance_frameworks data."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

_STATUS_MAP = {
    "Implemented":     "pass",
    "In Progress":     "partial",
    "At Risk":         "fail",
    "Not Implemented": "fail",
    "Not Started":     "not_applicable",
}


async def evaluate_from_db(db, framework_id: str) -> List[Dict[str, Any]]:
    """Return pass/partial/fail results by reading the seeded compliance_frameworks doc."""
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    fw = await db.compliance_frameworks.find_one({"id": framework_id})
    if not fw:
        return []
    results = []
    for ctrl in fw.get("controls", []):
        db_status = ctrl.get("status", "Not Implemented")
        status = _STATUS_MAP.get(db_status, "not_applicable")
        # Upgrade to pass if recent evidence exists
        ev_count = await db.asset_compliance.count_documents({
            "controlId": ctrl["id"],
            "status": "Compliant",
            "lastUpdated": {"$gte": cutoff_30d},
        })
        if ev_count > 0 and status != "pass":
            status = "pass"
        results.append({
            "id": ctrl["id"],
            "title": ctrl["name"],
            "description": ctrl.get("description", ""),
            "theme": ctrl.get("category", "General"),
            "status": status,
            "evidence_source": "db_seed",
            "evidence_count": ev_count,
            "last_reviewed": ctrl.get("lastReviewed", ""),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        })
    return results
