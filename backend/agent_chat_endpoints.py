"""
Agent Chat Endpoints — admin-to-endpoint (asset) direct messaging.

Flow:
  1. Admin selects an online agent/asset and starts a chat session.
  2. Backend creates a session and queues a `start_agent_chat` instruction.
  3. The agent on the endpoint receives the instruction and pops up a GUI window.
  4. User types in the window → agent POSTs to /user-message.
  5. Admin types in the portal → backend stores + queues `agent_chat_message` instruction.
  6. Agent polls instructions, receives the message, and displays it in the window.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
from agent_auth import verify_agent_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-chat", tags=["Agent Chat"])

_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
_ADMIN_ROLES = {"Tenant Admin", "tenant_admin"} | _SUPER_ROLES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_super(role: str) -> bool:
    return role in _SUPER_ROLES


def _is_admin(role: str) -> bool:
    return role in _ADMIN_ROLES


def _make_msg(
    sender_type: str,
    sender_id: str,
    content: str,
    sender_role: str = "",
    sender_name: str = "",
) -> Dict[str, Any]:
    return {
        "id":          str(uuid.uuid4()),
        "sender_type": sender_type,   # "admin" | "user" | "system"
        "sender_id":   sender_id,
        "sender_role": sender_role,   # e.g. "Tenant Admin", "Super Admin"
        "sender_name": sender_name or sender_id,
        "content":     content,
        "created_at":  _now(),
    }


async def _resolve_sender(db, username: str, role: str) -> str:
    """Return the display name for an admin sender, falling back to username."""
    user = await db._db.users.find_one(
        {"$or": [{"email": username}, {"username": username}]},
        {"name": 1, "_id": 0},
    )
    return (user or {}).get("name") or username


# ── Pydantic models ───────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    agent_id: str
    subject:  str = Field(..., max_length=300)
    message:  str = Field(..., max_length=5000)


class InitiateSessionRequest(BaseModel):
    """Sent by the endpoint agent when the user wants to contact an admin."""
    agent_id: str
    subject:  str = Field(..., max_length=300)
    message:  str = Field(..., max_length=5000)


class EscalateSessionRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=1000)
    target_admin: Optional[str] = Field(None, max_length=320)  # username/email of specific platform admin


class SendMessageRequest(BaseModel):
    content: str = Field(..., max_length=5000)


# ── Admin: start a chat session with an agent ─────────────────────────────────

@router.post("/sessions")
async def start_session(
    body: StartSessionRequest,
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """Admin initiates a chat with an online agent/asset."""
    if not _is_admin(current_user.role or ""):
        raise HTTPException(status_code=403, detail="Admin access required")

    db = get_database()
    caller_tenant = current_user.tenant_id or ""

    # Verify the agent exists and belongs to the caller's tenant
    agent_filter: Dict[str, Any] = {"id": body.agent_id}
    if not _is_super(current_user.role or ""):
        agent_filter["tenantId"] = caller_tenant
    agent = await db.agents.find_one(agent_filter)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    session_id = str(uuid.uuid4())
    caller_name = await _resolve_sender(db, current_user.username or "", current_user.role or "")
    first_msg = _make_msg(
        "admin", current_user.username or "", body.message,
        sender_role=current_user.role or "", sender_name=caller_name,
    )

    # Always store the AGENT's tenant so the agent key check in poll_messages /
    # user-message matches.  A super-admin's caller_tenant ("platform-admin")
    # would otherwise differ from the agent's own tenantId.
    session_tenant = agent.get("tenantId") or caller_tenant

    session: Dict[str, Any] = {
        "id":           session_id,
        "agent_id":     body.agent_id,
        "agent_hostname": agent.get("hostname", body.agent_id),
        "tenant_id":    session_tenant,
        "subject":      body.subject,
        "status":       "active",
        "initiator_id": current_user.username or "",
        "messages":     [first_msg],
        "created_at":   _now(),
        "updated_at":   _now(),
    }
    await db.agent_chat_sessions.insert_one({**session})
    session.pop("_id", None)

    # Queue instruction for the agent to open a chat window on the endpoint
    backend_url = _get_backend_url()
    instruction = {
        "agent_id":   body.agent_id,
        "type":       "start_agent_chat",
        "payload": {
            "session_id":      session_id,
            "subject":         body.subject,
            "initial_message": body.message,
            "backend_url":     backend_url,
            "sender":          current_user.username or "Administrator",
        },
        "status":     "pending",
        "tenantId":   agent.get("tenantId", caller_tenant),
        "created_at": _now(),
    }
    await db.agent_instructions.insert_one(instruction)

    logger.info("Agent chat session %s started for agent %s", session_id, body.agent_id)
    return session


# ── Admin: list sessions ──────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    status: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    if not _is_admin(current_user.role or ""):
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    query: Dict[str, Any] = {}
    if not _is_super(current_user.role or ""):
        query["tenant_id"] = current_user.tenant_id or ""
    if status:
        query["status"] = status
    sessions = await db.agent_chat_sessions.find(
        query, {"_id": 0}
    ).sort("updated_at", -1).to_list(100)
    # Strip full message arrays for list view
    for s in sessions:
        msgs = s.pop("messages", [])
        s["message_count"] = len(msgs)
        s["last_message"] = msgs[-1] if msgs else None
    return sessions


# ── Admin: get full session ───────────────────────────────────────────────────

@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    if not _is_admin(current_user.role or ""):
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    query: Dict[str, Any] = {"id": session_id}
    if not _is_super(current_user.role or ""):
        query["tenant_id"] = current_user.tenant_id or ""
    session = await db.agent_chat_sessions.find_one(query, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ── Admin: send a message to the endpoint ────────────────────────────────────

@router.post("/sessions/{session_id}/admin-message")
async def admin_send_message(
    session_id: str,
    body: SendMessageRequest,
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    if not _is_admin(current_user.role or ""):
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    query: Dict[str, Any] = {"id": session_id, "status": "active"}
    if not _is_super(current_user.role or ""):
        query["tenant_id"] = current_user.tenant_id or ""
    session = await db.agent_chat_sessions.find_one(query, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or closed")

    sender_name = await _resolve_sender(db, current_user.username or "", current_user.role or "")
    msg = _make_msg(
        "admin", current_user.username or "", body.content,
        sender_role=current_user.role or "", sender_name=sender_name,
    )
    await db.agent_chat_sessions.update_one(
        {"id": session_id},
        {"$push": {"messages": msg}, "$set": {"updated_at": _now()}},
    )

    # Queue instruction so agent picks up the message and shows it in the window
    await db.agent_instructions.insert_one({
        "agent_id":   session.get("agent_id"),
        "type":       "agent_chat_message",
        "payload":    {"session_id": session_id, "content": body.content, "sender": current_user.username or "Administrator"},
        "status":     "pending",
        "tenantId":   session.get("tenant_id", ""),
        "created_at": _now(),
    })

    # Real-time broadcast to admin portal — admins only (not all tenant users)
    try:
        from websocket_manager import sio, user_sessions, user_tenants, user_roles, _ADMIN_ROLES
        data = {"event": "agent_chat_message", "session_id": session_id, "message": msg}
        for uname, sid in user_sessions.items():
            if (user_roles.get(uname) in _ADMIN_ROLES and
                    user_tenants.get(uname, "") == (session.get("tenant_id") or "")):
                await sio.emit("agent_chat", data, room=sid)
    except Exception as e:
        logger.debug("Agent chat WS broadcast failed: %s", e)

    return msg


# ── Agent: endpoint user sends a reply ───────────────────────────────────────

@router.post("/sessions/{session_id}/user-message")
async def user_send_message(
    session_id: str,
    body: SendMessageRequest,
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
) -> Dict[str, Any]:
    """Called by the agent running on the endpoint when the user types a reply."""
    db = get_database()
    tenant_id = _tenant.get("id", "")
    # Fast path: tenant_id stored correctly (all sessions created after the fix)
    session = await db._db.agent_chat_sessions.find_one(
        {"id": session_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not session:
        # Fallback: session may have been created by a super-admin whose own
        # tenant ("platform-admin") was stamped instead of the agent's tenant.
        # Re-verify via agent ownership, then heal the stored tenant_id.
        session = await db._db.agent_chat_sessions.find_one({"id": session_id}, {"_id": 0})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        agent_check = await db.agents.find_one(
            {"id": session.get("agent_id"), "tenantId": tenant_id}, {"_id": 1}
        )
        if not agent_check:
            raise HTTPException(status_code=404, detail="Session not found")
        # Heal so future requests hit the fast path
        await db._db.agent_chat_sessions.update_one(
            {"id": session_id}, {"$set": {"tenant_id": tenant_id}}
        )
    if session.get("status") != "active":
        raise HTTPException(status_code=400, detail="Session is closed")

    hostname = session.get("agent_hostname", "Endpoint")
    msg = _make_msg(
        "user", "endpoint_user", body.content,
        sender_role="Endpoint User", sender_name=f"User @ {hostname}",
    )
    await db._db.agent_chat_sessions.update_one(
        {"id": session_id},
        {"$push": {"messages": msg}, "$set": {"updated_at": _now()}},
    )

    # Real-time: push to all admins in this tenant
    try:
        from websocket_manager import sio, user_sessions, user_tenants, user_roles, _ADMIN_ROLES
        data = {"event": "agent_chat_message", "session_id": session_id, "message": msg}
        session_tenant = session.get("tenant_id", "")
        for uname, sid in user_sessions.items():
            if (user_roles.get(uname) in _ADMIN_ROLES and
                    user_tenants.get(uname, "") == session_tenant):
                await sio.emit("agent_chat", data, room=sid)
    except Exception as e:
        logger.debug("Agent chat WS broadcast failed: %s", e)

    return msg


# ── Agent: poll for new admin messages ───────────────────────────────────────

@router.get("/sessions/{session_id}/messages")
async def poll_messages(
    session_id: str,
    since: Optional[float] = Query(None),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
) -> Dict[str, Any]:
    """Agent polls this endpoint to get new admin messages for an active session."""
    db = get_database()
    tenant_id = _tenant.get("id", "")
    # Fast path: tenant_id stored correctly
    session = await db._db.agent_chat_sessions.find_one(
        {"id": session_id, "tenant_id": tenant_id},
        {"_id": 0, "messages": 1, "status": 1, "agent_id": 1},
    )
    if not session:
        # Fallback: heal sessions stamped with super-admin's tenant
        raw = await db._db.agent_chat_sessions.find_one({"id": session_id}, {"_id": 0})
        if not raw:
            raise HTTPException(status_code=404, detail="Session not found")
        agent_check = await db.agents.find_one(
            {"id": raw.get("agent_id"), "tenantId": tenant_id}, {"_id": 1}
        )
        if not agent_check:
            raise HTTPException(status_code=404, detail="Session not found")
        await db._db.agent_chat_sessions.update_one(
            {"id": session_id}, {"$set": {"tenant_id": tenant_id}}
        )
        session = raw
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    all_msgs = session.get("messages", [])
    if since:
        from datetime import datetime, timezone
        since_dt = datetime.fromtimestamp(since, tz=timezone.utc).isoformat()
        new_msgs = [m for m in all_msgs if m.get("created_at", "") > since_dt and m.get("sender_type") == "admin"]
    else:
        new_msgs = [m for m in all_msgs if m.get("sender_type") == "admin"]

    return {"messages": new_msgs, "status": session.get("status", "active")}


# ── List platform admins available for escalation ────────────────────────────

@router.get("/platform-admins")
async def list_platform_admins(
    current_user: TokenData = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Return platform/super admins with online presence for the escalation picker."""
    if not _is_admin(current_user.role or ""):
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    admins = await db._db.users.find(
        {"role": {"$in": list(_SUPER_ROLES)}},
        {"_id": 0, "username": 1, "name": 1, "email": 1, "role": 1},
    ).to_list(50)
    try:
        from websocket_manager import user_sessions
        online = set(user_sessions.keys())
    except Exception:
        online = set()
    result = []
    for a in admins:
        uname = a.get("username") or a.get("email") or ""
        result.append({
            "username": uname,
            "name":     a.get("name") or uname,
            "email":    a.get("email") or "",
            "role":     a.get("role") or "Super Admin",
            "online":   uname in online,
        })
    result.sort(key=lambda x: (not x["online"], x["name"].lower()))
    return result


# ── Endpoint agent: initiate a new session to contact an admin ───────────────

@router.post("/sessions/initiate")
async def initiate_session(
    body: InitiateSessionRequest,
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
) -> Dict[str, Any]:
    """Endpoint agent starts a chat to contact an admin (reverse direction)."""
    db = get_database()
    tenant_id = _tenant.get("id", "")

    agent_filter: Dict[str, Any] = {"id": body.agent_id, "tenantId": tenant_id}
    agent = await db.agents.find_one(agent_filter, {"_id": 0, "hostname": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found in tenant")

    session_id = str(uuid.uuid4())
    hostname = agent.get("hostname", body.agent_id)
    first_msg = _make_msg(
        "user", "endpoint_user", body.message,
        sender_role="Endpoint User", sender_name=f"User @ {hostname}",
    )
    session: Dict[str, Any] = {
        "id":             session_id,
        "agent_id":       body.agent_id,
        "agent_hostname": agent.get("hostname", body.agent_id),
        "tenant_id":      tenant_id,
        "subject":        body.subject,
        "status":         "active",
        "initiator_id":   body.agent_id,
        "initiator_type": "endpoint",
        "messages":       [first_msg],
        "created_at":     _now(),
        "updated_at":     _now(),
    }
    await db.agent_chat_sessions.insert_one({**session})
    session.pop("_id", None)

    # Notify all admins in this tenant so they see the new session immediately
    try:
        from websocket_manager import sio, user_sessions, user_tenants, user_roles, _ADMIN_ROLES
        payload = {"event": "agent_chat_initiated", "session_id": session_id,
                   "agent_hostname": session["agent_hostname"], "subject": body.subject}
        for uname, sid in user_sessions.items():
            if user_roles.get(uname) in _ADMIN_ROLES and user_tenants.get(uname, "") == tenant_id:
                await sio.emit("agent_chat", payload, room=sid)
    except Exception as e:
        logger.debug("Endpoint-initiated chat broadcast failed: %s", e)

    return session


# ── Admin: escalate an endpoint chat to platform admin ───────────────────────

@router.post("/sessions/{session_id}/escalate")
async def escalate_session(
    session_id: str,
    body: EscalateSessionRequest,
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """Admin escalates an active endpoint chat to platform admin / super admin."""
    if not _is_admin(current_user.role or ""):
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    query: Dict[str, Any] = {"id": session_id, "status": "active"}
    if not _is_super(current_user.role or ""):
        query["tenant_id"] = current_user.tenant_id or ""
    session = await db.agent_chat_sessions.find_one(query, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or already closed")
    if session.get("escalated"):
        raise HTTPException(status_code=400, detail="Session already escalated")

    now = _now()
    note_text   = body.note or ""
    target_admin = body.target_admin or ""
    target_label = f" → {target_admin}" if target_admin else ""
    sys_content = (
        f"⚠️ Escalated to Platform Admin{target_label} by {current_user.username or 'admin'}"
        + (f" — {note_text}" if note_text else "")
    )
    sys_msg = _make_msg("system", "system", sys_content)

    await db.agent_chat_sessions.update_one(
        {"id": session_id},
        {"$set": {
            "escalated":        True,
            "escalated_at":     now,
            "escalated_by":     current_user.username or "",
            "escalation_note":  note_text,
            "escalation_target": target_admin,
            "updated_at":       now,
        }, "$push": {"messages": sys_msg}},
    )

    # Broadcast: if a specific admin was targeted notify only them, else all super admins
    try:
        from websocket_manager import sio, user_sessions, user_roles, _SUPER_ROLES
        payload = {
            "event":          "agent_chat_escalated",
            "session_id":     session_id,
            "agent_hostname": session.get("agent_hostname", ""),
            "subject":        session.get("subject", ""),
            "escalated_by":   current_user.username or "",
            "target_admin":   target_admin,
            "note":           note_text,
            "message":        sys_msg,
        }
        for uname, sid in user_sessions.items():
            if user_roles.get(uname) in _SUPER_ROLES:
                if not target_admin or uname == target_admin:
                    await sio.emit("agent_chat", payload, room=sid)
    except Exception as e:
        logger.debug("Escalation broadcast failed: %s", e)

    updated = await db.agent_chat_sessions.find_one({"id": session_id}, {"_id": 0})
    return updated


# ── Close session ─────────────────────────────────────────────────────────────

@router.patch("/sessions/{session_id}/close")
async def close_session(
    session_id: str,
    current_user: TokenData = Depends(get_current_user),  # required — no Optional
) -> Dict[str, Any]:
    if not _is_admin(current_user.role or ""):
        raise HTTPException(status_code=403, detail="Admin access required")
    db = get_database()
    # Scope to caller's tenant so admins cannot close sessions belonging to other tenants
    query: Dict[str, Any] = {"id": session_id}
    if not _is_super(current_user.role or ""):
        query["tenant_id"] = current_user.tenant_id or ""
    session = await db.agent_chat_sessions.find_one(query, {"_id": 0, "agent_id": 1, "tenant_id": 1})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.agent_chat_sessions.update_one(
        {"id": session_id},
        {"$set": {"status": "closed", "closed_at": _now(), "updated_at": _now()}},
    )

    # Tell the agent to tear down the endpoint chat window promptly.
    await db.agent_instructions.insert_one({
        "agent_id":   session.get("agent_id"),
        "type":       "close_agent_chat",
        "payload":    {"session_id": session_id},
        "status":     "pending",
        "tenantId":   session.get("tenant_id", ""),
        "created_at": _now(),
    })
    return {"status": "closed", "session_id": session_id}


def _get_backend_url() -> str:
    import os, socket
    platform_url = os.getenv("PLATFORM_URL", "").rstrip("/")
    if platform_url:
        return platform_url

    env_host = os.getenv("BACKEND_HOST", "").strip()
    env_port = os.getenv("BACKEND_PORT", "5000").strip()

    if env_host and env_host not in ("0.0.0.0", "127.0.0.1", "localhost"):
        return f"http://{env_host}:{env_port}"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
        if lan_ip and lan_ip != "127.0.0.1":
            return f"http://{lan_ip}:{env_port}"
    except Exception:
        pass

    return f"http://localhost:{env_port}"
