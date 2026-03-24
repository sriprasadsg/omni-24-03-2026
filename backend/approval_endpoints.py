from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from database import get_database
from approval_service import get_approval_service

router = APIRouter(prefix="/api/approvals", tags=["Approvals"])

@router.get("/pending")
async def get_pending_approvals(user_email: str = "", tenant_id: str = "default"):
    """Get all pending approval requests (optionally filtered by user email)."""
    db = get_database()
    service = get_approval_service(db)
    try:
        if user_email:
            return await service.get_pending_for_user(user_email, tenant_id)
        else:
            # Return all pending approvals for tenant
            cursor = db.approval_requests.find(
                {"tenantId": tenant_id, "status": "pending"}, {"_id": 0}
            ).sort("createdAt", -1)
            return await cursor.to_list(length=100)
    except Exception:
        return []

@router.get("/history")
async def get_approval_history(tenant_id: str = "default"):
    """Get history of all approval requests for a tenant."""
    db = get_database()
    cursor = db.approval_requests.find({"tenantId": tenant_id}, {"_id": 0}).sort("createdAt", -1)
    return await cursor.to_list(length=100)

@router.post("/{request_id}/decide")
async def submit_approval_decision(request_id: str, data: Dict[str, Any]):
    """
    Submit an approval or rejection decision.
    Payload: {"user_email": "...", "decision": "approve", "comments": "..."}
    """
    db = get_database()
    service = get_approval_service(db)
    
    user_email = data.get("user_email")
    decision = data.get("decision")
    comments = data.get("comments")
    
    if not user_email or not decision:
        raise HTTPException(status_code=400, detail="user_email and decision are required")
    
    try:
        updated_request = await service.submit_decision(request_id, user_email, decision, comments)
        return {"success": True, "request": updated_request}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{request_id}")
async def get_approval_request(request_id: str):
    """Get details of a specific approval request."""
    db = get_database()
    service = get_approval_service(db)
    request = await service.get_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    return request
