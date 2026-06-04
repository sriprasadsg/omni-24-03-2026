"""
Personal Tasks API — per-user task management persisted to MongoDB.
Replaces the frontend-only local-state implementation.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid

from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


class TaskCreate(BaseModel):
    text: str
    priority: str = "Medium"  # Low | Medium | High


class TaskUpdate(BaseModel):
    text: Optional[str] = None
    priority: Optional[str] = None
    completed: Optional[bool] = None


@router.get("")
async def list_tasks(
    current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """Return all tasks for the authenticated user."""
    db = get_database()
    cursor = db.tasks.find(
        {"userId": current_user.username, "tenantId": tenant_id},
        {"_id": 0},
    ).sort("createdAt", -1)
    tasks = await cursor.to_list(length=500)
    # Normalise numeric id field expected by the frontend
    for t in tasks:
        if "id" not in t:
            t["id"] = t.get("_id", str(uuid.uuid4()))
    return tasks


@router.post("", status_code=201)
async def create_task(
    payload: TaskCreate,
    current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """Create a new task for the authenticated user."""
    db = get_database()
    task_id = int(datetime.now(timezone.utc).timestamp() * 1000)
    task = {
        "id": task_id,
        "text": payload.text,
        "priority": payload.priority,
        "completed": False,
        "userId": current_user.username,
        "tenantId": tenant_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await db.tasks.insert_one({**task})
    task.pop("_id", None)
    return task


@router.patch("/{task_id}")
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """Toggle completion or update text/priority."""
    db = get_database()
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updatedAt"] = datetime.now(timezone.utc).isoformat()

    result = await db.tasks.find_one_and_update(
        {"id": task_id, "userId": current_user.username, "tenantId": tenant_id},
        {"$set": updates},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    current_user: TokenData = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    """Delete a task owned by the authenticated user."""
    db = get_database()
    result = await db.tasks.delete_one(
        {"id": task_id, "userId": current_user.username, "tenantId": tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
