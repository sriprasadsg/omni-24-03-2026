from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from file_share_service import file_share_service, SharedFile
from authentication_service import get_current_user
from pydantic import BaseModel, Field
from rate_limiter import limiter

router = APIRouter(prefix="/api/file-share", tags=["Secure File Sharing"])

class ShareCreate(BaseModel):
    file_name: str = Field(..., max_length=255)
    file_url: str = Field(..., max_length=2048)
    expires_at: Optional[str] = None
    password_protected: bool = False
    password: Optional[str] = Field(None, max_length=128)
    max_accesses: Optional[int] = None

class ShareAccess(BaseModel):
    password: Optional[str] = Field(None, max_length=128)

@router.get("/shares", response_model=List[SharedFile])
def get_shares(current_user=Depends(get_current_user)):
    user_email = getattr(current_user, "username", None) or getattr(current_user, "email", "")
    return file_share_service.get_my_shares(user_email)

@router.post("/shares", response_model=SharedFile)
def create_share(share: ShareCreate, current_user=Depends(get_current_user)):
    user_email = getattr(current_user, "username", None) or getattr(current_user, "email", "")
    data = share.dict()
    data["created_by"] = user_email
    return file_share_service.create_share(data)

@router.delete("/shares/{share_id}")
def revoke_share(share_id: str, current_user=Depends(get_current_user)):
    success = file_share_service.revoke_share(share_id)
    if not success:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"message": "Share revoked"}

@router.post("/access/{token}")
@limiter.limit("20/minute")
def access_share(request: Request, token: str, access: ShareAccess):
    """Public token-based access endpoint — no auth required, token IS the credential."""
    result = file_share_service.access_share(token, access.password)
    if "error" in result:
        if result.get("password_required"):
            raise HTTPException(status_code=403, detail="Password required")
        raise HTTPException(status_code=400, detail=result["error"])
    return result
