from fastapi import APIRouter, HTTPException, Depends, Request
from database import get_database
from authentication_service import get_current_user
from rbac_utils import require_permission
from models import User
import uuid
import os
import socket
from datetime import datetime, timezone

router = APIRouter(prefix="/api/remote", tags=["Remote Access"])

_REMOTE_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


def _remote_tenant(current_user) -> dict:
    role = current_user.get("role", "") if isinstance(current_user, dict) else getattr(current_user, "role", "")
    if role in _REMOTE_SUPER_ROLES:
        return {}
    tid = (current_user.get("tenantId") or current_user.get("tenant_id")) if isinstance(current_user, dict) \
        else (getattr(current_user, "tenantId", None) or getattr(current_user, "tenant_id", None))
    return {"tenantId": tid} if tid else {}


@router.get("")
@router.get("/")
async def list_remote_sessions(
    limit: int = 50,
    current_user=Depends(require_permission("view:remote_access"))
):
    """List recent remote access sessions for the caller's tenant."""
    db = get_database()
    try:
        sessions = await db.remote_sessions.find(
            _remote_tenant(current_user), {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(length=limit)
    except Exception:
        sessions = []
    return sessions

@router.get("/sessions")
async def get_active_sessions(
    current_user=Depends(require_permission("view:remote_access"))
):
    """Get active remote sessions for the caller's tenant."""
    db = get_database()
    try:
        sessions = await db.remote_sessions.find(
            {"status": "active", **_remote_tenant(current_user)}, {"_id": 0}
        ).sort("created_at", -1).limit(20).to_list(length=20)
    except Exception:
        sessions = []
    return sessions


def _resolve_backend_ws_base(request: Request) -> str:
    """Return the ws:// base URL agents should connect back to.
    Priority: PLATFORM_URL env → BACKEND_HOST env (if not 0.0.0.0/localhost) →
              auto-detect LAN IP → fallback to request host."""
    platform_url = os.getenv("PLATFORM_URL", "").rstrip("/")
    if platform_url:
        return platform_url.replace("https://", "wss://").replace("http://", "ws://")

    env_host = os.getenv("BACKEND_HOST", "").strip()
    env_port = os.getenv("BACKEND_PORT", "5000").strip()

    if env_host and env_host not in ("0.0.0.0", "127.0.0.1", "localhost"):
        return f"ws://{env_host}:{env_port}"

    # Try to detect the server's LAN IP so remote agents can reach us
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
        if lan_ip and lan_ip != "127.0.0.1":
            return f"ws://{lan_ip}:{env_port}"
    except Exception:
        pass

    # Last resort: derive from the incoming request host
    req_host = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not req_host or req_host in ("127.0.0.1", "::1"):
        req_host = (request.client.host if request.client else None) or "localhost"
    return f"ws://{req_host}:{env_port}"


@router.post("/session/start")
async def start_remote_session(request: Request, payload: dict, current_user: User = Depends(get_current_user)):
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
    caller_tenant_id = getattr(current_user, 'tenant_id', None) or getattr(current_user, 'tenantId', None)

    # The instruction must carry the AGENT's tenantId so the agent's polling query matches.
    # When a super-admin (tenant=platform-admin) targets an agent from another tenant, using
    # the caller's tenantId would make the instruction invisible to the agent.
    agent_doc = await db.agents.find_one({"id": agent_id})
    agent_tenant_id = (agent_doc.get("tenantId") if agent_doc else None) or caller_tenant_id

    # Create session record — scoped to the caller's tenant for access-control checks
    session_data = {
        "session_id": session_id,
        "agent_id": agent_id,
        "user_id": user_identifier,
        "protocol": protocol,
        "type": session_type,
        "status": "pending",
        "tenantId": caller_tenant_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.remote_sessions.insert_one(session_data)

    # Use smart URL resolution: handles PLATFORM_URL, LAN IP detection, and HTTPS
    agent_ws_base = _resolve_backend_ws_base(request)

    instruction = {
        "id":          str(uuid.uuid4()),
        "agent_id":    agent_id,
        "instruction": "start_remote_session",
        "type":        "start_remote_session",
        "payload": {
            "session_id": session_id,
            "protocol":   protocol,
            "type":       session_type,
            "url":        f"{agent_ws_base}/api/tunnel/{session_id}/agent",
        },
        "status":      "pending",
        "tenantId":    agent_tenant_id,
        "created_at":  datetime.now(timezone.utc).isoformat(),
    }
    await db.agent_instructions.insert_one(instruction)

    return {
        "session_id": session_id,
        "status": "pending",
        "websocket_url": f"/api/tunnel/{session_id}/user",
    }
