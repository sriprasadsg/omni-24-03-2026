from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from vendor_service import vendor_service, Vendor, VendorAssessment
from pydantic import BaseModel

router = APIRouter(prefix="/api/vendors", tags=["Vendor Management"])

class VendorCreate(BaseModel):
    name: str
    website: str
    criticality: str
    category: str
    contact_name: str
    contact_email: str
    contract_start: str
    contract_end: str
    status: str

class AssessmentCreate(BaseModel):
    assessment_date: str
    reviewer: str
    risk_score: int
    questionnaire_responses: Dict[str, Any]
    findings: List[str]

@router.get("", response_model=List[Vendor])
def get_vendors():
    return vendor_service.get_all_vendors()

@router.get("/{vendor_id}", response_model=Vendor)
def get_vendor(vendor_id: str):
    vendor = vendor_service.get_vendor(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor

@router.post("", response_model=Vendor)
def create_vendor(vendor: VendorCreate):
    return vendor_service.create_vendor(vendor.dict())

@router.post("/{vendor_id}/assessments")
def add_assessment(vendor_id: str, assessment: AssessmentCreate):
    result = vendor_service.add_assessment(vendor_id, assessment.dict())
    if not result:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return result

@router.delete("/{vendor_id}")
def delete_vendor(vendor_id: str):
    success = vendor_service.delete_vendor(vendor_id)
    if not success:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"message": "Vendor deleted successfully"}
