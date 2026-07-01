from fastapi import APIRouter, HTTPException, Depends
from risk_service import risk_service
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/risks", tags=["Risk Management"])

class RiskCreate(BaseModel):
    title: str
    description: str
    category: str
    status: str
    likelihood: int
    impact: int
    owner: str
    mitigation_plan: str = None
    ai_system_id: str = None
    vendor_id: str = None

class RiskUpdate(BaseModel):
    title: str = None
    description: str = None
    category: str = None
    status: str = None
    likelihood: int = None
    impact: int = None
    owner: str = None
    mitigation_plan: str = None

def _risk_tenant(current_user: TokenData) -> str:
    tid = getattr(current_user, "tenant_id", None) or None
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


@router.get("")
async def get_risks(current_user: TokenData = Depends(get_current_user)):
    role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or None
    return await risk_service.get_all_risks(tenant_id=tenant_id, role=role)

@router.post("")
async def create_risk(
    risk: RiskCreate,
    current_user: TokenData = Depends(get_current_user),
):
    return await risk_service.create_risk(risk.dict(exclude_unset=True), tenant_id=_risk_tenant(current_user))

@router.put("/{risk_id}")
async def update_risk(
    risk_id: str,
    risk: RiskUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or None
    updated_risk = await risk_service.update_risk(risk_id, risk.dict(exclude_unset=True), tenant_id=tenant_id, role=role)
    if not updated_risk:
        raise HTTPException(status_code=404, detail="Risk not found")
    return updated_risk

@router.delete("/{risk_id}")
async def delete_risk(
    risk_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or None
    success = await risk_service.delete_risk(risk_id, tenant_id=tenant_id, role=role)
    if not success:
        raise HTTPException(status_code=404, detail="Risk not found")
    return {"message": "Risk deleted successfully"}
