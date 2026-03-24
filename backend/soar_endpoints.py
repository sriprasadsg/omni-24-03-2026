from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from database import get_database
from datetime import datetime
import uuid
from soar_engine import soar_engine

router = APIRouter()

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
    tenant_id: str = "default"
    nodes: List[PlaybookNode]
    edges: List[PlaybookEdge]
    is_active: bool = True

@router.post("/playbooks")
async def create_playbook(playbook: PlaybookDef):
    db = get_database()
    doc = playbook.dict()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.utcnow().isoformat()
    await db.soar_playbooks.insert_one(doc)
    doc["_id"] = str(doc["_id"])
    return doc

@router.get("/playbooks")
async def list_playbooks(tenant_id: str = "default"):
    db = get_database()
    playbooks = await db.soar_playbooks.find({"tenant_id": tenant_id}).to_list(length=100)
    for p in playbooks:
        p["_id"] = str(p["_id"])
    return {"playbooks": playbooks}

@router.post("/playbooks/{playbook_id}/execute")
async def execute_playbook(playbook_id: str, trigger_context: Dict[str, Any], background_tasks: BackgroundTasks):
    db = get_database()
    playbook = await db.soar_playbooks.find_one({"id": playbook_id})
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
        
    # We run it in the background since execution could take a while
    background_tasks.add_task(run_and_save, playbook, trigger_context)
    
    return {"status": "accepted", "message": "Playbook execution started"}

async def run_and_save(playbook: dict, trigger_context: dict):
    db = get_database()
    result = await soar_engine.execute_playbook(playbook, trigger_context)
    
    # Save the run log
    run_doc = {
        "run_id": result["run_id"],
        "playbook_id": playbook["id"],
        "tenant_id": playbook.get("tenant_id", "default"),
        "timestamp": datetime.utcnow().isoformat(),
        "status": result["status"],
        "log": result["log"],
    }
    await db.soar_runs.insert_one(run_doc)

@router.get("/runs")
async def get_playbook_runs(tenant_id: str = "default", limit: int = 50):
    db = get_database()
    runs = await db.soar_runs.find({"tenant_id": tenant_id}).sort("timestamp", -1).limit(limit).to_list(length=limit)
    for r in runs:
        r["_id"] = str(r["_id"])
    return {"runs": runs}
