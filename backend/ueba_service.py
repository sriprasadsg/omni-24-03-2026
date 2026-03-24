from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from database import get_database

router = APIRouter(prefix="/api/ueba", tags=["UEBA"])
logger = logging.getLogger(__name__)

# --- Models ---
class ShadowAIEvent(BaseModel):
    agent_id: str
    process: str
    remote_ip: str
    remote_host: str
    timestamp: str

class LoginEvent(BaseModel):
    user_id: str
    ip_address: str
    user_agent: str
    timestamp: str

# --- Service Logic ---

async def persist_security_alert(db, alert_type: str, severity: str, title: str, description: str, metadata: Dict[str, Any]):
    """Helper to save alerts to database"""
    alert = {
        "type": alert_type,
        "severity": severity,
        "title": title,
        "description": description,
        "metadata": metadata,
        "created_at": datetime.utcnow().isoformat(),
        "status": "new",
        "timestamp": datetime.utcnow().isoformat()
    }
    await db.security_alerts.insert_one(alert)

# --- Endpoints ---

@router.post("/shadow-ai")
async def report_shadow_ai(event: ShadowAIEvent, background_tasks: BackgroundTasks, db=Depends(get_database)):
    """
    Ingest Shadow AI detection events from agents.
    """
    logger.warning(f"Shadow AI Detected: {event.process} -> {event.remote_host} on {event.agent_id}")
    
    # Store raw event
    await db.shadow_ai_events.insert_one(event.dict())
    
    # Create Alert
    background_tasks.add_task(
        persist_security_alert,
        db,
        alert_type="shadow_ai",
        severity="medium",
        title=f"Shadow AI Usage Detected: {event.remote_host}",
        description=f"Process '{event.process}' on agent {event.agent_id} connected to {event.remote_host}.",
        metadata=event.dict()
    )
    
    return {"status": "recorded"}

@router.post("/analyze-login")
async def analyze_login_behavior(event: LoginEvent, background_tasks: BackgroundTasks, db=Depends(get_database)):
    """
    Analyze login for behavioral anomalies (e.g. impossible travel, weird hours).
    Simple MVP: Flag logins between 00:00 and 05:00 local server time.
    """
    risk_score = 0
    reasons = []
    
    # Parse timestamp
    try:
        dt = datetime.fromisoformat(event.timestamp.replace('Z', '+00:00'))
        hour = dt.hour
        
        # Rule 1: Time of Day Anomaly
        if 0 <= hour < 5:
            risk_score += 50
            reasons.append("Off-hours login (Midnight - 5 AM)")
            
    except Exception as e:
        logger.error(f"Error parsing timestamp: {e}")
    
    # Rule 2: IP Reputation (Mock)
    if event.ip_address.startswith("192.168.1.1"):
        # Allow listed
        pass
    else:
        # Mock external check
        pass

    result = {
        "risk_score": risk_score,
        "reasons": reasons,
        "is_anomalous": risk_score > 30
    }

    if result["is_anomalous"]:
        logger.warning(f"Anomalous Login Detected: {event.user_id} Score={risk_score}")
        background_tasks.add_task(
            persist_security_alert,
            db,
            alert_type="ueba_anomaly",
            severity="high" if risk_score > 70 else "medium",
            title=f"Anomalous Login: {event.user_id}",
            description=f"Unusual behavior detected: {', '.join(reasons)}",
            metadata={**event.dict(), "analysis": result}
        )
    
    return result

@router.get("/shadow-ai/events")
async def get_shadow_ai_events(limit: int = 50, db=Depends(get_database)):
    """Get recent Shadow AI events"""
    cursor = db.shadow_ai_events.find().sort("timestamp", -1).limit(limit)
    events = await cursor.to_list(length=limit)
    # Convert ObjectId to str
    for e in events:
        e["id"] = str(e["_id"])
        del e["_id"]
    return events

@router.get("/stats")
async def get_ueba_stats(db=Depends(get_database)):
    """Get UEBA statistics"""
    shadow_count = await db.shadow_ai_events.count_documents({})
    # Count specific ueba alerts
    anomaly_count = await db.security_alerts.count_documents({"type": "ueba_anomaly"})
    
    return {
        "shadow_ai_detections": shadow_count,
        "login_anomalies": anomaly_count
    }
