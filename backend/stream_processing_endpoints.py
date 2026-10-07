from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
import logging
from typing import Dict, Any
from streaming_service import broker, processor
import asyncio
from database import get_database
from siem_engine import get_siem_engine
from authentication_service import get_current_user, get_current_user_or_agent, verify_token_async
from rbac_utils import is_super_admin, verify_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["Streaming Analytics"])

@router.on_event("startup")
async def startup_event():
    await processor.start()

@router.post("/publish/{topic}")
async def publish_event(
    topic: str,
    event: Dict[str, Any],
    current_user=Depends(get_current_user_or_agent),
):
    """
    Publish an event to a specific topic.
    If the topic is raw_logs, forward to the SIEM Engine.

    raw_logs is ingested into the caller's own tenant (from the token, never the
    body) and is open to agents and manage:settings holders. Every other topic
    is broadcast to all live-feed clients across tenants, so only super-admins
    may publish to it.
    """
    role = getattr(current_user, "role", "")
    is_agent = role == "agent"
    if topic != "raw_logs":
        if not is_super_admin(role):
            raise HTTPException(status_code=403, detail="Only platform super-admins may publish to this topic")
    elif not is_agent and not await verify_permission(current_user, "manage:settings"):
        raise HTTPException(status_code=403, detail="Missing required permission: manage:settings")

    await broker.publish(topic, event)

    if topic == "raw_logs":
        try:
            db = get_database()
            siem = get_siem_engine(db)
            # Expecting event structure: {"agent_id": ..., "logs": [...]}
            agent_id = current_user.username if is_agent else event.get("agent_id", "unknown")
            tenant_id = getattr(current_user, "tenant_id", None) or None
            logs = event.get("logs", [])
            if logs and tenant_id:
                await siem.ingest_logs(logs, tenant_id, agent_id)
        except Exception as e:
            logger.error("Streaming: Failed to process raw logs in SIEM engine: %s", e)
            
    return {"status": "published", "topic": topic}

@router.get("/metrics")
async def get_metrics(current_user=Depends(get_current_user)):
    """
    Get current broker metrics.
    """
    return broker.get_metrics()

@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.
    Subscribes to 'system_stats', 'logs', and 'security_events'.
    Requires a valid user JWT passed as the ?token= query parameter.
    """
    try:
        await verify_token_async(websocket.query_params.get("token", ""), allow_agent=False)
    except Exception:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    
    # Queue to hold messages for this client
    queue = asyncio.Queue()
    
    async def client_callback(event):
        await queue.put(event)

    # Subscribe this client to topics
    topics = ["system_stats", "logs", "security_events"]
    for topic in topics:
        broker.subscribe(topic, client_callback)
    
    try:
        while True:
            # Wait for next event in queue
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        # Unsubscribe on disconnect
        for topic in topics:
            broker.unsubscribe(topic, client_callback)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        for topic in topics:
            broker.unsubscribe(topic, client_callback)
