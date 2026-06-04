"""
JIT Privileged Access Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Any, Dict, Optional
import logging

from auth_utils import get_current_user
from auth_types import TokenData
import jit_access_service as svc

router = APIRouter(prefix="/api/jit", tags=["JIT Access"])
logger = logging.getLogger(__name__)


@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    return await svc.get_jit_summary(
        current_user.tenant_id or "", current_user.role or ""
    )


@router.get("/requests")
async def list_requests(
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    requests = await svc.list_jit_requests(
        current_user.tenant_id or "",
        current_user.role or "",
        status=status,
        limit=limit,
    )
    return {"requests": requests, "total": len(requests)}


@router.post("/requests")
async def create_request(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        if not current_user.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        req = await svc.create_jit_request(
            requester_id=current_user.username or "",
            requester_email=current_user.username or "",
            tenant_id=current_user.tenant_id,
            data=payload,
        )
        req.pop("_id", None)
        req.pop("access_token", None)
        return {"request": req, "message": "JIT access request submitted — awaiting approval"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad request")


@router.get("/requests/{request_id}")
async def get_request(request_id: str, current_user: TokenData = Depends(get_current_user)):
    req = await svc.get_jit_request(
        request_id, current_user.tenant_id or "", current_user.role or ""
    )
    if not req:
        raise HTTPException(status_code=404, detail="JIT request not found")
    return {"request": req}


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: str,
    payload: Dict[str, Any] = Body(default={}),
    current_user: TokenData = Depends(get_current_user),
):
    role = current_user.role or ""
    if role not in ("admin", "super_admin", "security_manager"):
        raise HTTPException(status_code=403, detail="Only admins can approve JIT requests")

    try:
        result = await svc.approve_jit_request(
            request_id=request_id,
            approver_id=current_user.username or "",
            approver_email=current_user.username or "",
            tenant_id=current_user.tenant_id or None,
            role=role,
        )
        result.pop("_id", None)
        return {"request": result, "message": "JIT access approved and activated"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad request")


@router.post("/requests/{request_id}/deny")
async def deny_request(
    request_id: str,
    payload: Dict[str, Any] = Body(default={}),
    current_user: TokenData = Depends(get_current_user),
):
    role = current_user.role or ""
    if role not in ("admin", "super_admin", "security_manager"):
        raise HTTPException(status_code=403, detail="Only admins can deny JIT requests")

    success = await svc.deny_jit_request(
        request_id=request_id,
        approver_email=current_user.username or "",
        tenant_id=current_user.tenant_id or "",
        role=role,
        deny_reason=payload.get("reason", ""),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Request not found or not in pending state")
    return {"message": "JIT request denied"}


@router.post("/requests/{request_id}/revoke")
async def revoke_request(
    request_id: str,
    payload: Dict[str, Any] = Body(default={}),
    current_user: TokenData = Depends(get_current_user),
):
    role = current_user.role or ""
    if role not in ("admin", "super_admin", "security_manager"):
        raise HTTPException(status_code=403, detail="Only admins can revoke JIT access")

    success = await svc.revoke_jit_request(
        request_id=request_id,
        revoker_email=current_user.username or "",
        tenant_id=current_user.tenant_id or "",
        role=role,
        revoke_reason=payload.get("reason", "Manual revocation"),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Request not found or not in active state")
    return {"message": "JIT access revoked"}
