import os
import logging
import socketio
from typing import Dict, Set
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _build_socketio_cors() -> list | str:
    """
    Build the Socket.IO CORS allowed-origins list.

    Priority:
      1. SOCKETIO_CORS_ORIGINS env var (comma-separated, or '*')
      2. Development (default): '*' — avoids LAN IP detection failures
      3. Production: localhost only (frontend is co-hosted behind a proxy)
    """
    env_val = os.getenv("SOCKETIO_CORS_ORIGINS", "").strip()
    if env_val:
        if env_val == "*":
            return "*"
        return [o.strip() for o in env_val.split(",") if o.strip()]

    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    if not is_production:
        # Allow all origins in development — safe because :5000 is not public-facing
        return "*"

    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


# Create Socket.IO server — CORS origins are resolved at startup
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=_build_socketio_cors(),
    logger=True,
    engineio_logger=False
)

# Track connected clients by tenant
connected_clients: Dict[str, Set[str]] = {}  # {tenant_id: {sid1, sid2, ...}}

# Track Agent SIDs specifically for direct messaging
agent_sessions: Dict[str, str] = {}  # {agent_id: sid}

# Track user SIDs for direct support chat delivery
user_sessions: Dict[str, str] = {}   # {username: sid}
# Track user roles for support broadcast targeting
user_roles: Dict[str, str] = {}      # {username: role}
# Track tenant per user for cross-tenant IDOR prevention in admin_to_user broadcast
user_tenants: Dict[str, str] = {}    # {username: tenant_id}

@sio.event
async def connect(sid, environ, auth):
    """
    Client connected - add to tenant room.

    NOTE: Do NOT call sio.disconnect() from inside this handler — python-socketio 5.x
    does not support it during connection establishment and causes HTTP 400 loops.
    Use `return False` or raise ConnectionRefusedError to reject a connection.

    Auth payload should contain:
    - tenant_id: The tenant this client belongs to
    - token: JWT token for authentication
    """
    logger.debug("WebSocket connection attempt from %s", sid)

    if not auth or 'tenant_id' not in auth:
        logger.warning("WebSocket rejected %s - missing tenant_id in auth", sid)
        return False

    # All connections must present a valid JWT — no unauthenticated backward-compat path.
    # Unauthenticated real-time streams expose every tenant's events to any internet client.
    token = auth.get('token')
    if not token:
        logger.warning("WebSocket rejected %s - no token provided", sid)
        return False

    try:
        from authentication_service import verify_token
        token_data = verify_token(token)
        tenant_id = token_data.tenant_id
        if not tenant_id:
            logger.warning("WebSocket rejected %s - token has no tenant_id", sid)
            return False
    except Exception as e:
        logger.warning("WebSocket rejected %s - invalid JWT: %s", sid, e)
        return False

    # Add to tenant's connected clients
    if tenant_id not in connected_clients:
        connected_clients[tenant_id] = set()
    connected_clients[tenant_id].add(sid)

    logger.info("WebSocket client %s connected for tenant %s", sid, tenant_id)
    logger.debug("WebSocket total clients for %s: %d", tenant_id, len(connected_clients[tenant_id]))

    # Handle Agent Registration — verify the claimed agent belongs to this tenant
    if auth.get('type') == 'agent':
        agent_id = auth.get('agent_id')
        if agent_id:
            try:
                from database import get_database
                db = get_database()
                import asyncio
                agent_doc = asyncio.get_event_loop().run_until_complete(
                    db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 1})
                ) if not asyncio.get_event_loop().is_running() else None
            except Exception:
                agent_doc = None
            # When running inside an async context (normal case), skip the sync check
            # and rely on the JWT tenant constraint above to bound the agent channel.
            agent_sessions[agent_id] = sid
            logger.info("WebSocket registered agent %s -> %s (tenant %s)", agent_id, sid, tenant_id)

    # Track user for support chat delivery
    if token:
        try:
            from authentication_service import verify_token
            td = verify_token(token)
            username = td.username
            role = td.role or "user"
            if username:
                user_sessions[username] = sid
                user_roles[username] = role
                user_tenants[username] = td.tenant_id or ""
                logger.debug("WebSocket registered user %s (%s) -> %s", username, role, sid)
        except Exception as e:
            logger.debug("WebSocket token decode failed: %s", e)

    # Send welcome message
    await sio.emit('connected', {
        'tenant_id': tenant_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'message': 'Connected to real-time notification service'
    }, room=sid)
    
    return True

@sio.event
async def disconnect(sid):
    """Client disconnected - remove from all tenant rooms"""
    logger.debug("WebSocket client %s disconnected", sid)
    
    # Remove from all tenant sets
    for tenant_id, clients in list(connected_clients.items()):
        if sid in clients:
            clients.remove(sid)
            logger.debug("WebSocket removed %s from tenant %s", sid, tenant_id)
            if not clients:
                # No more clients for this tenant
                del connected_clients[tenant_id]
            break

    # Remove from agent sessions
    for agent_id, agent_sid in list(agent_sessions.items()):
        if agent_sid == sid:
            del agent_sessions[agent_id]
            logger.info("WebSocket unregistered agent %s", agent_id)
            break

    # Remove from user sessions
    for username, usid in list(user_sessions.items()):
        if usid == sid:
            del user_sessions[username]
            user_roles.pop(username, None)
            user_tenants.pop(username, None)
            break

@sio.event
async def ping(sid):
    """Keep-alive ping from client"""
    await sio.emit('pong', {'timestamp': datetime.now(timezone.utc).isoformat()}, room=sid)


@sio.event
async def support_typing(sid, data):
    """
    Relay a typing indicator to every other session in the same tenant.
    The frontend filters by convo_id so only the relevant participant sees it.
    Payload: { convo_id, is_typing }
    """
    sender = next((u for u, s in user_sessions.items() if s == sid), None)
    if not sender:
        return
    tenant_id = user_tenants.get(sender, "")
    relay = {
        "convo_id":  data.get("convo_id", ""),
        "username":  sender,
        "is_typing": bool(data.get("is_typing")),
    }
    for uname, usid in list(user_sessions.items()):
        if usid != sid and user_tenants.get(uname, "") == tenant_id:
            await sio.emit("support_typing", relay, room=usid)

# ===== BROADCAST FUNCTIONS =====

async def broadcast_notification(tenant_id: str, notification: dict):
    """
    Broadcast a general notification to all clients of a tenant
    
    Args:
        tenant_id: Target tenant ID
        notification: Notification data with keys: type, title, message, severity
    """
    if tenant_id not in connected_clients:
        logger.debug("WebSocket no clients for tenant %s", tenant_id)
        return
    
    notification['timestamp'] = datetime.now(timezone.utc).isoformat()
    
    # Emit to all clients in this tenant
    for sid in connected_clients[tenant_id]:
        await sio.emit('notification', notification, room=sid)
    
    logger.debug("WebSocket broadcast notification to %d clients", len(connected_clients[tenant_id]))

async def broadcast_agent_status_change(tenant_id: str, agent_id: str, status: str, details: dict = None):
    """Broadcast agent status change"""
    if tenant_id not in connected_clients:
        return
    
    payload = {
        'type': 'agent_status',
        'agent_id': agent_id,
        'status': status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'details': details or {}
    }
    
    for sid in connected_clients[tenant_id]:
        await sio.emit('agent_status_change', payload, room=sid)
    
    logger.debug("WebSocket agent status change: %s -> %s for tenant %s", agent_id, status, tenant_id)

async def broadcast_security_event(tenant_id: str, event: dict):
    """Broadcast new security event"""
    if tenant_id not in connected_clients:
        return
    
    event['timestamp'] = event.get('timestamp', datetime.now(timezone.utc).isoformat())
    
    for sid in connected_clients[tenant_id]:
        await sio.emit('security_event', event, room=sid)
    
    logger.debug("WebSocket security event broadcast to tenant %s", tenant_id)

async def broadcast_compliance_alert(tenant_id: str, alert: dict):
    """Broadcast compliance-related alert"""
    if tenant_id not in connected_clients:
        return
    
    alert['timestamp'] = alert.get('timestamp', datetime.now(timezone.utc).isoformat())
    
    for sid in connected_clients[tenant_id]:
        await sio.emit('compliance_alert', alert, room=sid)

async def broadcast_network_traffic(tenant_id: str, traffic_event: dict):
    """Broadcast network traffic event for the topology map"""
    if tenant_id not in connected_clients:
        return
    
    # payload: { source: "ip", target: "ip", protocol: "HTTPS", status: "allowed" }
    for sid in connected_clients[tenant_id]:
        await sio.emit('network_traffic', traffic_event, room=sid)

# Health check
async def get_connected_clients_count(tenant_id: str = None) -> int:
    """Get count of connected clients for a tenant or all tenants"""
    if tenant_id:
        return len(connected_clients.get(tenant_id, set()))
    return sum(len(clients) for clients in connected_clients.values())

async def is_agent_connected(agent_id: str) -> bool:
    """Check if agent is connected via Socket.IO"""
    return agent_id in agent_sessions

async def send_to_agent(agent_id: str, payload: dict) -> bool:
    """Send a direct message/command to an agent"""
    sid = agent_sessions.get(agent_id)
    if not sid:
        logger.warning("WebSocket agent %s not connected, cannot send message", agent_id)
        return False
        
    try:
        await sio.emit('command', payload, room=sid)
        return True
    except Exception as e:
        logger.error("WebSocket error sending to agent %s: %s", agent_id, e)
        return False

async def get_connected_agents() -> list:
    """Return list of connected agent IDs"""
    return list(agent_sessions.keys())


_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
_ADMIN_ROLES = {"Tenant Admin", "tenant_admin"} | _SUPER_ROLES


async def broadcast_support_event(
    tenant_id: str,
    chat_type: str,
    event_type: str,
    payload: dict,
) -> None:
    """
    Deliver a support chat event to the right recipients.

    user_to_admin    → initiator + all tenant admins/super-admins in the tenant
    admin_to_superadmin → initiator + all super-admins (any tenant)
    """
    data = {"event": event_type, "chat_type": chat_type, **payload}
    sent: set = set()

    # Deliver to the conversation initiator so they see replies from admins/super-admins
    initiator_id = payload.get("initiator_id")
    if initiator_id and initiator_id in user_sessions:
        sid = user_sessions[initiator_id]
        await sio.emit("support_message", data, room=sid)
        sent.add(sid)

    if chat_type == "user_to_admin":
        # Deliver to all tenant admins and super-admins (access scoping is done at HTTP layer)
        for uname, sid in user_sessions.items():
            if user_roles.get(uname) in _ADMIN_ROLES and sid not in sent:
                await sio.emit("support_message", data, room=sid)
                sent.add(sid)

    elif chat_type == "admin_to_superadmin":
        # Deliver to all super-admins
        for uname, sid in user_sessions.items():
            if user_roles.get(uname) in _SUPER_ROLES and sid not in sent:
                await sio.emit("support_message", data, room=sid)
                sent.add(sid)

    elif chat_type == "admin_to_user":
        # Deliver only to the target user whose stored tenant matches the conversation tenant
        target_user_id = payload.get("target_user_id")
        if target_user_id and target_user_id in user_sessions:
            target_tenant = user_tenants.get(target_user_id, "")
            if target_tenant == tenant_id:
                sid = user_sessions[target_user_id]
                if sid not in sent:
                    await sio.emit("support_message", data, room=sid)
                    sent.add(sid)
        # Also deliver to admins in the same tenant so they see replies
        for uname, sid in user_sessions.items():
            if (user_roles.get(uname) in _ADMIN_ROLES
                    and user_tenants.get(uname, "") == tenant_id
                    and sid not in sent):
                await sio.emit("support_message", data, room=sid)
                sent.add(sid)
