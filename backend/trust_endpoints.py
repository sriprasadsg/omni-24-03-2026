from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from trust_service import trust_service, TrustProfile, AccessRequest
from pydantic import BaseModel

router = APIRouter(prefix="/api/trust-center", tags=["Trust Center"])

class RequestCreate(BaseModel):
    requester_email: str
    company: str
    reason: str

class RequestUpdate(BaseModel):
    status: str
    approved_by: Optional[str] = None

@router.get("/profile", response_model=TrustProfile)
def get_profile():
    return trust_service.get_profile()

@router.put("/profile", response_model=TrustProfile)
def update_profile(updates: Dict[str, Any]):
    return trust_service.update_profile(updates)

@router.get("/requests", response_model=List[AccessRequest])
def get_requests():
    return trust_service.get_requests()

@router.post("/requests", response_model=AccessRequest)
def create_request(request: RequestCreate):
    return trust_service.create_request(request.dict())

@router.put("/requests/{request_id}", response_model=AccessRequest)
def update_request(request_id: str, update: RequestUpdate):
    result = trust_service.update_request_status(request_id, update.status, update.approved_by)
    if not result:
        raise HTTPException(status_code=404, detail="Request not found")
    return result
