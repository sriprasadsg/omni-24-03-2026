from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from file_share_service import file_share_service, SharedFile
from pydantic import BaseModel

router = APIRouter(prefix="/api/file-share", tags=["Secure File Sharing"])

class ShareCreate(BaseModel):
    file_name: str
    file_url: str
    created_by: str
    expires_at: Optional[str] = None
    password_protected: bool = False
    password: Optional[str] = None
    max_accesses: Optional[int] = None

class ShareAccess(BaseModel):
    password: Optional[str] = None

@router.get("/shares", response_model=List[SharedFile])
def get_shares(user_email: str = "admin@omni-agent.com"):
    return file_share_service.get_my_shares(user_email)

@router.post("/shares", response_model=SharedFile)
def create_share(share: ShareCreate):
    return file_share_service.create_share(share.dict())

@router.delete("/shares/{share_id}")
def revoke_share(share_id: str):
    success = file_share_service.revoke_share(share_id)
    if not success:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"message": "Share revoked"}

@router.post("/access/{token}")
def access_share(token: str, access: ShareAccess):
    result = file_share_service.access_share(token, access.password)
    if "error" in result:
        if result.get("password_required"):
             raise HTTPException(status_code=403, detail="Password required")
        raise HTTPException(status_code=400, detail=result["error"])
    return result
