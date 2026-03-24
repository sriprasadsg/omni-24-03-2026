from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/historical")
async def get_historical_data(current_user: TokenData = Depends(get_current_user)):
    """Get historical analytics data"""
    db = get_database()
    # Get the most recent historical data point
    cursor = db.analytics_historical.find({}, {"_id": 0}).sort("date", -1).limit(1)
    data = await cursor.to_list(length=1)
    
    if data:
        return data[0]
        
    # Return default empty structure if no data exists
    return {
        "alerts": [],
        "compliance": [],
        "vulnerabilities": []
    }

@router.get("/bi")
async def get_bi_metrics(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user)
):
    """Get advanced BI metrics"""
    db = get_database()
    from bi_analytics_service import get_bi_analytics_service
    service = get_bi_analytics_service(db)
    return await service.get_bi_metrics(tenant_id)
