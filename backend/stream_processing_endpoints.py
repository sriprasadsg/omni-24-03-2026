from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, Any, List
from streaming_service import broker, processor
import asyncio
import json
from database import get_database
from siem_engine import get_siem_engine

router = APIRouter(prefix="/api/stream", tags=["Streaming Analytics"])

@router.on_event("startup")
async def startup_event():
    await processor.start()

@router.post("/publish/{topic}")
async def publish_event(topic: str, event: Dict[str, Any]):
    """
    Publish an event to a specific topic.
    If the topic is raw_logs, forward to the SIEM Engine.
    """
    await broker.publish(topic, event)
    
    if topic == "raw_logs":
        try:
            db = get_database()
            siem = get_siem_engine(db)
            # Expecting event structure: {"agent_id": ..., "tenant_id": ..., "logs": [...]}
            agent_id = event.get("agent_id", "unknown")
            tenant_id = event.get("tenant_id", "unknown")
            logs = event.get("logs", [])
            if logs:
                await siem.ingest_logs(logs, tenant_id, agent_id)
        except Exception as e:
            print(f"[Streaming] Failed to process raw logs in SIEM engine: {e}")
            
    return {"status": "published", "topic": topic}

@router.get("/metrics")
async def get_metrics():
    """
    Get current broker metrics.
    """
    return broker.get_metrics()

@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.
    Subscribes to 'system_stats', 'logs', and 'security_events'.
    """
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
        print(f"WebSocket error: {e}")
        for topic in topics:
            broker.unsubscribe(topic, client_callback)
