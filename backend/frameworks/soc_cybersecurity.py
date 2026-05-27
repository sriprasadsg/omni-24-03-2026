"""SOC for Cybersecurity — Entity-level cybersecurity risk management reporting."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "soc_cybersecurity"
FRAMEWORK_NAME = "SOC for Cybersecurity"
FRAMEWORK_VERSION = "2017"
CONTROLS: List[Dict[str, Any]] = []  # loaded from DB


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """DB eval enhanced with live incident-response and playbook checks."""
    results = await evaluate_from_db(db, "soc_cybersecurity")
    has_incidents = await db.incidents.count_documents({}) > 0
    has_playbooks = await db.playbooks.count_documents({}) > 0
    has_events = await db.security_events.count_documents({}) > 0

    for r in results:
        if r.get("theme", "").lower() in ("incident response", "incident management"):
            if has_incidents and has_playbooks:
                r["status"] = "pass"
                r["ir_evidence"] = "incident tracker and playbooks both present"
            elif has_playbooks:
                r["status"] = "partial"
                r["ir_evidence"] = "playbooks present; no incidents recorded"
        if r.get("theme", "").lower() in ("threat detection", "monitoring"):
            if has_events:
                r["status"] = "pass"
                r["monitoring_evidence"] = "security events present"
    return results
