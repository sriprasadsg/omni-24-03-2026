"""Audit Program Lifecycle endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData
from audit_program_service import audit_program_service

router = APIRouter(prefix="/api/audit-programs", tags=["Audit Programs"])


def _tenant(user: TokenData) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


def _role(user: TokenData) -> str:
    return getattr(user, "role", "")


class ProgramCreate(BaseModel):
    name: str
    description: Optional[str] = None
    framework: Optional[str] = None
    type: Optional[str] = "Internal"
    auditor: Optional[str] = None
    auditee: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    scope: Optional[List[str]] = None
    controls: Optional[List[str]] = None


class ProgramUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    framework: Optional[str] = None
    type: Optional[str] = None
    auditor: Optional[str] = None
    auditee: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    scope: Optional[List[str]] = None
    controls: Optional[List[str]] = None


class StatusTransition(BaseModel):
    status: str


class FindingCreate(BaseModel):
    title: str
    description: Optional[str] = None
    severity: Optional[str] = "Medium"
    controlId: Optional[str] = None
    recommendation: Optional[str] = None


class FindingUpdate(BaseModel):
    status: Optional[str] = None
    managementResponse: Optional[str] = None
    recommendation: Optional[str] = None
    severity: Optional[str] = None


@router.get("")
async def list_programs(current_user: TokenData = Depends(get_current_user)):
    return await audit_program_service.list_programs(_tenant(current_user), _role(current_user))


@router.post("")
async def create_program(payload: ProgramCreate, current_user: TokenData = Depends(get_current_user)):
    created_by = getattr(current_user, "username", getattr(current_user, "email", "unknown"))
    return await audit_program_service.create_program(
        payload.model_dump(exclude_none=True), _tenant(current_user), created_by
    )


@router.get("/{program_id}")
async def get_program(program_id: str, current_user: TokenData = Depends(get_current_user)):
    p = await audit_program_service.get_program(program_id, _tenant(current_user), _role(current_user))
    if not p:
        raise HTTPException(status_code=404, detail="Audit program not found")
    return p


@router.put("/{program_id}")
async def update_program(program_id: str, payload: ProgramUpdate, current_user: TokenData = Depends(get_current_user)):
    p = await audit_program_service.update_program(
        program_id, payload.model_dump(exclude_none=True), _tenant(current_user), _role(current_user)
    )
    if not p:
        raise HTTPException(status_code=404, detail="Audit program not found")
    return p


@router.put("/{program_id}/status")
async def transition_status(program_id: str, payload: StatusTransition, current_user: TokenData = Depends(get_current_user)):
    try:
        p = await audit_program_service.transition_status(
            program_id, payload.status, _tenant(current_user), _role(current_user)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not p:
        raise HTTPException(status_code=404, detail="Audit program not found")
    return p


@router.post("/{program_id}/findings")
async def add_finding(program_id: str, payload: FindingCreate, current_user: TokenData = Depends(get_current_user)):
    p = await audit_program_service.add_finding(
        program_id, payload.model_dump(exclude_none=True), _tenant(current_user), _role(current_user)
    )
    if not p:
        raise HTTPException(status_code=404, detail="Audit program not found")
    return p


@router.put("/{program_id}/findings/{finding_id}")
async def update_finding(
    program_id: str,
    finding_id: str,
    payload: FindingUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    p = await audit_program_service.update_finding(
        program_id, finding_id, payload.model_dump(exclude_none=True), _tenant(current_user), _role(current_user)
    )
    if not p:
        raise HTTPException(status_code=404, detail="Audit program or finding not found")
    return p


@router.get("/{program_id}/report")
async def get_report(program_id: str, current_user: TokenData = Depends(get_current_user)):
    return await audit_program_service.get_report(program_id, _tenant(current_user), _role(current_user))


@router.delete("/{program_id}")
async def delete_program(program_id: str, current_user: TokenData = Depends(get_current_user)):
    deleted = await audit_program_service.delete_program(program_id, _tenant(current_user), _role(current_user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Audit program not found")
    return {"success": True}
