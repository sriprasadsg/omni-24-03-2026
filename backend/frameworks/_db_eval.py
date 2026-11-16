"""Shared DB-driven framework evaluator for the frameworks whose controls live in compliance_frameworks.

The seeded control status ("Implemented" on every control of the 22 seeded frameworks) is not evidence and is
not read. A control is judged by its asset_compliance rows from the last 30 days, the worst asset deciding:
Non-Compliant -> fail, Warning -> partial, Compliant -> pass. With no recent row it is "not_assessed", which the
framework score leaves out like not_applicable (compliance_frameworks_endpoints._score).
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from compliance_reporting_data import _score_status

_EVIDENCE_STATUS = {"Non-Compliant": "fail", "Warning": "partial", "Compliant": "pass"}
_RANK = {"fail": 0, "partial": 1, "pass": 2}


async def evaluate_from_db(db, framework_id: str) -> List[Dict[str, Any]]:
    """One result per control of the seeded doc, its status from recent asset evidence only (see the module)."""
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    fw = await db.compliance_frameworks.find_one({"id": framework_id})
    if not fw:
        return []
    controls = [c for c in fw.get("controls", []) if c.get("id")]
    worst: Dict[str, str] = {}
    counts: Dict[str, int] = {}
    async for row in db.asset_compliance.find(
            {"controlId": {"$in": [c["id"] for c in controls]}, "lastUpdated": {"$gte": cutoff_30d}},
            {"_id": 0, "controlId": 1, "status": 1}):
        cid = row.get("controlId")
        status = _EVIDENCE_STATUS[_score_status(row.get("status", ""))]
        counts[cid] = counts.get(cid, 0) + 1
        if cid not in worst or _RANK[status] < _RANK[worst[cid]]:
            worst[cid] = status
    results = []
    for ctrl in controls:
        results.append({
            "id": ctrl["id"],
            "title": ctrl["name"],
            "description": ctrl.get("description", ""),
            "theme": ctrl.get("category", "General"),
            "status": worst.get(ctrl["id"], "not_assessed"),
            "evidence_source": "asset_compliance",
            "evidence_count": counts.get(ctrl["id"], 0),
            "last_reviewed": ctrl.get("lastReviewed", ""),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        })
    return results
