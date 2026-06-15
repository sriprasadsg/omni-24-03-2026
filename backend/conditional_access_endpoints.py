"""Conditional Access Policy REST endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Any, Dict
import logging

from auth_utils import get_current_user
from auth_types import TokenData
import conditional_access_service as svc

router = APIRouter(prefix="/api/conditional-access", tags=["Conditional Access"])
logger = logging.getLogger(__name__)


def _tenant(user: TokenData) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return user.tenant_id


@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    return await svc.get_summary(_tenant(current_user))


@router.get("/policies")
async def list_policies(current_user: TokenData = Depends(get_current_user)):
    policies = await svc.list_policies(_tenant(current_user))
    return {"policies": policies, "total": len(policies)}


@router.post("/policies")
async def create_policy(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        payload["created_by"] = current_user.username or ""
        policy = await svc.create_policy(_tenant(current_user), payload)
        return {"policy": policy, "message": "Policy created"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/policies/{policy_id}")
async def get_policy(policy_id: str, current_user: TokenData = Depends(get_current_user)):
    policy = await svc.get_policy(policy_id, _tenant(current_user))
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"policy": policy}


@router.patch("/policies/{policy_id}")
async def update_policy(
    policy_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        policy = await svc.update_policy(policy_id, _tenant(current_user), payload)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        return {"policy": policy}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/policies/{policy_id}")
async def delete_policy(policy_id: str, current_user: TokenData = Depends(get_current_user)):
    deleted = await svc.delete_policy(policy_id, _tenant(current_user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"message": "Policy deleted"}


@router.post("/evaluate")
async def evaluate(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    """Evaluate conditional access policies against a device/session context."""
    result = await svc.evaluate(_tenant(current_user), payload)
    return result
