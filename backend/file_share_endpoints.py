from fastapi import APIRouter, HTTPException, Depends, Request, Response, UploadFile, File, Form
from fastapi.responses import FileResponse
from typing import Optional
import file_share_service
from authentication_service import get_current_user
from database import get_database
from pydantic import BaseModel, Field
from rate_limiter import limiter
from tickets_endpoints import _validate_attachment

router = APIRouter(prefix="/api/file-share", tags=["Secure File Sharing"])


class ShareAccess(BaseModel):
    password: Optional[str] = Field(None, max_length=128)


def _email(current_user) -> str:
    return getattr(current_user, "username", None) or getattr(current_user, "email", "")


@router.get("/shares")
async def get_shares(current_user=Depends(get_current_user)):
    return await file_share_service.list_shares(get_database(), _email(current_user))


@router.post("/shares")
async def create_share(
    file: UploadFile = File(...),
    expires_in_days: int = Form(7, ge=1, le=90),
    password: Optional[str] = Form(None, max_length=128),
    max_accesses: Optional[int] = Form(None, ge=1, le=10000),
    current_user=Depends(get_current_user),
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The file is empty")
    if len(contents) > file_share_service.MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit")
    mimetype = _validate_attachment(file.filename or "file", contents, file.content_type)
    return await file_share_service.create_share(
        get_database(),
        file_name=file.filename or "file",
        contents=contents,
        mimetype=mimetype,
        created_by=_email(current_user),
        tenant_id=getattr(current_user, "tenant_id", None),
        expires_in_days=expires_in_days,
        password=password or None,
        max_accesses=max_accesses,
    )


@router.delete("/shares/{share_id}")
async def revoke_share(share_id: str, current_user=Depends(get_current_user)):
    if not await file_share_service.revoke_share(get_database(), share_id, _email(current_user)):
        raise HTTPException(status_code=404, detail="Share not found")
    return {"message": "Share revoked"}


@router.post("/access/{token}")
@limiter.limit("20/minute")
async def access_share(request: Request, response: Response, token: str, access: ShareAccess):
    """Public token-based download — no auth required, the token IS the credential."""
    result = await file_share_service.open_share(get_database()._db, token, access.password)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])
    share = result["share"]
    try:
        path = file_share_service.stored_path(share["stored_name"])
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    # Content-Disposition: attachment, so the browser saves rather than renders it
    return FileResponse(path, filename=share["file_name"], media_type=share.get("mimetype") or "application/octet-stream")
