from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from risk_service import risk_service, Risk
from pydantic import BaseModel

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

@router.get("", response_model=List[Risk])
def get_risks():
    return risk_service.get_all_risks()

@router.post("", response_model=Risk)
def create_risk(risk: RiskCreate):
    return risk_service.create_risk(risk.dict(exclude_unset=True))

@router.put("/{risk_id}", response_model=Risk)
def update_risk(risk_id: str, risk: RiskUpdate):
    updated_risk = risk_service.update_risk(risk_id, risk.dict(exclude_unset=True))
    if not updated_risk:
        raise HTTPException(status_code=404, detail="Risk not found")
    return updated_risk

@router.delete("/{risk_id}")
def delete_risk(risk_id: str):
    success = risk_service.delete_risk(risk_id)
    if not success:
        raise HTTPException(status_code=404, detail="Risk not found")
    return {"message": "Risk deleted successfully"}
