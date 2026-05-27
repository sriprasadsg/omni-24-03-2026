import os
import logging
import socketio
from typing import Dict, Set
from datetime import datetime, timezone
import asyncio

logger = logging.getLogger(__name__)

# Create Socket.IO server with CORS support
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
    ],
    logger=True,
    engineio_logger=False
)

# Track connected clients by tenant
connected_clients: Dict[str, Set[str]] = {}  # {tenant_id: {sid1, sid2, ...}}

# Track Agent SIDs specifically for direct messaging
agent_sessions: Dict[str, str] = {} # {agent_id: sid}

@sio.event
async def connect(sid, environ, auth):
    """
    Client connected - add to tenant room
    
    Auth payload should contain:
    - tenant_id: The tenant this client belongs to
    - token: JWT token for authentication (optional for now)
    """
    logger.debug("WebSocket connection attempt from %s", sid)
    
    if not auth or 'tenant_id' not in auth:
        logger.warning("WebSocket rejected %s - missing tenant_id in auth", sid)
        await sio.disconnect(sid)
        return False

    # Validate JWT and derive tenant_id from the token, not from the client-supplied dict
    token = auth.get('token')
    if token:
        try:
            from authentication_service import verify_token
            token_data = verify_token(token)
            tenant_id = token_data.tenant_id
            if not tenant_id:
                logger.warning("WebSocket rejected %s - token has no tenant_id", sid)
                await sio.disconnect(sid)
                return False
        except Exception:
            logger.warning("WebSocket rejected %s - invalid JWT", sid)
            await sio.disconnect(sid)
            return False
    else:
        # No token supplied — still accept for backward-compat but use client-provided tenant
        tenant_id = auth.get('tenant_id')
    
    # Add to tenant's connected clients
    if tenant_id not in connected_clients:
        connected_clients[tenant_id] = set()
    connected_clients[tenant_id].add(sid)
    
    logger.info("WebSocket client %s connected for tenant %s", sid, tenant_id)
    logger.debug("WebSocket total clients for %s: %d", tenant_id, len(connected_clients[tenant_id]))
    
    # Handle Agent Registration
    if auth.get('type') == 'agent':
        agent_id = auth.get('agent_id')
        if agent_id:
            agent_sessions[agent_id] = sid
            logger.info("WebSocket registered agent %s -> %s", agent_id, sid)
    
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

@sio.event
async def ping(sid):
    """Keep-alive ping from client"""
    await sio.emit('pong', {'timestamp': datetime.now(timezone.utc).isoformat()}, room=sid)

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
