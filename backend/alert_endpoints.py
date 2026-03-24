from fastapi import APIRouter, Depends
from typing import List
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])

@router.get("")
async def get_alerts(current_user: TokenData = Depends(get_current_user)):
    """Get all alerts"""
    db = get_database()
    alerts = await db.alerts.find({}, {"_id": 0}).to_list(length=100)
    return alerts
