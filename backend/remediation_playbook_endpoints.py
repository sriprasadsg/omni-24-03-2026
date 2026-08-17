"""Tenant-scoped CRUD over the deterministic `remediation_playbooks` store
(Phase 53-01, AUTO-02). This is the store the autonomous remediation engine
(53-03) executes — NOT the LLM-driven `playbooks` store fronted by
enhanced_playbook_endpoints.py.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from authentication_service import get_current_user
from database import get_database
from rbac_utils import verify_permission
from remediation_playbook_service import sync_default_playbooks_to_db, validate

logger = logging.getLogger("remediation_playbook_endpoints")
router = APIRouter(prefix="/api/remediation-playbooks", tags=["Remediation Playbooks"])


class PlaybookStep(BaseModel):
    action: str
    params: Dict[str, Any] = {}
    destructive: bool = False


class PlaybookIn(BaseModel):
    name: str
    finding_class: str
    match: Dict[str, Any] = {}
    steps: List[PlaybookStep]
    rollback: List[PlaybookStep] = []


async def _require_ops_permission(current_user=Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:active_response"):
        raise HTTPException(status_code=403, detail="Permission denied")
    return current_user


@router.get("")
async def list_playbooks(current_user=Depends(_require_ops_permission)):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    await sync_default_playbooks_to_db(db)
    return await db.remediation_playbooks.find(
        {"$or": [{"source": "vendored"}, {"tenantId": tenant_id}]}, {"_id": 0}
    ).to_list(length=200)


@router.get("/{playbook_id}")
async def get_playbook(playbook_id: str, current_user=Depends(_require_ops_permission)):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    playbook = await db.remediation_playbooks.find_one(
        {"id": playbook_id, "$or": [{"source": "vendored"}, {"tenantId": tenant_id}]}, {"_id": 0}
    )
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return playbook


@router.post("")
async def create_playbook(body: PlaybookIn, current_user=Depends(_require_ops_permission)):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    doc = body.model_dump()
    try:
        validate(doc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    doc["id"] = f"pb-{uuid.uuid4().hex}"
    doc["source"] = "operator"
    doc["tenantId"] = tenant_id
    doc["createdAt"] = datetime.now(timezone.utc).isoformat()
    doc["createdBy"] = getattr(current_user, "id", None) or getattr(current_user, "email", None)
    await db.remediation_playbooks.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{playbook_id}")
async def update_playbook(playbook_id: str, body: PlaybookIn, current_user=Depends(_require_ops_permission)):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    existing = await db.remediation_playbooks.find_one({"id": playbook_id, "tenantId": tenant_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Playbook not found (vendored playbooks are read-only)")

    updates = body.model_dump()
    try:
        validate(updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    updates["updatedAt"] = datetime.now(timezone.utc).isoformat()
    await db.remediation_playbooks.update_one({"id": playbook_id, "tenantId": tenant_id}, {"$set": updates})
    updated = await db.remediation_playbooks.find_one({"id": playbook_id, "tenantId": tenant_id}, {"_id": 0})
    return updated


@router.delete("/{playbook_id}")
async def delete_playbook(playbook_id: str, current_user=Depends(_require_ops_permission)):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    existing = await db.remediation_playbooks.find_one({"id": playbook_id, "tenantId": tenant_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Playbook not found (vendored playbooks are read-only)")
    await db.remediation_playbooks.delete_one({"id": playbook_id, "tenantId": tenant_id})
    return {"deleted": True}
