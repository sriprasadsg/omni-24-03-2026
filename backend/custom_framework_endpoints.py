"""
Custom Compliance Framework Builder Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Any, Dict
import logging

from auth_utils import get_current_user
from auth_types import TokenData
import custom_framework_service as svc

router = APIRouter(prefix="/api/custom-frameworks", tags=["Custom Frameworks"])
logger = logging.getLogger(__name__)


@router.get("/templates")
async def list_templates(current_user: TokenData = Depends(get_current_user)):
    return {"templates": [
        {"id": k, "name": v["name"], "description": v["description"]}
        for k, v in svc.BUILTIN_TEMPLATES.items()
    ]}


@router.get("")
async def list_frameworks(current_user: TokenData = Depends(get_current_user)):
    frameworks = await svc.list_frameworks(current_user.tenant_id or None, current_user.role or "")
    return {"frameworks": frameworks, "total": len(frameworks)}


@router.post("")
async def create_framework(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    if not payload.get("name"):
        raise HTTPException(status_code=400, detail="Framework name is required")

    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    framework = await svc.create_framework(
        current_user.tenant_id,
        current_user.username or "",
        payload,
    )
    framework.pop("_id", None)
    return {"framework": framework, "message": "Framework created successfully"}


@router.get("/{framework_id}")
async def get_framework(framework_id: str, current_user: TokenData = Depends(get_current_user)):
    fw = await svc.get_framework(framework_id, current_user.tenant_id or None, current_user.role or "")
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found")
    return {"framework": fw}


@router.put("/{framework_id}")
async def update_framework(
    framework_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    success = await svc.update_framework(framework_id, current_user.tenant_id or None, current_user.role or "", payload)
    if not success:
        raise HTTPException(status_code=404, detail="Framework not found or access denied")
    return {"message": "Framework updated successfully"}


@router.delete("/{framework_id}")
async def delete_framework(
    framework_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    success = await svc.delete_framework(framework_id, current_user.tenant_id or None, current_user.role or "")
    if not success:
        raise HTTPException(status_code=404, detail="Framework not found or access denied")
    return {"message": "Framework deleted"}


@router.post("/{framework_id}/domains")
async def add_domain(
    framework_id: str,
    domain: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    result = await svc.add_domain(framework_id, current_user.tenant_id or None, current_user.role or "", domain)
    if result is None:
        raise HTTPException(status_code=404, detail="Framework not found")
    return {"domain": result, "message": "Domain added"}


@router.post("/{framework_id}/domains/{domain_id}/controls")
async def add_control(
    framework_id: str,
    domain_id: str,
    control: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    result = await svc.add_control(framework_id, domain_id, current_user.tenant_id or None, current_user.role or "", control)
    if result is None:
        raise HTTPException(status_code=404, detail="Framework or domain not found")
    return {"control": result, "message": "Control added"}


@router.post("/{framework_id}/evaluate")
async def evaluate_framework(
    framework_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    result = await svc.evaluate_framework_compliance(framework_id, current_user.tenant_id or None, current_user.role or "")
    if not result:
        raise HTTPException(status_code=404, detail="Framework not found")
    return result


@router.post("/{framework_id}/publish")
async def publish_framework(
    framework_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    success = await svc.update_framework(framework_id, current_user.tenant_id or None, current_user.role or "", {"status": "published"})
    if not success:
        raise HTTPException(status_code=404, detail="Framework not found")
    return {"message": "Framework published successfully"}
