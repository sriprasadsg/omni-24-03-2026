"""
ITDR API Endpoints
REST API to surface Identity Threat Detection & Response alerts.
Also hooks into auth login events via hooks called at login/role-change time.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from itdr_service import itdr_service

router = APIRouter(prefix="/api/itdr", tags=["ITDR - Identity Threat Detection"])


@router.get("/alerts")
async def get_itdr_alerts(
    unack_only: bool = Query(default=False),
    limit: int = Query(default=100, le=500),
    current_user: TokenData = Depends(get_current_user)
):
    """Get ITDR threat alerts."""
    return await itdr_service.get_alerts(limit=limit, unack_only=unack_only)


@router.patch("/alerts/{alert_id}/acknowledge")
async def acknowledge_itdr_alert(
    alert_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Acknowledge an ITDR alert."""
    success = await itdr_service.acknowledge_alert(alert_id, by=current_user.username)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "acknowledged", "alert_id": alert_id}


@router.get("/summary")
async def get_itdr_summary(current_user: TokenData = Depends(get_current_user)):
    """Get ITDR summary stats."""
    db = get_database()
    by_type = {}
    pipeline = [
        {"$match": {}},
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
    ]
    async for doc in db.itdr_alerts.aggregate(pipeline):
        by_type[doc["_id"]] = doc["count"]

    total = await db.itdr_alerts.count_documents({})
    unack = await db.itdr_alerts.count_documents({"acknowledged": False})
    critical = await db.itdr_alerts.count_documents({"severity": "critical", "acknowledged": False})
    return {
        "total_alerts": total,
        "unacknowledged": unack,
        "critical_unacknowledged": critical,
        "by_type": by_type,
    }
