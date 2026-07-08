"""
Compliance Remediation Service — DB logic for compliance_remediation_tasks.

Exports: create_task, list_tasks, get_task, update_task, dispatch_rescan
Collection: compliance_remediation_tasks (NOT remediation_tasks — reserved for
continuous_compliance_service).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_id(doc: Optional[dict]) -> Optional[dict]:
    """Remove MongoDB _id from a document dict in place and return it."""
    if doc is not None:
        doc.pop("_id", None)
    return doc


async def create_task(db, data: dict, tenant_filter: dict, created_by: str) -> dict:
    """REM-01: Insert a new compliance remediation task; returns the persisted doc."""
    asset_id = data.get("asset_id", "")
    # CR-02/WR-03: never trust agent_id from user input — derive only from
    # a tenant-scoped asset lookup so cross-tenant dispatch is impossible.
    agent_id = ""
    if asset_id:
        try:
            asset_doc = await db.assets.find_one({"id": asset_id, **tenant_filter})
            if asset_doc:
                agent_id = asset_doc.get("agentId", "")
        except Exception as exc:
            logger.warning("Could not resolve agent_id from asset %s: %s", asset_id, exc)

    now = _now()
    task = {
        "id": str(uuid.uuid4()),
        "title": data.get("title", ""),
        "control_id": data.get("control_id", ""),
        "asset_id": asset_id,
        "framework_id": data.get("framework_id", ""),
        "status": "open",
        "priority": data.get("priority", "medium"),
        "assignee": data.get("assignee", ""),
        "due_date": data.get("due_date"),
        "description": data.get("description", ""),
        "resolution_notes": None,
        "agent_id": agent_id,
        "ai_suggestion": None,
        "tenantId": tenant_filter.get("tenantId", ""),
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    await db.compliance_remediation_tasks.insert_one(task)
    task.pop("_id", None)
    return task


async def list_tasks(
    db,
    tenant_filter: dict,
    status: Optional[str] = None,
    control_id: Optional[str] = None,
) -> list:
    """REM-02: List tasks for the caller's tenant, filterable by status/control_id."""
    query: dict = {**tenant_filter}
    if status is not None:
        query["status"] = status
    if control_id is not None:
        query["control_id"] = control_id

    cursor = db.compliance_remediation_tasks.find(query)
    results = await cursor.to_list(length=500)
    for doc in results:
        doc.pop("_id", None)
    return results


async def get_task(db, task_id: str, tenant_filter: dict) -> Optional[dict]:
    """Fetch a single task by id within tenant scope."""
    doc = await db.compliance_remediation_tasks.find_one({"id": task_id, **tenant_filter})
    return _strip_id(doc)


async def update_task(
    db,
    task_id: str,
    updates: dict,
    tenant_filter: dict,
    created_by: str = "system",
) -> Optional[dict]:
    """REM-03: Apply updates to a task. On status='resolved', dispatches a rescan."""
    updates["updated_at"] = _now()
    result = await db.compliance_remediation_tasks.update_one(
        {"id": task_id, **tenant_filter},
        {"$set": updates},
    )
    if result.matched_count == 0:
        return None

    task = await db.compliance_remediation_tasks.find_one({"id": task_id, **tenant_filter})
    _strip_id(task)

    if task and updates.get("status") == "resolved":
        dispatch_result = await dispatch_rescan(db, task, created_by)
        task["dispatch"] = dispatch_result

    return task


async def dispatch_rescan(db, task: dict, created_by: str) -> dict:
    """REM-03: Resolve agent and insert 'Run Compliance Scan' instruction."""
    agent_id = task.get("agent_id", "")

    if not agent_id:
        asset_id = task.get("asset_id", "")
        tenant_id = task.get("tenantId", "")
        asset_filter = {"id": asset_id}
        if tenant_id:
            asset_filter["tenantId"] = tenant_id  # WR-03: tenant-scope asset lookup
        if asset_id:
            try:
                asset_doc = await db.assets.find_one(asset_filter)
                if asset_doc:
                    agent_id = asset_doc.get("agentId", "")
            except Exception as exc:
                logger.warning("dispatch_rescan: asset lookup failed for %s: %s", asset_id, exc)

    if not agent_id:
        return {"dispatched": False, "reason": "No agent enrolled for this asset"}

    instruction = {
        "agent_id": agent_id,
        "instruction": "Run Compliance Scan",
        "status": "pending",
        "created_at": _now(),
        "created_by": created_by,
        "priority": "high",
        "control_id": task.get("control_id", ""),
        "remediation_task_id": task.get("id", ""),
        "tenantId": task.get("tenantId", ""),  # CR-03: required by agent polling query
    }
    await db.agent_instructions.insert_one(instruction)

    sent = False
    try:
        from websocket_manager import send_to_agent
        sent = await send_to_agent(
            agent_id,
            {
                "action": "compliance_scan",
                "instruction": "Run Compliance Scan",
                "control_id": task.get("control_id", ""),
                "task_id": task.get("id", ""),
            },
        )
    except Exception as exc:
        logger.debug("dispatch_rescan: send_to_agent non-fatal: %s", exc)

    return {"dispatched": True, "agent_id": agent_id, "pushed": sent}
