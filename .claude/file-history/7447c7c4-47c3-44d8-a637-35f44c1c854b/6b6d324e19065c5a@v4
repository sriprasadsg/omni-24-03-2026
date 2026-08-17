"""
Compliance Remediation Endpoints.

Routes (prefix /api/compliance-remediation):
  POST   /tasks               — create remediation task (REM-01)
  GET    /tasks               — list tasks, filterable by status/control_id (REM-02)
  PATCH  /tasks/{task_id}     — update task; dispatches rescan on resolve (REM-03)
  POST   /tasks/{task_id}/suggest — AI-suggested remediation steps (REM-01 AI assist)

Route prefix is /api/compliance-remediation (NOT /api/remediation — that prefix
is owned by remediation_endpoints.py for the vulnerability domain).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal

from authentication_service import get_current_user
from database import get_database
import compliance_remediation_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compliance-remediation", tags=["Compliance Remediation"])

_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}


def _tenant_filter(user) -> dict:
    role = getattr(user, "role", "") or ""
    if role in _SUPER_ADMIN_ROLES:
        return {}
    tenant = getattr(user, "tenant_id", "") or ""
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return {"tenantId": tenant}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    control_id: str = ""
    asset_id: str = ""
    framework_id: str = ""
    assignee: str = ""
    assignee_type: str = "user"
    due_date: Optional[str] = None
    description: str = Field("", max_length=4000)
    priority: Literal["low", "medium", "high", "critical"] = "medium"


class TaskUpdate(BaseModel):
    status: Optional[Literal["open", "in_progress", "resolved"]] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    resolution_notes: Optional[str] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/tasks", status_code=201)
async def create_task(
    body: TaskCreate,
    current_user: dict = Depends(get_current_user),
):
    """REM-01: Create a new compliance remediation task (tenant-scoped)."""
    tf = _tenant_filter(current_user)
    created_by = getattr(current_user, "username", None) or "unknown"
    return await svc.create_task(get_database(), body.model_dump(), tenant_filter=tf, created_by=created_by)


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(None),
    control_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """REM-02: List tasks for the caller's tenant with optional filters."""
    tf = _tenant_filter(current_user)
    return await svc.list_tasks(get_database(), tf, status=status, control_id=control_id)


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    body: TaskUpdate,
    current_user: dict = Depends(get_current_user),
):
    """REM-03: Update task status/fields; dispatches rescan when status becomes 'resolved'."""
    tf = _tenant_filter(current_user)
    created_by = getattr(current_user, "username", None) or "unknown"
    result = await svc.update_task(
        get_database(), task_id, body.model_dump(exclude_none=True), tf, created_by=created_by
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Optimistic UI update: broadcast immediately when rescan was dispatched
    if result.get("dispatch", {}).get("dispatched"):
        try:
            from websocket_manager import broadcast_remediation_update
            tenant_id = tf.get("tenantId") or result.get("tenantId", "")
            await broadcast_remediation_update(
                tenant_id,
                {
                    "task_id": task_id,
                    "status": result.get("status"),
                    "control_id": result.get("control_id"),
                },
            )
        except Exception as exc:
            logger.warning("broadcast_remediation_update failed (non-fatal): %s", exc)

    return result


@router.post("/tasks/{task_id}/suggest")
async def suggest_remediation(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """REM-01 AI assist: Generate AI-suggested remediation steps for a task."""
    tf = _tenant_filter(current_user)
    db = get_database()

    task = await svc.get_task(db, task_id, tf)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Resolve asset context for richer prompt
    asset_context = ""
    asset_id = task.get("asset_id", "")
    if asset_id:
        try:
            asset_doc = await db.assets.find_one({"id": asset_id})
            if asset_doc:
                asset_type = asset_doc.get("type") or asset_doc.get("asset_type") or "unknown"
                os_name = asset_doc.get("os") or asset_doc.get("operatingSystem") or "unknown"
                asset_context = f"type={asset_type}, os={os_name}"
        except Exception as exc:
            logger.warning("suggest_remediation: asset lookup failed: %s", exc)

    from ai_service import ai_service
    text = await ai_service.suggest_remediation(
        control_id=task.get("control_id", ""),
        control_description=task.get("description", ""),
        failure_reason=f"Control {task.get('control_id', '')} failed on asset {asset_id}",
        asset_context=asset_context or asset_id,
    )

    # Persist suggestion back to the task (tenant-scoped write — CR-01)
    try:
        await db.compliance_remediation_tasks.update_one(
            {"id": task_id, **tf},
            {"$set": {"ai_suggestion": text}},
        )
    except Exception as exc:
        logger.warning("Failed to persist ai_suggestion: %s", exc)

    return {"suggestion": text}
