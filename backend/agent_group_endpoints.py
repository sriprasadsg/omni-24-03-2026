"""Agent Group Management Endpoints — /api/agent-groups/"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from authentication_service import get_current_user, TokenData
from database import get_database
from datetime import datetime, timezone
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api/agent-groups", tags=["Agent Groups"])


class GroupCreate(BaseModel):
    name: str
    description: str = ""
    color: str = "#3b82f6"
    tags: List[str] = []


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    tags: Optional[List[str]] = None


class MembersUpdate(BaseModel):
    agent_ids: List[str]


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


@router.get("/")
async def list_groups(current_user: TokenData = Depends(get_current_user)):
    """List all agent groups for the tenant."""
    db = get_database()
    groups = []
    async for doc in db.agent_groups.find({"tenantId": current_user.tenant_id}):
        _strip_id(doc)
        # Attach member count
        doc["member_count"] = await db.agent_group_members.count_documents(
            {"group_id": doc["id"], "tenantId": current_user.tenant_id}
        )
        groups.append(doc)
    return groups


@router.post("/", status_code=201)
async def create_group(body: GroupCreate, current_user: TokenData = Depends(get_current_user)):
    """Create a new agent group."""
    db = get_database()
    exists = await db.agent_groups.find_one(
        {"name": body.name, "tenantId": current_user.tenant_id}
    )
    if exists:
        raise HTTPException(status_code=409, detail="Group name already exists")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": current_user.tenant_id,
        "name": body.name,
        "description": body.description,
        "color": body.color,
        "tags": body.tags,
        "created_at": now,
        "updated_at": now,
        "created_by": current_user.email,
    }
    await db.agent_groups.insert_one(doc)
    _strip_id(doc)
    doc["member_count"] = 0
    return doc


@router.put("/{group_id}")
async def update_group(
    group_id: str,
    body: GroupUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    """Update an agent group's metadata."""
    db = get_database()
    existing = await db.agent_groups.find_one(
        {"id": group_id, "tenantId": current_user.tenant_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Group not found")
    updates = {k: v for k, v in body.dict().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.agent_groups.update_one(
        {"id": group_id, "tenantId": current_user.tenant_id},
        {"$set": updates},
    )
    doc = await db.agent_groups.find_one({"id": group_id})
    _strip_id(doc)
    doc["member_count"] = await db.agent_group_members.count_documents(
        {"group_id": group_id, "tenantId": current_user.tenant_id}
    )
    return doc


@router.delete("/{group_id}", status_code=204)
async def delete_group(group_id: str, current_user: TokenData = Depends(get_current_user)):
    """Delete a group and its memberships."""
    db = get_database()
    existing = await db.agent_groups.find_one(
        {"id": group_id, "tenantId": current_user.tenant_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Group not found")
    await db.agent_groups.delete_one({"id": group_id, "tenantId": current_user.tenant_id})
    await db.agent_group_members.delete_many({"group_id": group_id, "tenantId": current_user.tenant_id})
    return None


@router.get("/{group_id}/members")
async def list_members(group_id: str, current_user: TokenData = Depends(get_current_user)):
    """List agents in a group, enriched with agent details."""
    db = get_database()
    group = await db.agent_groups.find_one(
        {"id": group_id, "tenantId": current_user.tenant_id}
    )
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    members = []
    async for m in db.agent_group_members.find(
        {"group_id": group_id, "tenantId": current_user.tenant_id}
    ):
        agent = await db.agents.find_one(
            {"id": m["agent_id"], "tenantId": current_user.tenant_id}
        )
        if agent:
            _strip_id(agent)
            members.append({
                "agent_id": m["agent_id"],
                "added_at": m.get("added_at"),
                "hostname": agent.get("hostname"),
                "platform": agent.get("platform"),
                "status": agent.get("status"),
                "ip_address": agent.get("ipAddress"),
            })
    return members


@router.post("/{group_id}/members", status_code=201)
async def add_members(
    group_id: str,
    body: MembersUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    """Add agents to a group (idempotent)."""
    db = get_database()
    group = await db.agent_groups.find_one(
        {"id": group_id, "tenantId": current_user.tenant_id}
    )
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for agent_id in body.agent_ids:
        exists = await db.agent_group_members.find_one(
            {"group_id": group_id, "agent_id": agent_id, "tenantId": current_user.tenant_id}
        )
        if not exists:
            await db.agent_group_members.insert_one({
                "id": str(uuid.uuid4()),
                "tenantId": current_user.tenant_id,
                "group_id": group_id,
                "agent_id": agent_id,
                "added_at": now,
                "added_by": current_user.email,
            })
            added += 1
    return {"group_id": group_id, "added": added, "total_requested": len(body.agent_ids)}


@router.delete("/{group_id}/members/{agent_id}", status_code=204)
async def remove_member(
    group_id: str,
    agent_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Remove an agent from a group."""
    db = get_database()
    result = await db.agent_group_members.delete_one(
        {"group_id": group_id, "agent_id": agent_id, "tenantId": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Agent not in group")
    return None
