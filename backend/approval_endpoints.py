import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from database import get_database
from approval_service import get_approval_service
from rbac_utils import require_permission

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["Approvals"])


def _tid(user):
    if isinstance(user, dict):
        return user.get("tenant_id") or user.get("tenantId") or None
    return getattr(user, "tenant_id", None) or getattr(user, "tenantId", None) or None


@router.get("/pending")
async def get_pending_approvals(
    user_email: str = "",
    current_user: dict = Depends(require_permission("view:approvals")),
):
    """Get all pending approval requests (optionally filtered by user email)."""
    db = get_database()
    service = get_approval_service(db)
    tenant_id = _tid(current_user)
    try:
        if user_email:
            return await service.get_pending_for_user(user_email, tenant_id)
        cursor = db.approval_requests.find(
            {"tenantId": tenant_id, "status": "pending"}, {"_id": 0}
        ).sort("createdAt", -1)
        return await cursor.to_list(length=100)
    except Exception as exc:
        _log.error("Failed to fetch pending approvals: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/history")
async def get_approval_history(
    current_user: dict = Depends(require_permission("view:approvals")),
):
    """Get history of all approval requests for a tenant."""
    db = get_database()
    tenant_id = _tid(current_user)
    cursor = db.approval_requests.find({"tenantId": tenant_id}, {"_id": 0}).sort("createdAt", -1)
    return await cursor.to_list(length=100)


@router.post("/{request_id}/decide")
async def submit_approval_decision(
    request_id: str,
    data: Dict[str, Any],
    current_user: dict = Depends(require_permission("manage:approvals")),
):
    """
    Submit an approval or rejection decision.
    Payload: {"decision": "approve", "comments": "..."}
    """
    db = get_database()
    service = get_approval_service(db)
    tenant_id = _tid(current_user)

    # Always derive email from the verified JWT — never accept it from the request body
    user_email = (
        current_user.get("email") if isinstance(current_user, dict)
        else getattr(current_user, "email", None)
    )
    if not user_email:
        raise HTTPException(status_code=401, detail="Could not determine caller identity")

    decision = data.get("decision")
    if not decision:
        raise HTTPException(status_code=400, detail="decision is required")
    comments = data.get("comments")

    try:
        updated_request = await service.submit_decision(
            request_id, user_email, decision, comments, tenant_id=tenant_id
        )
        return {"success": True, "request": updated_request}
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{request_id}")
async def get_approval_request(
    request_id: str,
    current_user: dict = Depends(require_permission("view:approvals")),
):
    """Get details of a specific approval request."""
    db = get_database()
    service = get_approval_service(db)
    tenant_id = _tid(current_user)
    request = await service.get_request(request_id, tenant_id=tenant_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    return request
