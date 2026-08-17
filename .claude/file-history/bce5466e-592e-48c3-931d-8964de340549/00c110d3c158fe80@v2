"""Statement of Applicability (SoA) endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Response
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData
from soa_service import soa_service

router = APIRouter(prefix="/api/soa", tags=["Statement of Applicability"])


def _tenant(user: TokenData) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


def _role(user: TokenData) -> str:
    return getattr(user, "role", "")


class EntryUpdate(BaseModel):
    included: Optional[bool] = None
    justification: Optional[str] = None
    implementationStatus: Optional[str] = None
    implementationDescription: Optional[str] = None
    owner: Optional[str] = None


class BulkUpdatePayload(BaseModel):
    updates: List[Dict[str, Any]]


@router.get("/{framework_id}")
async def get_soa(framework_id: str, current_user: TokenData = Depends(get_current_user)):
    return await soa_service.get_soa(framework_id, _tenant(current_user), _role(current_user))


@router.post("/{framework_id}/generate")
async def generate_soa(framework_id: str, current_user: TokenData = Depends(get_current_user)):
    created = await soa_service.generate_soa(framework_id, _tenant(current_user))
    existing = await soa_service.get_soa(framework_id, _tenant(current_user), _role(current_user))
    return {"generated": len(created), "total": len(existing), "entries": existing}


@router.get("/{framework_id}/summary")
async def get_soa_summary(framework_id: str, current_user: TokenData = Depends(get_current_user)):
    return await soa_service.get_summary(framework_id, _tenant(current_user), _role(current_user))


@router.get("/{framework_id}/export")
async def export_soa_csv(framework_id: str, current_user: TokenData = Depends(get_current_user)):
    csv_data = await soa_service.export_csv(framework_id, _tenant(current_user), _role(current_user))
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=soa-{framework_id}.csv"},
    )


@router.put("/{framework_id}/bulk")
async def bulk_update_soa(
    framework_id: str,
    payload: BulkUpdatePayload,
    current_user: TokenData = Depends(get_current_user),
):
    updated = await soa_service.bulk_update(
        framework_id, payload.updates, _tenant(current_user), _role(current_user)
    )
    return {"updated": updated}


@router.put("/entry/{entry_id}")
async def update_soa_entry(
    entry_id: str,
    data: EntryUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    entry = await soa_service.update_entry(
        entry_id, data.model_dump(exclude_none=True), _tenant(current_user), _role(current_user)
    )
    if not entry:
        raise HTTPException(status_code=404, detail="SoA entry not found")
    return entry


@router.get("/entry/{entry_id}")
async def get_soa_entry(entry_id: str, current_user: TokenData = Depends(get_current_user)):
    entry = await soa_service.get_entry(entry_id, _tenant(current_user), _role(current_user))
    if not entry:
        raise HTTPException(status_code=404, detail="SoA entry not found")
    return entry
