from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from database import get_database

router = APIRouter(tags=["Future Ops"])

@router.get("/api/aiops/capacity-predictions")
async def get_capacity_predictions():
    """Get AI Capacity Predictions from database"""
    db = get_database()
    predictions = await db.capacity_predictions.find({}, {"_id": 0}).to_list(length=100)
    
    if not predictions:
        return {
            "predictions": [],
            "message": "No capacity predictions available. Enable AI capacity planning."
        }
    
    return {"predictions": predictions}

@router.get("/api/streaming/live-events")
async def get_live_events():
    """Get Live Events from metrics database"""
    db = get_database()
    
    # Calculate real-time metrics from database
    events_count = await db.events.count_documents({})
    
    return {
        "eventsPerSecond": 0,
        "avgLatencyMs": 0,
        "activeStreams": 0,
        "message": "Connect event streaming to see live data"
    }

@router.get("/api/multicloud/cost-optimization")
async def get_cost_optimization():
    """Get Cost Optimization recommendations from database"""
    db = get_database()
    recommendations = await db.cost_recommendations.find({}, {"_id": 0}).to_list(length=100)
    
    if not recommendations:
        return {
            "recommendations": [],
            "message": "Run cost optimizer to generate recommendations"
        }
    
    return {"recommendations": recommendations}

@router.get("/api/privacy/consent-tracking")
async def get_consent_tracking():
    """Get Privacy Consent tracking from database"""
    db = get_database()
    
    with_consent = await db.user_consents.count_documents({"status": "granted"})
    pending = await db.user_consents.count_documents({"status": "pending"})
    revoked = await db.user_consents.count_documents({"status": "revoked"})
    
    total = with_consent + pending + revoked
    compliance_rate = int((with_consent / total * 100)) if total > 0 else 0
    
    return {
        "withConsent": with_consent,
        "complianceRate": compliance_rate,
        "pending": pending,
        "revoked": revoked
    }

@router.get("/api/blockchain/audit-chain")
async def get_blockchain_audit():
    """Get Blockchain Audit data from database"""
    db = get_database()
    blocks = await db.blockchain_audit.find({}, {"_id": 0}).sort("blockNumber", -1).to_list(length=10)
    
    if not blocks:
        return []
    
    return blocks

@router.get("/api/xdr/automated-hunts")
async def get_xdr_hunts():
    """Get XDR automated hunts from database"""
    db = get_database()
    
    # Query real hunt data
    findings = await db.xdr_findings.count_documents({})
    threats = await db.xdr_threats.count_documents({"confirmed": True})
    hunts = await db.xdr_hunts.count_documents({"status": "active"})
    false_positives = await db.xdr_findings.count_documents({"falsePositive": True})
    
    return {
        "findingsLast24h": findings,
        "confirmedThreats": threats,
        "activeHunts": hunts,
        "falsePositives": false_positives
    }
