from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends, Request, Response
from typing import Optional
import asyncio
import logging
import os
import hashlib
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = "static/evidence"
os.makedirs(UPLOAD_DIR, exist_ok=True)

_ALLOWED_UPLOAD_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".zip", ".tar", ".gz",
    ".md", ".json", ".xml", ".html",
})

_ALLOWED_UPLOAD_MIME_PREFIXES: tuple[str, ...] = (
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats",
    "application/vnd.ms-excel",
    "application/zip",
    "application/gzip",
    "application/x-tar",
    "application/json",
    "application/xml",
    "text/",
    "image/",
)


MANUAL_ARTIFACT_CATEGORIES = [
    "pentest_report",
    "vulnerability_assessment",
    "vendor_assessment",
    "dpa_agreement",
    "baa_agreement",
    "soc2_report",
    "iso27001_certificate",
    "restore_test_result",
    "risk_assessment",
    "security_awareness_training",
    "incident_report",
    "policy_document",
    "other",
]


def _write_binary(path: str, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@router.post("/api/compliance/artifacts/upload")
@limiter.limit("10/hour")
async def upload_manual_artifact(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    category: str = Form(..., description=f"One of: {', '.join(MANUAL_ARTIFACT_CATEGORIES)}"),
    control_ids: str = Form("", description="Comma-separated control IDs this artifact satisfies"),
    description: str = Form("", description="Brief description of what this artifact proves"),
    asset_id: Optional[str] = Form(None, description="Asset or tenant this artifact belongs to"),
    current_user=Depends(get_current_user),
):
    """
    Upload a manual compliance evidence artifact (pentest report, DPA, vendor SOC2 report,
    restore test result, etc.).  Returns the record with SHA-256 integrity hash.
    """
    if category not in MANUAL_ARTIFACT_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Valid: {MANUAL_ARTIFACT_CATEGORIES}"
        )

    file_content = await file.read()
    if len(file_content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    original_name = os.path.basename(file.filename or "artifact")
    file_ext = os.path.splitext(original_name)[1].lower()

    # Whitelist extension and MIME type — reject executables and scripts
    if file_ext and file_ext not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{file_ext}' is not allowed.")
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type and not any(content_type.startswith(p) for p in _ALLOWED_UPLOAD_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail=f"MIME type '{content_type}' is not allowed.")

    # Validate asset_id belongs to caller's tenant
    if asset_id:
        _caller_tenant = getattr(current_user, "tenant_id", None)
        if _caller_tenant:
            _db = get_database()
            _asset = await _db.assets.find_one({"id": asset_id, "tenantId": _caller_tenant})
            if not _asset:
                raise HTTPException(status_code=403, detail="Asset not found in your tenant")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    uploader = getattr(current_user, "username", getattr(current_user, "email", "unknown"))
    safe_filename = f"artifact_{category}_{timestamp}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    await asyncio.to_thread(_write_binary, file_path, file_content)

    sha256 = _sha256_file(file_path)
    control_list = [c.strip() for c in control_ids.split(",") if c.strip()]

    record = {
        "id": f"artifact-{timestamp}",
        "type": "manual_artifact",
        "category": category,
        "filename": original_name,
        "stored_as": safe_filename,
        "url": f"/static/evidence/{safe_filename}",
        "sha256": sha256,
        "size_bytes": len(file_content),
        "content_type": file.content_type,
        "description": description,
        "control_ids": control_list,
        "asset_id": asset_id,
        "uploaded_by": uploader,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_review",
    }

    db = get_database()
    await db.compliance_artifacts.insert_one({**record, "_id": record["id"]})

    for control_id in control_list:
        scope = {"assetId": asset_id, "controlId": control_id} if asset_id else {"controlId": control_id}
        await db.asset_compliance.update_one(
            scope,
            {
                "$set": {"status": "Pending_Review", "lastUpdated": record["uploaded_at"]},
                "$push": {"evidence": record},
            },
            upsert=True,
        )

    return {"success": True, "artifact": record}


@router.get("/api/compliance/artifacts")
async def list_manual_artifacts(
    category: Optional[str] = None,
    asset_id: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    """List all manually uploaded compliance artifacts, optionally filtered by category or asset."""
    db = get_database()
    query: dict = {"type": "manual_artifact"}
    if category:
        query["category"] = category

    user_role = getattr(current_user, "role", "")
    user_tenant = getattr(current_user, "tenant_id", None)
    is_super_admin = user_role in ("Super Admin", "superadmin", "super_admin")
    if not is_super_admin:
        query["tenantId"] = user_tenant
        if asset_id:
            query["asset_id"] = asset_id
    elif asset_id:
        query["asset_id"] = asset_id

    docs = await db.compliance_artifacts.find(query).sort("uploaded_at", -1).to_list(200)
    for d in docs:
        d.pop("_id", None)
    return {"artifacts": docs, "count": len(docs)}


@router.get("/api/compliance/artifacts/categories")
async def list_artifact_categories():
    """Return the list of valid manual artifact categories."""
    return {"categories": MANUAL_ARTIFACT_CATEGORIES}
