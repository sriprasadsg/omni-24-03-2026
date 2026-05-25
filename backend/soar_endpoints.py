from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from database import get_database
from datetime import datetime, timezone
import uuid
from soar_engine import soar_engine
from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id

router = APIRouter()

_SOAR_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

class PlaybookNode(BaseModel):
    id: str
    type: str # e.g. "trigger", "enrich_ip_vt", "block_ip_firewall"
    position: Dict[str, float]
    data: Dict[str, Any]

class PlaybookEdge(BaseModel):
    id: str
    source: str
    target: str
    data: Optional[Dict[str, Any]] = None

class PlaybookDef(BaseModel):
    name: str
    description: str = ""
    nodes: List[PlaybookNode]
    edges: List[PlaybookEdge]
    is_active: bool = True

@router.post("/playbooks")
async def create_playbook(
    playbook: PlaybookDef,
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    tenant_id = get_tenant_id()
    doc = playbook.dict()
    doc["tenant_id"] = tenant_id
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = getattr(current_user, "username", "system")
    await db.soar_playbooks.insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.get("/playbooks")
async def list_playbooks(
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    user_role = getattr(current_user, "role", "")
    tenant_id = get_tenant_id()
    query: dict = {} if user_role in _SOAR_SUPER_ROLES else {"tenant_id": tenant_id}
    playbooks = await db.soar_playbooks.find(query).to_list(length=100)
    for p in playbooks:
        p["_id"] = str(p["_id"])
    return {"playbooks": playbooks}

@router.post("/playbooks/{playbook_id}/execute")
async def execute_playbook(
    playbook_id: str,
    trigger_context: Dict[str, Any],
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    user_role = getattr(current_user, "role", "")
    tenant_id = get_tenant_id()
    playbook_filter: dict = {"id": playbook_id}
    if user_role not in _SOAR_SUPER_ROLES:
        playbook_filter["tenant_id"] = tenant_id
    playbook = await db.soar_playbooks.find_one(playbook_filter)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    background_tasks.add_task(run_and_save, playbook, trigger_context)
    return {"status": "accepted", "message": "Playbook execution started"}

async def run_and_save(playbook: dict, trigger_context: dict):
    db = get_database()
    result = await soar_engine.execute_playbook(playbook, trigger_context)

    run_doc = {
        "run_id": result["run_id"],
        "playbook_id": playbook["id"],
        "tenant_id": playbook.get("tenant_id", "default"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": result["status"],
        "log": result["log"],
    }
    await db.soar_runs.insert_one(run_doc)

@router.get("/runs")
async def get_playbook_runs(
    limit: int = Query(50, ge=1, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    user_role = getattr(current_user, "role", "")
    tenant_id = get_tenant_id()
    query: dict = {} if user_role in _SOAR_SUPER_ROLES else {"tenant_id": tenant_id}
    runs = await db.soar_runs.find(query).sort("timestamp", -1).limit(limit).to_list(length=limit)
    for r in runs:
        r["_id"] = str(r["_id"])
    return {"runs": runs}
