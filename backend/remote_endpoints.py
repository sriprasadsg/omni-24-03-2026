from fastapi import APIRouter, Body, HTTPException, Depends, Request
from catalogue_mounts_agents import REMOTE_ACCESS_GUARD
from database import get_database
from authentication_service import get_current_user, get_current_user_or_agent
from rbac_utils import require_permission
import rbac_utils
from models import User
from tunnel_endpoints import close_session, is_session_connected
from control_session_audit_service import write_audit, list_audit
import uuid
import os
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/remote", tags=["Remote Access"])

_REMOTE_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
# Consent decisions the tunnel-authenticated agent may report (74-02 Task 3)
_CONTROL_CONSENT_DECISIONS = {"accept", "decline", "timeout"}
# Session type -> audit mode, for the sessions whose screen stream asks the endpoint user.
_CONSENT_MODES = {"desktop": "view", "control": "control"}
# Grace window after a control session is created in which it still blocks a new
# one even without a connected tunnel — the agent may not have dialed in yet.
_CONTROL_CONNECT_GRACE_SECONDS = 90


def _control_session_still_live(existing: dict) -> bool:
    """Whether an existing control session should still block a new request.

    True while its tunnel is connected, or within the connect grace window after
    creation. A session that is neither is stale (its capture died while the
    browser held the socket open) and must not wedge the agent forever.
    """
    if is_session_connected(existing.get("session_id", "")):
        return True
    created = existing.get("created_at")
    if not created:
        return False
    try:
        ts = datetime.fromisoformat(created) if isinstance(created, str) else created
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False
    return (datetime.now(timezone.utc) - ts).total_seconds() < _CONTROL_CONNECT_GRACE_SECONDS


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


@router.get("", dependencies=[Depends(REMOTE_ACCESS_GUARD)])
@router.get("/", dependencies=[Depends(REMOTE_ACCESS_GUARD)])
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

@router.get("/sessions", dependencies=[Depends(REMOTE_ACCESS_GUARD)])
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
    """Return the ws(s):// base URL agents should connect back to.

    It must be the address agents already use: the one their installer wrote
    (agent_download_endpoints._resolve_url) — PLATFORM_URL, else https://<app
    host> when agents pin the TLS front end's certificate (AGENT_CA_CERT_FILE).
    BACKEND_WS_HOST (plain ws:// to :5000) used to win over both; left pointing
    at a retired server it sent every desktop session there, and the agent
    would send its tenant key and screen in clear text.
    Priority: PLATFORM_URL → wss://<app host> (pinned agents) → BACKEND_WS_HOST →
              app Host (x-forwarded-host/host + x-forwarded-proto) →
              BACKEND_HOST env (if not 0.0.0.0/localhost) → request client host."""
    platform_url = os.getenv("PLATFORM_URL", "").rstrip("/")
    if platform_url:
        return platform_url.replace("https://", "wss://").replace("http://", "ws://")

    app_host = (request.headers.get("host") or "").split(":")[0].strip()
    if os.getenv("AGENT_CA_CERT_FILE") and app_host not in ("", "localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return f"wss://{app_host}"

    ws_host = os.getenv("BACKEND_WS_HOST", "").strip()
    ws_port = os.getenv("BACKEND_WS_PORT", "5000").strip()
    if ws_host:
        return f"ws://{ws_host}:{ws_port}"

    # Prefer public application host — works for internet agents behind proxy
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").strip().lower()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").strip()
    # host already includes port when non-standard; strip empty / loopback
    if host and host not in ("", "localhost", "127.0.0.1", "::1"):
        ws_scheme = "wss" if proto == "https" else "ws"
        return f"{ws_scheme}://{host}"

    env_host = os.getenv("BACKEND_HOST", "").strip()
    env_port = os.getenv("BACKEND_PORT", "5000").strip()

    if env_host and env_host not in ("0.0.0.0", "127.0.0.1", "localhost"):
        return f"ws://{env_host}:{env_port}"

    # Last resort: request client host (never LAN IP — breaks internet reachability)
    req_host = (request.client.host if request.client else None) or "localhost"
    return f"ws://{req_host}:{env_port}"


@router.post("/session/start", dependencies=[Depends(REMOTE_ACCESS_GUARD)])
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
    if session_type != "control" and not await rbac_utils.verify_permission(current_user, "view:remote_access"):
        # Shell/desktop/vnc sessions need view:remote_access — the same permission
        # that gates listing sessions.
        raise HTTPException(status_code=403, detail="Missing required permission: view:remote_access")

    if not agent_id:
        raise HTTPException(status_code=400, detail="Agent ID is required")

    db = get_database()

    # Single-active-control-session guard (74-02, D-10/T-74-10): refuse a
    # second control request against an agent that already has a pending or
    # active control session. Leave desktop/shell/vnc unaffected.
    #
    # Only a session that is genuinely still live blocks. A control session
    # whose capture died (Defender quarantine, crash) stays "active" in the DB
    # while the browser keeps its socket open on the "ended" overlay; that dead
    # row used to wedge every later control request with a 409. So an existing
    # control session only blocks while its tunnel is connected, or within a
    # short grace window after creation (the agent may not have connected yet).
    # Otherwise it is stale — reap it and let this request through.
    if session_type == "control":
        existing = await db.remote_sessions.find_one(
            {"agent_id": agent_id, "type": "control", "status": {"$in": ["pending", "active"]}},
            {"_id": 1, "session_id": 1, "created_at": 1},
        )
        if existing:
            if _control_session_still_live(existing):
                raise HTTPException(
                    status_code=409,
                    detail={"reason": "already_controlled",
                            "message": f"Agent {agent_id} already has a control session ({existing['session_id']})."
                                       " Disconnect it first before starting another."},
                )
            # Stale: close it (also sentinels any half-open tunnel) and continue.
            close_session(existing["session_id"])
            await db.remote_sessions.update_one(
                {"session_id": existing["session_id"]}, {"$set": {"status": "closed"}}
            )
            logger.info("Reaped stale control session %s for agent %s before starting a new one",
                        existing["session_id"], agent_id)

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


@router.post("/session/{session_id}/disconnect", dependencies=[Depends(REMOTE_ACCESS_GUARD)])
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
    principal=Depends(get_current_user_or_agent),
):
    """Agent reports consent decision (accept/decline/timeout). Writes audit.

    Only the agent the session targets may report its user's decision, with
    its own agent token. A user token (including the requester's own) or a
    tenant registration key is refused, so nobody can record consent on the
    endpoint user's behalf. (This route used to require a user login as well
    as an agent token in the body, so no agent could ever reach it.)
    """
    if getattr(principal, "role", "") != "agent":
        raise HTTPException(status_code=401, detail="Agent authentication required")
    agent = principal

    decision = payload.get("decision")
    if decision not in _CONTROL_CONSENT_DECISIONS:
        raise HTTPException(status_code=400, detail="Invalid decision: must be accept, decline, or timeout")

    db = get_database()
    # Raw collection: the request runs in the agent's tenant, but a super
    # admin's session is stamped "platform-admin", so the tenant wrapper would
    # never find it. The ownership check below is what scopes this route.
    sessions = db._db.remote_sessions
    session = await sessions.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # The agent asks its user before streaming the screen at all, so a view
    # session's decision is audited too (it used to be refused here, leaving
    # view-mode consent unrecorded). Shell sessions never prompt.
    mode = _CONSENT_MODES.get(session.get("type"))
    if mode is None:
        raise HTTPException(status_code=400, detail="Consent only applies to desktop view and control sessions")

    # The session's own agent only. Comparing tenants was not enough: a super
    # admin's session carries "platform-admin", which skipped the check, so any
    # tenant's agent could record consent for it.
    session_tenant = session.get("tenantId")
    if agent.username != session.get("agent_id"):
        raise HTTPException(status_code=403, detail="Agent does not own this session")

    tenant_id = session_tenant
    disconnect_reason = {
        "accept": None,
        "decline": "consent_declined",
        "timeout": "consent_timeout",
    }.get(decision)

    if disconnect_reason:
        close_session(session_id)
        await sessions.update_one(
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
            "mode": mode,
        },
    )

    if decision == "accept":
        await sessions.update_one(
            {"session_id": session_id}, {"$set": {"status": "active"}}
        )

    return {"status": "recorded", "decision": decision}


@router.get("/capabilities", dependencies=[Depends(REMOTE_ACCESS_GUARD)])
async def get_capabilities(current_user=Depends(get_current_user)):
    """Return what the caller can do: view vs control."""
    can_view = await rbac_utils.verify_permission(current_user, "view:remote_access")
    can_control = await rbac_utils.verify_permission(current_user, "control:remote_access")
    return {"can_view": can_view, "can_control": can_control}
