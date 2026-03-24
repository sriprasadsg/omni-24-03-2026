from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from typing import List, Dict, Any, Optional
from datetime import datetime
from ueba_engine import ueba_engine
from database import get_database
from tenant_context import get_tenant_id
from authentication_service import get_current_user

router = APIRouter()

@router.get("/risk-scores", dependencies=[Depends(get_current_user)])
async def get_all_risk_scores(tenant_id: str = Depends(get_tenant_id)):
    """
    Returns the latest risk scores for all users in the tenant, sorted by highest risk first.
    """
    db = get_database()
    
    # Get latest risk calculations
    scores_cursor = db.ueba_risk_scores.find({"tenantId": tenant_id}).sort("score", -1)
    scores = await scores_cursor.to_list(100)
    
    # Join with user table to get names/emails
    user_ids = [s.get("userId") for s in scores if s.get("userId")]
    users_cursor = db.users.find({"id": {"$in": user_ids}, "tenantId": tenant_id})
    users_list = await users_cursor.to_list(None)
    
    user_map = {u.get("id"): u for u in users_list}
    
    results = []
    for score_doc in scores:
        user_info = user_map.get(score_doc.get("userId"), {})
        
        results.append({
            "userId": score_doc.get("userId"),
            "userName": user_info.get("name", "Unknown User"),
            "userEmail": user_info.get("email", "Unknown Email"),
            "userAvatar": user_info.get("avatar", ""),
            "score": score_doc.get("score", 0),
            "ruleScore": score_doc.get("ruleScore", 0),
            "mlScore": score_doc.get("mlScore", 0),
            "reasons": score_doc.get("reasons", []),
            "lastCalculated": score_doc.get("timestamp")
        })
        
    return {"results": results}

@router.get("/user/{user_id}/history", dependencies=[Depends(get_current_user)])
async def get_user_risk_history(user_id: str, tenant_id: str = Depends(get_tenant_id)):
    """
    Returns the historical risk scores for a specific user to plot on a graph.
    """
    db = get_database()
    
    history_cursor = db.ueba_risk_history.find(
        {"tenantId": tenant_id, "userId": user_id}
    ).sort("timestamp", 1) # chronological order
    
    history = await history_cursor.to_list(100)
    
    # Format for charting
    chart_data = []
    for doc in history:
        chart_data.append({
            "timestamp": doc.get("timestamp"),
            "score": doc.get("score"),
            "vector": doc.get("vector", {})
        })
        
    return {"history": chart_data}

@router.post("/calculate-all", dependencies=[Depends(get_current_user)])
async def calculate_all_scores(background_tasks: BackgroundTasks, tenant_id: str = Depends(get_tenant_id)):
    """
    Triggers a manual recalculation of UEBA risk scores for all users in the tenant.
    Runs asynchronously.
    """
    async def run_calculation():
        db = get_database()
        users = await db.users.find({"tenantId": tenant_id}).to_list(None)
        
        for user in users:
            uid = user.get("id")
            if uid:
                try:
                    await ueba_engine.calculate_risk_score(tenant_id, uid)
                except Exception as e:
                    print(f"[UEBA Task] Error calculating risk for user {uid}: {e}")
                    
    background_tasks.add_task(run_calculation)
    return {"success": True, "message": "UEBA Risk computation started in the background."}

@router.get("/alerts", dependencies=[Depends(get_current_user)])
async def get_ueba_alerts(tenant_id: str = Depends(get_tenant_id)):
    """
    Returns active high-severity UEBA alerts.
    """
    db = get_database()
    alerts_cursor = db.ueba_alerts.find({"tenantId": tenant_id}).sort("timestamp", -1)
    alerts = await alerts_cursor.to_list(50)
    
    # Remove _id from response
    for a in alerts:
        a["_id"] = str(a["_id"])
        
    return {"alerts": alerts}
