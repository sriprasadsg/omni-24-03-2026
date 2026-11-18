"""What analysts do to alerts from the SOC console and Alert Management.

Every change is scoped to the caller's tenant (``scope``; None is a Super Admin's platform view),
records who did it and when (the console's response times come from ``acknowledgedAt`` and
``closedAt``), and goes to the audit ledger. Nothing is deleted: Alert Management's "archive" only
hides an alert. Cases are created here, server side, so their tenant is the alert's.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import audit_ledger
from database import get_database
from soc_alerts import HIDDEN, RESOLUTIONS
from soc_service import STATUS_QUERY, scope_filter, view

logger = logging.getLogger(__name__)

ACTIONS = ("acknowledge", "assign", "unassign", "close", "reopen", "archive")
CLOSE_RESOLUTIONS = tuple(r for r in RESOLUTIONS if r != "approved")  # approval goes through approve_ai
BULK_ACTIONS = ("acknowledge", "close", "archive")
PAST = {"acknowledge": "acknowledged", "assign": "assigned", "unassign": "unassigned", "close": "closed",
        "reopen": "reopened", "archive": "archived"}
MAX_BULK = 200
PROCESS_IN_TITLE = re.compile(r":\s*(.+)$")


class ActionError(ValueError):
    """A request the alert's current state does not allow (HTTP 409) or that names no alert (404)."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _actor(user: Any) -> str:
    return getattr(user, "username", None) or getattr(user, "email", None) or "unknown"


def change_for(action: str, user: Any, now: str, resolution: Optional[str] = None, note: Optional[str] = None,
               assignee: Optional[str] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """(status precondition, update pipeline) for one action; raises ActionError on a bad request."""
    who = _actor(user)
    first_response = {"acknowledgedAt": {"$ifNull": ["$acknowledgedAt", now]},
                      "acknowledgedBy": {"$ifNull": ["$acknowledgedBy", who]}}
    if action == "acknowledge":
        return ({"$in": STATUS_QUERY["open"]},
                [{"$set": {"status": "acknowledged", "acknowledged": True, **first_response}}])
    if action == "assign":
        return ({"$in": STATUS_QUERY["active"]}, [{"$set": {"assignee": (assignee or who)[:120]}}])
    if action == "unassign":
        return ({"$in": STATUS_QUERY["active"]}, [{"$unset": "assignee"}])
    if action == "close":
        if resolution not in CLOSE_RESOLUTIONS:
            raise ActionError(f"resolution must be one of: {', '.join(CLOSE_RESOLUTIONS)}", 400)
        return ({"$in": STATUS_QUERY["active"]},
                [{"$set": {"status": "closed", "resolution": resolution, "closedAt": now, "closedBy": who,
                           "closeNote": (note or "")[:2000], "acknowledged": True, **first_response}}])
    if action == "reopen":
        return ({"$in": STATUS_QUERY["closed"]},
                [{"$set": {"status": "open", "acknowledged": False}},
                 {"$unset": ["resolution", "closedAt", "closedBy", "closeNote"]}])
    if action == "archive":
        return ({"$nin": list(HIDDEN)}, [{"$set": {"status": "archived", "archivedAt": now, "archivedBy": who}}])
    raise ActionError(f"action must be one of: {', '.join(ACTIONS)}", 400)


async def _find(db, scope: Optional[str], alert_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The alert and its collection: security_alerts first, then the legacy alerts."""
    for name in ("security_alerts", "alerts"):
        doc = await db[name].find_one({"id": alert_id, **scope_filter(scope)}, {"_id": 0})
        if doc:
            return doc, name
    return None, None


async def apply_action(scope: Optional[str], alert_id: str, action: str, user: Any, resolution: Optional[str] = None,
                       note: Optional[str] = None, assignee: Optional[str] = None) -> Dict[str, Any]:
    db = get_database()
    precondition, update = change_for(action, user, _now(), resolution, note, assignee)
    doc, name = await _find(db, scope, alert_id)
    if not doc:
        raise ActionError("Alert not found", 404)
    result = await db[name].update_one({"id": alert_id, **scope_filter(scope), "status": precondition}, update)
    if result.matched_count == 0:
        raise ActionError(f"This alert can't be {PAST[action]} in its current state; refresh and try again")
    after, _ = await _find(db, scope, alert_id)
    await _audit(f"soc.alert.{action}", doc.get("tenantId"), user, alertId=alert_id, resolution=resolution)
    return view(after or doc, legacy=name == "alerts")


async def bulk_action(scope: Optional[str], ids: List[str], action: str, user: Any,
                      resolution: Optional[str] = None, note: Optional[str] = None) -> Dict[str, int]:
    if action not in BULK_ACTIONS:
        raise ActionError(f"bulk action must be one of: {', '.join(BULK_ACTIONS)}", 400)
    ids = list(dict.fromkeys(i for i in ids if isinstance(i, str) and i))[:MAX_BULK]
    db = get_database()
    precondition, update = change_for(action, user, _now(), resolution, note)
    matched = modified = 0
    for name in ("security_alerts", "alerts"):
        result = await db[name].update_many({"id": {"$in": ids}, **scope_filter(scope), "status": precondition}, update)
        matched += result.matched_count
        modified += result.modified_count
    await _audit(f"soc.alert.bulk_{action}", scope or "platform-admin", user, alertIds=ids, modified=modified,
                 resolution=resolution)
    return {"matched": matched, "modified": modified}


def _case_severity(severity: str) -> str:
    return severity.capitalize() if severity in ("critical", "high", "medium", "low") else "Low"


async def open_case(scope: Optional[str], alert_id: str, user: Any) -> Dict[str, Any]:
    """A security case for the alert (or the case it already has), and the alert acknowledged."""
    db = get_database()
    doc, name = await _find(db, scope, alert_id)
    if not doc:
        raise ActionError("Alert not found", 404)
    if doc.get("caseId"):
        existing = await db.security_cases.find_one({"id": doc["caseId"], **scope_filter(scope)}, {"_id": 0})
        if existing:
            return {"case": existing, "created": False}
    alert = view(doc, legacy=name == "alerts")
    now = _now()
    case = {
        "id": f"case-{uuid.uuid4()}",
        "tenantId": alert["tenantId"],
        "title": f"Case: {alert['title']}"[:300],
        "status": "New",
        "severity": _case_severity(alert["severity"]),
        "owner": _actor(user),
        "createdAt": now, "updatedAt": now,
        "relatedEvents": [{
            "id": alert["id"], "tenantId": alert["tenantId"], "timestamp": alert["createdAt"],
            "severity": _case_severity(alert["severity"]), "description": alert["description"] or alert["title"],
            "type": alert["typeLabel"], "source": {"ip": "", "hostname": alert["hostname"] or alert["agentId"] or ""},
            "details": alert["evidence"],
        }],
        "comments": [], "enrichmentData": [], "alertIds": [alert["id"]],
    }
    await db.security_cases.insert_one({**case, "_id": case["id"]})
    case.pop("_id", None)
    who = _actor(user)
    await db[name].update_one({"id": alert_id, **scope_filter(scope)}, [{"$set": {
        "caseId": case["id"],
        "status": {"$cond": [{"$in": [{"$ifNull": ["$status", "open"]}, STATUS_QUERY["open"]]}, "acknowledged", "$status"]},
        "acknowledgedAt": {"$ifNull": ["$acknowledgedAt", now]}, "acknowledgedBy": {"$ifNull": ["$acknowledgedBy", who]},
    }}])
    await _audit("soc.alert.case", alert["tenantId"], user, alertId=alert_id, caseId=case["id"])
    return {"case": case, "created": True}


def process_of(doc: Dict[str, Any]) -> Optional[str]:
    name = doc.get("process") or ((PROCESS_IN_TITLE.search(doc.get("title") or "") or [None, None])[1])
    name = str(name or "").strip().lower()
    return None if name in ("", "unknown", "none") else name


async def approve_ai(scope: Optional[str], alert_id: str, user: Any, all_endpoints: bool = False,
                     reason: Optional[str] = None) -> Dict[str, Any]:
    """Approve the AI process an alert is about (on its endpoint, or all the tenant's) and close its alerts."""
    db = get_database()
    doc, _ = await _find(db, scope, alert_id)
    if not doc:
        raise ActionError("Alert not found", 404)
    process = process_of(doc)
    if doc.get("type") != "shadow_ai_process" or not process:
        raise ActionError("Only an AI process alert that names its process can be approved", 400)
    tenant = doc.get("tenantId")
    agent = None if all_endpoints else doc.get("agent_id")
    now, who = _now(), _actor(user)
    host = None
    if agent:
        found = await db.agents.find_one({"id": agent, **scope_filter(scope)}, {"_id": 0, "hostname": 1})
        host = (found or {}).get("hostname")
    approval = {"id": str(uuid.uuid4()), "tenantId": tenant, "process": process, "agentId": agent, "hostname": host,
                "reason": (reason or "")[:500], "approvedBy": who, "approvedAt": now}
    await db.approved_ai_processes.update_one(
        {"tenantId": tenant, "process": process, "agentId": agent}, {"$setOnInsert": approval}, upsert=True)
    match = {"tenantId": tenant, "type": "shadow_ai_process", "status": {"$in": STATUS_QUERY["active"]},
             "$or": [{"process": process}, {"title": {"$regex": f":\\s*{re.escape(process)}$", "$options": "i"}}]}
    if agent:
        match["agent_id"] = agent
    result = await db.security_alerts.update_many(match, [{"$set": {
        "status": "closed", "resolution": "approved", "closedAt": now, "closedBy": who,
        "closeNote": (reason or f"{process} approved")[:2000], "acknowledged": True,
        "acknowledgedAt": {"$ifNull": ["$acknowledgedAt", now]}, "acknowledgedBy": {"$ifNull": ["$acknowledgedBy", who]},
    }}])
    await _audit("soc.ai_process.approve", tenant, user, process=process, agentId=agent, closed=result.modified_count)
    stored = await db.approved_ai_processes.find_one({"tenantId": tenant, "process": process, "agentId": agent}, {"_id": 0})
    return {"approval": stored or approval, "closed": result.modified_count}


async def list_approvals(scope: Optional[str]) -> List[Dict[str, Any]]:
    db = get_database()
    return await db.approved_ai_processes.find(scope_filter(scope), {"_id": 0}).sort("approvedAt", -1).to_list(500)


async def revoke_approval(scope: Optional[str], approval_id: str, user: Any) -> None:
    db = get_database()
    found = await db.approved_ai_processes.find_one({"id": approval_id, **scope_filter(scope)}, {"_id": 0})
    if not found:
        raise ActionError("Approval not found", 404)
    await db.approved_ai_processes.delete_one({"id": approval_id, **scope_filter(scope)})
    await _audit("soc.ai_process.revoke", found.get("tenantId"), user, process=found.get("process"),
                 agentId=found.get("agentId"))


async def _audit(action: str, tenant_id: Optional[str], user: Any, **fields: Any) -> None:
    try:
        await audit_ledger.event(action, tenant_id or "platform-admin",
                                 actor={"email": _actor(user), "role": getattr(user, "role", None),
                                        "tenantId": getattr(user, "tenant_id", None)}, **fields)
    except Exception as e:  # the ledger spools on failure; never undo the analyst's change over it
        logger.warning("SOC audit entry %s not recorded: %s", action, e)
