from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends, Request, Response
from typing import Optional
import asyncio
import logging
import os
import hashlib
import uuid
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from rbac_utils import require_permission
from rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

# CR-02: stored outside backend/static/ so files are never reachable through the
# public, unauthenticated `/static` mount in app.py. All reads must go through the
# RBAC/tenant-scoped download endpoints in compliance_evidence_endpoints.py, which
# resolve files by basename and do not depend on this constant's value matching any
# URL prefix returned to clients.
UPLOAD_DIR = "private_uploads/evidence"
os.makedirs(UPLOAD_DIR, exist_ok=True)

_ALLOWED_UPLOAD_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".zip", ".tar", ".gz",
    # ".md", ".json", ".xml", ".html" removed — servable, script-capable formats (CR-01)
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

# Single source of truth for elevated-admin role variants (WR-02) — imported by
# compliance_evidence_endpoints.py rather than each module keeping its own list.
_SUPER_ROLES: frozenset[str] = frozenset({
    "Super Admin", "super_admin", "superadmin", "admin", "platform-admin"
})


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


_MAGIC_SIGNATURES: dict[str, bytes] = {
    ".pdf":  b"%PDF-",
    ".png":  b"\x89PNG\r\n\x1a\n",
    ".jpg":  b"\xFF\xD8\xFF",
    ".jpeg": b"\xFF\xD8\xFF",
    ".docx": b"PK\x03\x04",
    ".xlsx": b"PK\x03\x04",
}

# WR-03: genuinely-unsigned extensions (no magic bytes exist to check) that are
# nonetheless text-like enough to sanity-check as defense-in-depth, now that
# CR-01 guarantees `ext` here is always non-empty and allowlisted.
_TEXT_LIKE_UNSIGNED_EXTENSIONS: frozenset[str] = frozenset({".txt", ".csv"})
_SUSPICIOUS_TEXT_PREFIXES: tuple[bytes, ...] = (b"<script", b"<html", b"<!doctype", b"<?php")


def _check_magic(content: bytes, ext: str) -> bool:
    """Return True if file content leading bytes match the expected magic for ext.

    Returns True for extensions with no defined signature (pass-through), except
    an empty ext (rejected outright — WR-03) and text-like unsigned extensions,
    which get a lightweight NUL-byte / markup-prefix sanity check since they'd
    otherwise have no content validation at all.
    """
    if not ext:
        return False
    sig = _MAGIC_SIGNATURES.get(ext)
    if sig is not None:
        return content[:len(sig)] == sig
    if ext in _TEXT_LIKE_UNSIGNED_EXTENSIONS:
        head = content[:4096]
        if b"\x00" in head:
            return False
        stripped = head[:256].lstrip().lower()
        if any(stripped.startswith(p) for p in _SUSPICIOUS_TEXT_PREFIXES):
            return False
    return True


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
    current_user=Depends(require_permission("manage:compliance_evidence")),
):
    """
    Upload a manual compliance evidence artifact (pentest report, DPA, vendor SOC2 report,
    restore test result, etc.).  Returns the record with SHA-256 integrity hash.
    """
    try:
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

        # Whitelist extension and MIME type — reject executables and scripts.
        # Fails closed on an empty/omitted extension (CR-01), matching the sibling
        # pattern in compliance_evidence_endpoints.py's upload handlers.
        if not file_ext or file_ext not in _ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type '{file_ext or '(none)'}' is not allowed.")
        content_type = (file.content_type or "").split(";")[0].strip()
        if not content_type or not any(content_type.startswith(p) for p in _ALLOWED_UPLOAD_MIME_PREFIXES):
            raise HTTPException(status_code=400, detail=f"MIME type '{content_type}' is not allowed.")

        # Magic-byte validation (CR-03) — catches content/extension mismatches (e.g. an
        # HTML/script payload saved with a spoofed extension and forged Content-Type).
        if not _check_magic(file_content, file_ext):
            raise HTTPException(status_code=400, detail="File content does not match extension")

        # Validate asset_id belongs to caller's tenant. Fails closed (CR-04) when a
        # non-super caller has no tenant_id, instead of skipping the check outright.
        if asset_id:
            _caller_tenant = getattr(current_user, "tenant_id", None)
            _user_role = getattr(current_user, "role", "")
            if _user_role not in _SUPER_ROLES:
                if not _caller_tenant:
                    raise HTTPException(status_code=403, detail="Tenant context required")
                _db = get_database()
                _asset = await _db.assets.find_one({"id": asset_id, "tenantId": _caller_tenant})
                if not _asset:
                    raise HTTPException(status_code=403, detail="Asset not found in your tenant")
        uploader = getattr(current_user, "username", getattr(current_user, "email", "unknown"))
        # Unique per-upload filename (CR-04) — a second-granularity timestamp with no
        # random component let two same-second uploads silently overwrite each other.
        safe_filename = f"artifact_{category}_{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        await asyncio.to_thread(_write_binary, file_path, file_content)

        sha256 = _sha256_file(file_path)
        control_list = [c.strip() for c in control_ids.split(",") if c.strip()]

        record = {
            "id": f"artifact-{uuid.uuid4().hex}",
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
            "tenantId": getattr(current_user, "tenant_id", None),
            "status": "pending_review",
        }

        db = get_database()
        await db.compliance_artifacts.insert_one({**record, "_id": record["id"]})

        for control_id in control_list:
            if asset_id:
                # Asset-scoped control: unambiguous (assetId, controlId) filter (CR-05).
                await db.asset_compliance.update_one(
                    {"assetId": asset_id, "controlId": control_id},
                    {
                        "$set": {"status": "Pending_Review", "lastUpdated": record["uploaded_at"]},
                        "$push": {"evidence": record},
                    },
                    upsert=True,
                )
            else:
                # Org-wide control (no specific asset) — route to the dedicated
                # control_evidence collection instead of an ambiguous {"controlId": ...}
                # filter against asset_compliance, which can match/mutate an unrelated
                # asset's record (CR-05).
                await db.control_evidence.insert_one({**record, "controlId": control_id})

        return {"success": True, "artifact": record}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Manual artifact upload error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


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
    is_super_admin = user_role in _SUPER_ROLES
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
