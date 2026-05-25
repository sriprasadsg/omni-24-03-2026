from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from vendor_service import vendor_service, Vendor, VendorAssessment
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/vendors", tags=["Vendor Management"])

_VENDOR_ADMIN_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin", "Tenant Admin"}


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

@router.get("")
async def get_vendors(current_user: TokenData = Depends(get_current_user)):
    return await vendor_service.get_all_vendors()


@router.get("/{vendor_id}")
async def get_vendor(vendor_id: str, current_user: TokenData = Depends(get_current_user)):
    vendor = await vendor_service.get_vendor(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor

@router.post("")
async def create_vendor(vendor: VendorCreate, current_user: TokenData = Depends(get_current_user)):
    if getattr(current_user, "role", "") not in _VENDOR_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return await vendor_service.create_vendor(vendor.dict())

@router.post("/{vendor_id}/assessments")
async def add_assessment(
    vendor_id: str,
    assessment: AssessmentCreate,
    current_user: TokenData = Depends(get_current_user),
):
    if getattr(current_user, "role", "") not in _VENDOR_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    result = await vendor_service.add_assessment(vendor_id, assessment.dict())
    if not result:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return result

@router.get("/{vendor_id}/risk-score")
async def get_vendor_risk_score(vendor_id: str, current_user: TokenData = Depends(get_current_user)):
    score = await vendor_service.calculate_risk_score(vendor_id)
    return {"vendor_id": vendor_id, "risk_score": score}

@router.get("/dashboard/summary")
async def get_vendor_dashboard(current_user: TokenData = Depends(get_current_user)):
    return await vendor_service.get_portfolio_summary()

@router.post("/{vendor_id}/documents")
async def upload_vendor_document(
    vendor_id: str,
    doc_name: str,
    doc_type: str,
    current_user: TokenData = Depends(get_current_user),
):
    if getattr(current_user, "role", "") not in _VENDOR_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    success = await vendor_service.add_document(vendor_id, {"name": doc_name, "type": doc_type})
    if not success:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"message": "Document uploaded successfully"}

@router.get("/questionnaire/template")
def get_questionnaire_template(current_user: TokenData = Depends(get_current_user)):
    """Return the standard vendor security questionnaire template."""
    return {
        "version": "2.0",
        "sections": [
            {
                "id": "data_handling",
                "title": "Data Handling & Classification",
                "questions": [
                    {"id": "dh1", "text": "What categories of our data does this vendor process?", "type": "multiselect",
                     "options": ["PII", "PHI", "PCI", "Financial", "Confidential IP", "None"]},
                    {"id": "dh2", "text": "Is our data encrypted at rest?", "type": "yesno"},
                    {"id": "dh3", "text": "Is our data encrypted in transit?", "type": "yesno"},
                    {"id": "dh4", "text": "Where is our data stored geographically?", "type": "text"},
                ]
            },
            {
                "id": "access_control",
                "title": "Access Control & Identity",
                "questions": [
                    {"id": "ac1", "text": "Does the vendor enforce MFA for all admin accounts?", "type": "yesno"},
                    {"id": "ac2", "text": "Does the vendor use privileged access management (PAM)?", "type": "yesno"},
                    {"id": "ac3", "text": "How often are access rights reviewed?", "type": "select",
                     "options": ["Monthly", "Quarterly", "Annually", "Never"]},
                ]
            },
            {
                "id": "incident_response",
                "title": "Incident Response",
                "questions": [
                    {"id": "ir1", "text": "Does the vendor have a documented incident response plan?", "type": "yesno"},
                    {"id": "ir2", "text": "What is their breach notification SLA?", "type": "select",
                     "options": ["< 24 hours", "24-72 hours", "72 hours - 7 days", "> 7 days", "No SLA"]},
                    {"id": "ir3", "text": "Has the vendor experienced a breach in the last 24 months?", "type": "yesno"},
                ]
            },
            {
                "id": "compliance",
                "title": "Compliance & Certifications",
                "questions": [
                    {"id": "cp1", "text": "Which compliance certifications does the vendor hold?", "type": "multiselect",
                     "options": ["SOC2 Type II", "ISO 27001", "PCI-DSS", "HIPAA BAA", "GDPR DPA", "FedRAMP", "None"]},
                    {"id": "cp2", "text": "When was the last third-party security audit?", "type": "text"},
                    {"id": "cp3", "text": "Is the vendor willing to share their latest audit report?", "type": "yesno"},
                ]
            },
            {
                "id": "business_continuity",
                "title": "Business Continuity",
                "questions": [
                    {"id": "bc1", "text": "What is the vendor's documented RTO?", "type": "text"},
                    {"id": "bc2", "text": "What is the vendor's documented RPO?", "type": "text"},
                    {"id": "bc3", "text": "Does the vendor have a tested DR plan?", "type": "yesno"},
                ]
            },
        ]
    }


@router.post("/{vendor_id}/review")
async def schedule_review(
    vendor_id: str,
    review_date: str,
    reviewer: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Schedule a periodic vendor review."""
    if getattr(current_user, "role", "") not in _VENDOR_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    vendor = await vendor_service.get_vendor(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.get("name"),
        "review_scheduled": review_date,
        "reviewer": reviewer,
        "status": "scheduled",
    }


@router.delete("/{vendor_id}")
async def delete_vendor(vendor_id: str, current_user: TokenData = Depends(get_current_user)):
    if getattr(current_user, "role", "") not in _VENDOR_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    success = await vendor_service.delete_vendor(vendor_id)
    if not success:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"message": "Vendor deleted successfully"}
