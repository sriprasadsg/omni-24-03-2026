from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from trust_service import trust_service, TrustProfile, AccessRequest
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData

_TRUST_ADMIN_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin", "Tenant Admin"}

router = APIRouter(prefix="/api/trust-center", tags=["Trust Center"])

class RequestCreate(BaseModel):
    requester_email: str
    company: str
    reason: str

class RequestUpdate(BaseModel):
    status: str
    approved_by: Optional[str] = None

@router.get("/profile", response_model=TrustProfile)
def get_profile(current_user: TokenData = Depends(get_current_user)):
    return trust_service.get_profile()

@router.put("/profile", response_model=TrustProfile)
def update_profile(updates: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    if getattr(current_user, "role", "") not in _TRUST_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return trust_service.update_profile(updates)

@router.get("/requests", response_model=List[AccessRequest])
def get_requests(current_user: TokenData = Depends(get_current_user)):
    if getattr(current_user, "role", "") not in _TRUST_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return trust_service.get_requests()

@router.post("/requests", response_model=AccessRequest)
def create_request(request: RequestCreate, current_user: TokenData = Depends(get_current_user)):
    return trust_service.create_request(request.dict())

@router.put("/requests/{request_id}", response_model=AccessRequest)
def update_request(request_id: str, update: RequestUpdate, current_user: TokenData = Depends(get_current_user)):
    if getattr(current_user, "role", "") not in _TRUST_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    result = trust_service.update_request_status(request_id, update.status, update.approved_by)
    if not result:
        raise HTTPException(status_code=404, detail="Request not found")
    return result
