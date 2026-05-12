"""
Incident War Room Service
Collaborative real-time incident management with timeline, tasks, evidence, and chat.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

INCIDENT_SEVERITIES = ["P1-Critical", "P2-High", "P3-Medium", "P4-Low"]
INCIDENT_STATUSES = ["open", "investigating", "contained", "eradicated", "recovering", "closed", "post_mortem"]
INCIDENT_TYPES = [
    "ransomware", "data_breach", "phishing", "insider_threat", "ddos",
    "malware", "unauthorized_access", "supply_chain", "zero_day", "other",
]


async def create_incident(tenant_id: str, created_by: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    now = datetime.now(timezone.utc)
    incident_number = await _next_incident_number(tenant_id)

    incident = {
        "id": str(uuid.uuid4()),
        "number": incident_number,
        "title": data.get("title", "Untitled Incident"),
        "description": data.get("description", ""),
        "severity": data.get("severity", "P2-High"),
        "type": data.get("type", "other"),
        "status": "open",
        "tenant_id": tenant_id,
        "created_by": created_by,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "closed_at": None,
        "incident_commander": data.get("incident_commander", created_by),
        "responders": data.get("responders", [created_by]),
        "affected_assets": data.get("affected_assets", []),
        "affected_users": data.get("affected_users", []),
        "attack_vector": data.get("attack_vector", ""),
        "ioc_list": data.get("ioc_list", []),
        "timeline": [
            {
                "id": str(uuid.uuid4()),
                "timestamp": now.isoformat(),
                "actor": created_by,
                "event_type": "incident_created",
                "description": f"Incident created: {data.get('title', '')}",
                "severity": data.get("severity", "P2-High"),
            }
        ],
        "tasks": [],
        "evidence_ids": [],
        "related_alert_ids": data.get("related_alert_ids", []),
        "chat_messages": [],
        "playbook_id": data.get("playbook_id"),
        "mttr_seconds": None,
        "containment_time": None,
        "eradication_time": None,
        "tags": data.get("tags", []),
    }

    await db.incidents.insert_one(incident)
    logger.info("[WarRoom] Incident %s created: %s", incident_number, incident["title"])
    return incident


async def _next_incident_number(tenant_id: str) -> str:
    db = get_database()
    count = await db.incidents.count_documents({"tenant_id": tenant_id})
    year = datetime.now().year
    return f"INC-{year}-{(count + 1):04d}"


async def update_incident_status(
    incident_id: str, actor: str, new_status: str, tenant_id: str, role: str, note: str = ""
) -> bool:
    db = get_database()
    query = {"id": incident_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    incident = await db.incidents.find_one(query)
    if not incident:
        return False

    now = datetime.now(timezone.utc)
    update = {
        "status": new_status,
        "updated_at": now.isoformat(),
    }

    if new_status == "closed":
        update["closed_at"] = now.isoformat()
        created_at = datetime.fromisoformat(incident["created_at"].replace("Z", "+00:00"))
        update["mttr_seconds"] = int((now - created_at).total_seconds())

    if new_status == "contained":
        update["containment_time"] = now.isoformat()
    if new_status == "eradicated":
        update["eradication_time"] = now.isoformat()

    timeline_entry = {
        "id": str(uuid.uuid4()),
        "timestamp": now.isoformat(),
        "actor": actor,
        "event_type": "status_change",
        "description": f"Status changed to {new_status}" + (f": {note}" if note else ""),
        "severity": incident.get("severity", ""),
    }

    await db.incidents.update_one(
        {"id": incident_id},
        {"$set": update, "$push": {"timeline": timeline_entry}},
    )
    return True


async def add_timeline_event(
    incident_id: str, actor: str, tenant_id: str, role: str, event: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    db = get_database()
    query = {"id": incident_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "actor": actor,
        "event_type": event.get("event_type", "note"),
        "description": event.get("description", ""),
        "severity": event.get("severity", ""),
        "iocs": event.get("iocs", []),
        "attachment_url": event.get("attachment_url", ""),
    }

    result = await db.incidents.update_one({"id": incident_id}, {"$push": {"timeline": entry}})
    if result.modified_count == 0:
        return None
    return entry


async def add_task(
    incident_id: str, actor: str, tenant_id: str, role: str, task: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    db = get_database()
    query = {"id": incident_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    new_task = {
        "id": str(uuid.uuid4()),
        "title": task.get("title", "New Task"),
        "description": task.get("description", ""),
        "assignee": task.get("assignee", actor),
        "priority": task.get("priority", "medium"),
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "due_at": task.get("due_at"),
        "completed_at": None,
    }

    result = await db.incidents.update_one({"id": incident_id}, {"$push": {"tasks": new_task}})
    if result.modified_count == 0:
        return None
    return new_task


async def add_chat_message(
    incident_id: str, actor: str, tenant_id: str, role: str, message: str
) -> Optional[Dict[str, Any]]:
    db = get_database()
    query = {"id": incident_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    msg = {
        "id": str(uuid.uuid4()),
        "actor": actor,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "chat",
    }

    result = await db.incidents.update_one({"id": incident_id}, {"$push": {"chat_messages": msg}})
    if result.modified_count == 0:
        return None

    # Broadcast via WebSocket
    try:
        from websocket_manager import sio
        incident = await db.incidents.find_one({"id": incident_id}, {"tenant_id": 1})
        if incident:
            await sio.emit(f"incident_chat_{incident_id}", msg, room=incident.get("tenant_id"))
    except Exception as exc:
        logger.debug("[WarRoom] WebSocket emit failed: %s", exc)

    return msg


async def list_incidents(
    tenant_id: str, role: str, status: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}
    if status:
        query["status"] = status

    incidents = await db.incidents.find(
        query, {"chat_messages": 0, "timeline": {"$slice": -5}}
    ).sort("created_at", -1).to_list(length=limit)

    for inc in incidents:
        inc["_id"] = str(inc["_id"])
    return incidents


async def get_incident(incident_id: str, tenant_id: str, role: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    query = {"id": incident_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id
    inc = await db.incidents.find_one(query)
    if inc:
        inc["_id"] = str(inc["_id"])
    return inc


async def get_incident_summary(tenant_id: str, role: str) -> Dict[str, Any]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}

    counts = {}
    for status in INCIDENT_STATUSES:
        counts[status] = await db.incidents.count_documents({**query, "status": status})

    by_severity = {}
    for sev in INCIDENT_SEVERITIES:
        by_severity[sev] = await db.incidents.count_documents({**query, "severity": sev})

    open_incidents = await db.incidents.find(
        {**query, "status": {"$in": ["open", "investigating"]}},
        {"id": 1, "number": 1, "title": 1, "severity": 1, "status": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(length=10)

    for inc in open_incidents:
        inc["_id"] = str(inc["_id"])

    return {
        "counts_by_status": counts,
        "counts_by_severity": by_severity,
        "total": sum(counts.values()),
        "open_count": counts.get("open", 0) + counts.get("investigating", 0),
        "critical_open": by_severity.get("P1-Critical", 0),
        "active_incidents": open_incidents,
        "incident_types": INCIDENT_TYPES,
        "severities": INCIDENT_SEVERITIES,
        "statuses": INCIDENT_STATUSES,
    }
