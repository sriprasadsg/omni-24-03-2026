"""
Custom Compliance Framework Builder Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Any, Dict, List, Optional
import logging

from auth_utils import get_current_user
import custom_framework_service as svc

router = APIRouter(prefix="/api/custom-frameworks", tags=["Custom Frameworks"])
logger = logging.getLogger(__name__)


@router.get("/templates")
async def list_templates(current_user: dict = Depends(get_current_user)):
    return {"templates": [
        {"id": k, "name": v["name"], "description": v["description"]}
        for k, v in svc.BUILTIN_TEMPLATES.items()
    ]}


@router.get("")
async def list_frameworks(current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    frameworks = await svc.list_frameworks(tenant_id, role)
    return {"frameworks": frameworks, "total": len(frameworks)}


@router.post("")
async def create_framework(
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    if not payload.get("name"):
        raise HTTPException(status_code=400, detail="Framework name is required")

    tenant_id = current_user.get("tenant_id", "platform-admin")
    created_by = current_user.get("email", current_user.get("username", ""))
    framework = await svc.create_framework(tenant_id, created_by, payload)
    framework.pop("_id", None)
    return {"framework": framework, "message": "Framework created successfully"}


@router.get("/{framework_id}")
async def get_framework(framework_id: str, current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    fw = await svc.get_framework(framework_id, tenant_id, role)
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found")
    return {"framework": fw}


@router.put("/{framework_id}")
async def update_framework(
    framework_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    success = await svc.update_framework(framework_id, tenant_id, role, payload)
    if not success:
        raise HTTPException(status_code=404, detail="Framework not found or access denied")
    return {"message": "Framework updated successfully"}


@router.delete("/{framework_id}")
async def delete_framework(
    framework_id: str,
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    success = await svc.delete_framework(framework_id, tenant_id, role)
    if not success:
        raise HTTPException(status_code=404, detail="Framework not found or access denied")
    return {"message": "Framework deleted"}


@router.post("/{framework_id}/domains")
async def add_domain(
    framework_id: str,
    domain: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    result = await svc.add_domain(framework_id, tenant_id, role, domain)
    if result is None:
        raise HTTPException(status_code=404, detail="Framework not found")
    return {"domain": result, "message": "Domain added"}


@router.post("/{framework_id}/domains/{domain_id}/controls")
async def add_control(
    framework_id: str,
    domain_id: str,
    control: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    result = await svc.add_control(framework_id, domain_id, tenant_id, role, control)
    if result is None:
        raise HTTPException(status_code=404, detail="Framework or domain not found")
    return {"control": result, "message": "Control added"}


@router.post("/{framework_id}/evaluate")
async def evaluate_framework(
    framework_id: str,
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    result = await svc.evaluate_framework_compliance(framework_id, tenant_id, role)
    if not result:
        raise HTTPException(status_code=404, detail="Framework not found")
    return result


@router.post("/{framework_id}/publish")
async def publish_framework(
    framework_id: str,
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user.get("tenant_id", "")
    role = current_user.get("role", "")
    success = await svc.update_framework(framework_id, tenant_id, role, {"status": "published"})
    if not success:
        raise HTTPException(status_code=404, detail="Framework not found")
    return {"message": "Framework published successfully"}
