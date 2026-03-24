from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from datetime import datetime, timezone
import uuid
from streaming_service import broker

router = APIRouter(prefix="/api/logs", tags=["Logs"])

class LogEntry(BaseModel):
    id: Optional[str] = None
    timestamp: Optional[str] = None
    severity: str # INFO, WARN, ERROR, DEBUG
    service: str
    hostname: str 
    agentId: Optional[str] = None # Added to support precise filtering
    message: str
    tenantId: Optional[str] = None
    metadata: Optional[dict] = {}

@router.get("")
async def get_logs(current_user: TokenData = Depends(get_current_user)):
    """Get system logs"""
    db = get_database()
    logs = await db.logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(100).to_list(length=100)
    return logs

@router.post("")
async def ingest_log(log: LogEntry, background_tasks: BackgroundTasks, current_user: TokenData = Depends(get_current_user)):
    """Ingest a new log entry"""
    db = get_database()
    
    # 1. Prepare Log Entry
    log_dict = log.dict()
    if not log_dict.get("id"):
        log_dict["id"] = uuid.uuid4().hex
    if not log_dict.get("timestamp"):
        log_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    # Ensure tenant isolation via token
    # If the user is an agent (service account), they might pass a tenantId, 
    # but for now we trust the token's tenant or default to it.
    if current_user and current_user.tenant_id:
        log_dict["tenantId"] = current_user.tenant_id
        
    # 2. Persist to MongoDB
    await db.logs.insert_one(log_dict)
    
    # 3. Stream to Real-time UI (Fire and Forget)
    # We publish to "logs" topic which the UI subscribes to
    background_tasks.add_task(broker.publish, "logs", log_dict)
    
    return {"success": True, "id": log_dict["id"]}

