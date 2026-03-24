from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from typing import List, Dict, Any
from datetime import datetime, timezone
import os
import shutil
import base64
import hashlib

from database import get_database
from authentication_service import get_current_user

# ── Local Repository Configuration ──────────────────────────────────────────
REPO_DIR = os.path.join(os.getcwd(), "data", "local_repo")
os.makedirs(REPO_DIR, exist_ok=True)

router = APIRouter(prefix="/api/repo", tags=["Local Software Repository"])

@router.post("/upload")
async def upload_package(
    file: UploadFile = File(...),
    pkg_type: str = Query(..., description="'pip', 'npm', or 'apt'"),
    current_user: Any = Depends(get_current_user)
):
    """
    Upload a software package binary/archive to the local repository.
    Only allows administrators.
    """
    role = getattr(current_user, "role", None)
    if role not in ("Super Admin", "Tenant Admin"):
        raise HTTPException(status_code=403, detail="Unauthorised. Admins only.")

    tenant_id = getattr(current_user, "tenantId", "global")
    
    # Secure filename
    filename = os.path.basename(file.filename)
    if not filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Extract package name and version from filename if possible
    # A simple parsing heuristic; for a real production system this would use pkg-specific parsers
    name_parts = filename.replace(".whl", "").replace(".tar.gz", "").replace(".deb", "").replace(".tgz", "").split("-")
    pkg_name = name_parts[0] if name_parts else filename
    pkg_version = "-".join(name_parts[1:]) if len(name_parts) > 1 else "unknown"

    # Save the file
    file_path = os.path.join(REPO_DIR, f"{tenant_id}_{filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Calculate checksum
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    checksum = hasher.hexdigest()

    # Record in DB
    db = get_database()
    package_doc = {
        "tenantId": tenant_id,
        "filename": filename,
        "pkg_name": pkg_name,
        "pkg_version": pkg_version,
        "pkg_type": pkg_type,
        "checksum": checksum,
        "size_bytes": os.path.getsize(file_path),
        "uploaded_by": getattr(current_user, "username", "system"),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "file_path": file_path
    }
    
    await db.local_repo.update_one(
        {"tenantId": tenant_id, "filename": filename},
        {"$set": package_doc},
        upsert=True
    )

    return {"message": "Package uploaded successfully", "package": package_doc}


@router.get("/packages")
async def list_packages(current_user: Any = Depends(get_current_user)):
    """ List all available software packages in the tenant's local repository. """
    tenant_id = getattr(current_user, "tenantId", "global")
    db = get_database()
    
    # Admins see all, otherwise isolate by tenant
    query = {}
    if getattr(current_user, "role", None) != "Super Admin" and tenant_id != "global":
        query["tenantId"] = tenant_id

    packages = await db.local_repo.find(query, {"_id": 0}).sort("uploaded_at", -1).to_list(length=1000)
    return packages


@router.delete("/packages/{filename}")
async def delete_package(filename: str, current_user: Any = Depends(get_current_user)):
    """ Remove a package from the local repository. """
    role = getattr(current_user, "role", None)
    if role not in ("Super Admin", "Tenant Admin"):
        raise HTTPException(status_code=403, detail="Unauthorised. Admins only.")

    tenant_id = getattr(current_user, "tenantId", "global")
    db = get_database()
    
    pkg = await db.local_repo.find_one({"tenantId": tenant_id, "filename": filename})
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    # Delete physical file
    file_path = pkg.get("file_path")
    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    # Delete DB record
    await db.local_repo.delete_one({"tenantId": tenant_id, "filename": filename})
    
    return {"message": "Package deleted successfully"}


@router.get("/download/{filename}")
async def download_package(filename: str, tenantId: str = Query(...)):
    """ 
    Serve the package file to agents. 
    Requires tenantId query param matching the file's tenant.
    """
    db = get_database()
    pkg = await db.local_repo.find_one({"tenantId": tenantId, "filename": filename})
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
        
    file_path = pkg.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File missing on disk")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )
