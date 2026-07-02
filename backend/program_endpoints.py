"""Program Control Grouping API — CRUD + control management."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_database
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service
import program_service as svc
import logging

router = APIRouter(prefix="/api/programs", tags=["Programs"])
logger = logging.getLogger(__name__)


class ProgramCreate(BaseModel):
    name: str
    description: str = ""
    framework_id: str = ""
    owner: str = ""
    control_ids: list[str] = []


class ControlsUpdate(BaseModel):
    add: list[str] = []
    remove: list[str] = []


@router.post("")
async def create_program(payload: ProgramCreate, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    db = get_database()
    if not payload.name:
        raise HTTPException(status_code=400, detail="name required")
    doc = await svc.create_program(db, get_tenant_id(), payload.model_dump())
    return {"program": doc}


@router.get("")
async def list_programs(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    items = await svc.list_programs(db, get_tenant_id())
    return {"items": items, "count": len(items)}


@router.get("/{program_id}")
async def get_program(program_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    doc = await svc.get_program(db, program_id, get_tenant_id())
    if not doc:
        raise HTTPException(status_code=404, detail="Program not found")
    return {"program": doc}


@router.put("/{program_id}/controls")
async def update_program_controls(program_id: str, payload: ControlsUpdate, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    db = get_database()
    doc = await svc.update_controls(db, program_id, get_tenant_id(), payload.add, payload.remove)
    if not doc:
        raise HTTPException(status_code=404, detail="Program not found")
    return {"program": doc}


@router.delete("/{program_id}")
async def delete_program(program_id: str, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    db = get_database()
    ok = await svc.delete_program(db, program_id, get_tenant_id())
    if not ok:
        raise HTTPException(status_code=404, detail="Program not found")
    return {"success": True}
