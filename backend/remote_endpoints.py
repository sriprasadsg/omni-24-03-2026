from fastapi import APIRouter, Body, HTTPException, Depends, Request
from database import get_database
from authentication_service import get_current_user
from rbac_utils import require_permission
import rbac_utils
from models import User
from tunnel_endpoints import close_session
from control_session_audit_service import write_audit, list_audit
import uuid
import os
import socket
from datetime import datetime, timezone

router = APIRouter(prefix="/api/remote", tags=["Remote Access"])

_REMOTE_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
# Consent decisions the tunnel-authenticated agent may report (74-02 Task 3)
_CONTROL_CONSENT_DECISIONS = {"accept", "decline", "timeout"}


def _requester_identity(current_user) -> dict:
    """Extract requester identity for audit payload."""
    if isinstance(current_user, dict):
        return {
            "requester_name": current_user.get("name") or current_user.get("displayName") or "Unknown",
            "requester_email": current_user.get("email") or current_user.get("username") or "unknown@local",
            "requester_role": current_user.get("role") or "unknown",
        }
    return {
        "requester_name": getattr(current_user, "name", None) or getattr(current_user, "displayName", None) or "Unknown",
        "requester_email": getattr(current_user, "email", None) or getattr(current_user, "username", None) or "unknown@local",
        "requester_role": getattr(current_user, "role", None) or "unknown",
    }


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
    Priority: BACKEND_WS_HOST env → PLATFORM_URL env → BACKEND_HOST env (if not 0.0.0.0/localhost) →
              auto-detect LAN IP → fallback to request host.
    BACKEND_WS_HOST is independent WS override for cross-subnet agent reachability."""
    ws_host = os.getenv("BACKEND_WS_HOST", "").strip()
    ws_port = os.getenv("BACKEND_WS_PORT", "5000").strip()
    if ws_host:
        return f"ws://{ws_host}:{ws_port}"

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
async def start_remote_session(request: Request, payload: dict = Body(...), current_user: User = Depends(get_current_user)):
    """
    Start a remote session with an agent.
    Payload: {"agent_id": "uuid", "protocol": "ssh", "type": "shell"}
    """
    agent_id = payload.get("agent_id")
    protocol = payload.get("protocol", "ssh")
    session_type = payload.get("type", "shell")

    if session_type == "control" and not await rbac_utils.verify_permission(current_user, "control:remote_access"):
        # Phase 74: interactive control is a distinct permission — a
        # view:remote_access-only principal must be refused before any session
        # or instruction is written (T-74-01). No permission implication: a
        # control gate never checks view, and view never grants control.
        raise HTTPException(status_code=403, detail="Missing required permission: control:remote_access")

    if not agent_id:
        raise HTTPException(status_code=400, detail="Agent ID is required")

    db = get_database()

    # Single-active-control-session guard (74-02, D-10/T-74-10): refuse a
    # second control request against an agent that already has a pending or
    # active control session. Leave desktop/shell/vnc unaffected.
    if session_type == "control":
        existing = await db.remote_sessions.find_one(
            {"agent_id": agent_id, "type": "control", "status": {"$in": ["pending", "active"]}},
            {"_id": 1, "session_id": 1},
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"reason": "already_controlled",
                        "message": f"Agent {agent_id} already has a control session ({existing['session_id']})."
                                   " Disconnect it first before starting another."},
            )

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

    # `payload` param holds the original request body — save before shadowing
    request_body = payload
    instruction_payload = {
        "session_id": session_id,
        "protocol":   protocol,
        "type":       session_type,
        "url":        f"{agent_ws_base}/api/tunnel/{session_id}/agent",
    }
    # Linux SSH shell sessions may carry credentials provided by the browser
    if session_type == "shell" and request_body.get("protocol") == "ssh":
        cred_user = request_body.get("username", "")
        cred_pass = request_body.get("password", "")
        if cred_user:
            instruction_payload["username"] = cred_user
        if cred_pass:
            instruction_payload["password"] = cred_pass
    if session_type == "control":
        instruction_payload.update(_requester_identity(current_user))
        instruction_payload["tenant_name"] = caller_tenant_id or "platform"

    instruction = {
        "id":          str(uuid.uuid4()),
        "agent_id":    agent_id,
        "instruction": "start_remote_session",
        "type":        "start_remote_session",
        "payload":     instruction_payload,
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


@router.post("/session/{session_id}/disconnect")
async def disconnect_session(
    session_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    """Disconnect an active control session (admin force-kill). Gated on control:remote_access."""
    if not await rbac_utils.verify_permission(current_user, "control:remote_access"):
        raise HTTPException(status_code=403, detail="Missing required permission: control:remote_access")

    db = get_database()
    session = await db.remote_sessions.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.get("type") != "control":
        raise HTTPException(status_code=400, detail="Only control sessions can be force-disconnected")

    requester = _requester_identity(current_user)
    tenant_id = session.get("tenantId")

    # Kill the tunnel
    close_session(session_id)

    # Update session status
    await db.remote_sessions.update_one(
        {"session_id": session_id}, {"$set": {"status": "closed"}}
    )

    # Write audit record
    await write_audit(
        db,
        tenant_id,
        {
            "session_id": session_id,
            "agent_id": session.get("agent_id"),
            "event": "session_end",
            "disconnect_reason": payload.get("reason", "admin_disconnect"),
            "mode": "control",
            **requester,
        },
    )

    return {"status": "disconnected", "session_id": session_id}


@router.post("/session/{session_id}/consent")
async def report_consent(
    session_id: str,
    payload: dict,
    current_user=Depends(get_current_user),  # Agent auth via token or X-Tenant-Key
):
    """Agent reports consent decision (accept/decline/timeout). Writes audit."""
    from authentication_service import verify_token_async

    # Verify agent identity via JWT or X-Tenant-Key header
    token = payload.get("token", "")
    tenant_key = payload.get("tenant_key", "")

    agent_verified = False
    if token:
        try:
            await verify_token_async(token)
            agent_verified = True
        except Exception:
            pass

    if not agent_verified and tenant_key:
        db = get_database()
        tenant = await db.tenants.find_one({"registrationKey": tenant_key})
        if tenant:
            agent_verified = True

    if not agent_verified:
        raise HTTPException(status_code=401, detail="Agent authentication required")

    decision = payload.get("decision")
    if decision not in _CONTROL_CONSENT_DECISIONS:
        raise HTTPException(status_code=400, detail="Invalid decision: must be accept, decline, or timeout")

    db = get_database()
    session = await db.remote_sessions.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.get("type") != "control":
        raise HTTPException(status_code=400, detail="Consent only applies to control sessions")

    # Tenant scope check
    session_tenant = session.get("tenantId")
    if session_tenant and session_tenant != "platform-admin":
        agent_tenant = tenant.get("id") if tenant_key and (tenant := await db.tenants.find_one({"registrationKey": tenant_key})) else None
        if agent_tenant and agent_tenant != session_tenant:
            raise HTTPException(status_code=403, detail="Agent tenant mismatch")

    tenant_id = session_tenant
    disconnect_reason = {
        "accept": None,
        "decline": "consent_declined",
        "timeout": "consent_timeout",
    }.get(decision)

    if disconnect_reason:
        close_session(session_id)
        await db.remote_sessions.update_one(
            {"session_id": session_id}, {"$set": {"status": "closed"}}
        )

    await write_audit(
        db,
        tenant_id,
        {
            "session_id": session_id,
            "agent_id": session.get("agent_id"),
            "event": "consent_decision",
            "consent_decision": decision,
            "disconnect_reason": disconnect_reason,
            "mode": "control",
        },
    )

    if decision == "accept":
        await db.remote_sessions.update_one(
            {"session_id": session_id}, {"$set": {"status": "active"}}
        )

    return {"status": "recorded", "decision": decision}


@router.get("/capabilities")
async def get_capabilities(current_user=Depends(get_current_user)):
    """Return what the caller can do: view vs control."""
    can_view = await rbac_utils.verify_permission(current_user, "view:remote_access")
    can_control = await rbac_utils.verify_permission(current_user, "control:remote_access")
    return {"can_view": can_view, "can_control": can_control}
