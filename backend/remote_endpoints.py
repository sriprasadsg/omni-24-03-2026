from fastapi import APIRouter, HTTPException, Depends
from database import get_database
from authentication_service import get_current_user
from models import User
import uuid
import datetime

router = APIRouter(prefix="/api/remote", tags=["Remote Access"])

@router.get("")
@router.get("/")
async def list_remote_sessions(tenant_id: str = "default", limit: int = 50):
    """List recent remote access sessions."""
    db = get_database()
    try:
        sessions = await db.remote_sessions.find(
            {}, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(length=limit)
    except Exception:
        sessions = []
    return sessions

@router.get("/sessions")
async def get_active_sessions():
    """Get active remote sessions."""
    db = get_database()
    try:
        sessions = await db.remote_sessions.find(
            {"status": "active"}, {"_id": 0}
        ).sort("created_at", -1).limit(20).to_list(length=20)
    except Exception:
        sessions = []
    return sessions


@router.post("/session/start")
async def start_remote_session(payload: dict, current_user: User = Depends(get_current_user)):
    """
    Start a remote session with an agent.
    Payload: {"agent_id": "uuid", "protocol": "ssh", "type": "shell"}
    """
    agent_id = payload.get("agent_id")
    protocol = payload.get("protocol", "ssh")
    session_type = payload.get("type", "shell")
    
    if not agent_id:
        raise HTTPException(status_code=400, detail="Agent ID is required")

    db = get_database()
    session_id = str(uuid.uuid4())
    
    # Get user identifier - try email first, fall back to id
    user_identifier = getattr(current_user, 'email', None) or getattr(current_user, 'id', 'unknown')
    
    # Create session record
    session_data = {
        "session_id": session_id,
        "agent_id": agent_id,
        "user_id": user_identifier,
        "protocol": protocol,
        "type": session_type,
        "status": "pending",
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    await db.remote_sessions.insert_one(session_data)
    
    # Queue instruction for agent
    # We use the agent_id provided. The agent_endpoints logic handles mapping if needed.
    instruction = {
        "agent_id": agent_id,
        "type": "start_remote_session",
        "payload": {
            "session_id": session_id,
            "protocol": protocol,
            "url": f"ws://localhost:5000/api/tunnel/{session_id}/agent" 
        },
        "status": "pending",
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    await db.agent_instructions.insert_one(instruction)
    
    return {"session_id": session_id, "status": "pending", "websocket_url": f"ws://localhost:5000/api/tunnel/{session_id}/user"}
