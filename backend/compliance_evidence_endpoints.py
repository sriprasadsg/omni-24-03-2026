from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends, Request, Response
from fastapi.responses import FileResponse
import asyncio
import logging
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from rbac_utils import require_permission
from rate_limiter import limiter
from compliance_artifacts_endpoints import UPLOAD_DIR, _write_binary, _ALLOWED_UPLOAD_EXTENSIONS, _ALLOWED_UPLOAD_MIME_PREFIXES, _check_magic, _SUPER_ROLES
from evidence_coc import _append_coc_entry
from evidence_staleness import get_staleness_threshold, compute_stale

logger = logging.getLogger(__name__)

router = APIRouter()


# Narrowed allowlists for manual evidence uploads (EVID-01 / EVID-05)
_EVIDENCE_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"
})
# WR-05: application/msword and application/vnd.ms-excel (legacy .doc/.xls MIME
# types) removed — .doc/.xls are not in _EVIDENCE_ALLOWED_EXTENSIONS above, so
# those prefixes were unreachable and misleading to future maintainers.
_EVIDENCE_ALLOWED_MIME_PREFIXES: tuple[str, ...] = (
    "application/pdf",
    "application/vnd.openxmlformats",
    "image/png",
    "image/jpeg",
)


@router.post("/api/assets/{asset_id}/compliance/evidence")
@limiter.limit("30/hour")
async def upload_compliance_evidence(
    request: Request,
    response: Response,
    asset_id: str,
    file: UploadFile = File(...),
    control_id: str = Form(...),
    description: str = Form("", max_length=1000),
    current_user=Depends(require_permission("manage:compliance_evidence")),
):
    try:
        # Derive caller identity from JWT
        user_role = getattr(current_user, "role", "")
        uploader = getattr(current_user, "username", "unknown")
        tenant_id = getattr(current_user, "tenant_id", None) or ""

        # Verify the asset belongs to the caller's tenant (non-admins only)
        if user_role not in _SUPER_ROLES:
            db = get_database()
            asset = await db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
            if not asset:
                raise HTTPException(status_code=403, detail="Asset not found in your tenant")

        # Narrowed extension allowlist for manual evidence (EVID-01)
        file_ext = os.path.splitext(file.filename or "")[1].lower()
        if not file_ext or file_ext not in _EVIDENCE_ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type '{file_ext}' is not allowed.")

        # Narrowed MIME allowlist for manual evidence (EVID-01)
        content_type = (file.content_type or "").split(";")[0].strip()
        if not content_type or not any(content_type.startswith(p) for p in _EVIDENCE_ALLOWED_MIME_PREFIXES):
            raise HTTPException(status_code=400, detail=f"MIME type '{content_type}' is not allowed.")

        # Read file content exactly once (RESEARCH Pitfall 6)
        file_content = await file.read()

        # Enforce 25 MB size cap (EVID-01)
        if len(file_content) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")

        # Magic-byte MIME validation using stdlib only (EVID-05)
        if not _check_magic(file_content, file_ext):
            raise HTTPException(status_code=400, detail="File content does not match extension")

        safe_filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)
        await asyncio.to_thread(_write_binary, file_path, file_content)

        file_url = f"/static/evidence/{safe_filename}"
        timestamp = datetime.now(timezone.utc).isoformat()

        evidence_record = {
            "id": f"ev-manual-{uuid.uuid4().hex}",
            "name": os.path.basename(file.filename or "evidence"),
            "url": file_url,
            "type": file.content_type,
            "uploadedAt": timestamp,
            "assetId": asset_id,
            "controlId": control_id,
            "tenantId": tenant_id,
            "uploaded_by": uploader,
            "description": description,
            "source": "manual",
            "systemGenerated": False,
        }

        db = get_database()
        await db.asset_compliance.update_one(
            {"assetId": asset_id, "controlId": control_id},
            {
                "$set": {
                    "status": "Pending_Review",
                    "lastUpdated": timestamp,
                    "tenantId": tenant_id,
                },
                "$push": {"evidence": evidence_record},
            },
            upsert=True,
        )
        await _append_coc_entry(
            db=db,
            evidence_id=evidence_record["id"],
            tenant_id=tenant_id,
            actor=uploader,
            action_type="create",
            snapshot_before=None,
            snapshot_after=evidence_record,
        )

        return {"success": True, "evidence": evidence_record}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/compliance/evidence")
async def get_all_compliance_evidence(current_user=Depends(get_current_user)):
    """Fetch AssetCompliance records. Super Admins see all; others see only their tenant's assets."""
    db = get_database()
    user_role = getattr(current_user, "role", "")
    is_super_admin = user_role in _SUPER_ROLES

    if is_super_admin:
        query: dict = {}
    else:
        tenant_id = getattr(current_user, "tenant_id", None)
        if not tenant_id:
            return []
        tenant_asset_ids = await db.assets.distinct("id", {"tenantId": tenant_id})
        if not tenant_asset_ids:
            return []
        query = {"assetId": {"$in": tenant_asset_ids}}

    cursor = db.asset_compliance.find(query)
    records = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        records.append(doc)
    return records


@router.get("/api/compliance/evidence/download/{evidence_id}")
async def download_compliance_evidence(
    evidence_id: str,
    current_user=Depends(get_current_user),
):
    """Download a specific piece of evidence (file or system-generated markdown)."""
    db = get_database()

    match_filter: dict = {"evidence.id": evidence_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in _SUPER_ROLES:
        _tid = getattr(current_user, "tenant_id", None) or None
        if not _tid:
            raise HTTPException(status_code=403, detail="Tenant context required")
        match_filter["tenantId"] = _tid

    pipeline = [
        {"$unwind": "$evidence"},
        {"$match": match_filter},
        {"$project": {"evidence": 1, "_id": 0}},
    ]
    result = await db.asset_compliance.aggregate(pipeline).to_list(length=1)

    if not result:
        raise HTTPException(status_code=404, detail="Evidence not found")

    evidence = result[0]["evidence"]

    if evidence.get("systemGenerated") or evidence.get("url") == "#":
        content = evidence.get("content") or evidence.get("details") or "No details available."
        import re as _re
        safe_name = _re.sub(r'[^A-Za-z0-9._-]', '_', evidence.get('name', 'evidence'))
        filename = f"{safe_name}.md"
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    file_url = evidence.get("url", "")
    possible_filename = Path(file_url).name  # strip path components
    if not possible_filename or possible_filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid evidence file reference")

    # Resolve and confine to upload directory — prevent path traversal
    _safe_dir = Path(UPLOAD_DIR).resolve()
    file_path_resolved = (_safe_dir / possible_filename).resolve()
    if not str(file_path_resolved).startswith(str(_safe_dir) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid file path")
    file_path = str(file_path_resolved)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Evidence file not found on server")

    filename = os.path.basename(file_path)
    return FileResponse(
        file_path,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/assets/{asset_id}/compliance")
async def get_asset_compliance(
    asset_id: str,
    current_user=Depends(get_current_user),
):
    """Get compliance evidence for a specific asset."""
    db = get_database()

    # Non-admins must own the asset before seeing its compliance records
    user_role = getattr(current_user, "role", "")
    if user_role not in _SUPER_ROLES:
        tenant_id = getattr(current_user, "tenant_id", None) or ""
        asset = await db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
        if not asset:
            raise HTTPException(status_code=403, detail="Asset not found in your tenant")

    cursor = db.asset_compliance.find(
        {"$or": [
            {"assetId": asset_id},
            {"asset_id": asset_id},
            {"assetId": f"asset-{asset_id}"},
        ]},
        {"_id": 0},
    )
    return await cursor.to_list(length=1000)


@router.delete("/api/assets/{asset_id}/compliance/evidence/{evidence_id}")
async def delete_compliance_evidence(
    asset_id: str,
    evidence_id: str,
    current_user=Depends(get_current_user),
):
    """Delete a manual evidence record with owner/admin RBAC and disk cleanup (EVID-04)."""
    try:
        db = get_database()
        user_role = getattr(current_user, "role", "")
        caller_tenant = getattr(current_user, "tenant_id", None)
        caller_username = getattr(current_user, "username", "")
        is_super = user_role in _SUPER_ROLES

        # Tenant isolation (T-02-04): non-super callers must have a tenant_id.
        # Checked before touching the DB so this 403 never correlates with
        # whether any specific evidence_id exists.
        if not is_super and not caller_tenant:
            raise HTTPException(status_code=403, detail="Tenant context required")

        # WR-02: scope the initial lookup by tenant for non-super callers so a
        # cross-tenant evidence ID collapses into the same 404 as "not found",
        # instead of leaking existence via a distinguishable 403-vs-404 response.
        match_filter: dict = {"assetId": asset_id, "evidence.id": evidence_id}
        if not is_super:
            match_filter["tenantId"] = caller_tenant

        pipeline = [
            {"$unwind": "$evidence"},
            {"$match": match_filter},
            {"$project": {"evidence": 1, "tenantId": 1, "_id": 0}},
        ]
        result = await db.asset_compliance.aggregate(pipeline).to_list(length=1)
        if not result:
            raise HTTPException(status_code=404, detail="Evidence not found")

        ev = result[0]["evidence"]
        doc_tenant = result[0].get("tenantId")

        # Never allow deletion of automated evidence (EVID-04 / T-02-05)
        if ev.get("systemGenerated"):
            raise HTTPException(status_code=403, detail="Automated evidence cannot be deleted")

        # Owner check: non-admins may only delete their own uploads (EVID-04 / T-02-03)
        if not is_super and ev.get("uploaded_by") != caller_username:
            raise HTTPException(status_code=403, detail="You can only delete your own evidence")

        # Pull the sub-document from the evidence array
        await db.asset_compliance.update_one(
            {"assetId": asset_id, "evidence.id": evidence_id},
            {"$pull": {"evidence": {"id": evidence_id}}},
        )
        await _append_coc_entry(
            db=db,
            evidence_id=evidence_id,
            tenant_id=doc_tenant or caller_tenant or "",
            actor=caller_username,
            action_type="delete",
            snapshot_before=ev,
            snapshot_after=None,
        )

        # Disk cleanup with path-traversal guard (T-02-06)
        file_url = ev.get("url", "")
        fname = Path(file_url).name
        if fname and not fname.startswith("."):
            _safe_dir = Path(UPLOAD_DIR).resolve()
            resolved = (_safe_dir / fname).resolve()
            if str(resolved).startswith(str(_safe_dir) + os.sep) or resolved == _safe_dir:
                resolved.unlink(missing_ok=True)

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete evidence error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/compliance/controls/{control_id}/evidence")
@limiter.limit("30/hour")
async def upload_control_direct_evidence(
    request: Request,
    control_id: str,
    file: UploadFile = File(...),
    description: str = Form("", max_length=1000),
    department: str = Form("", max_length=100),
    current_user=Depends(require_permission("manage:compliance_evidence")),
):
    """Upload evidence directly to a compliance control (no asset required).
    Used for organisational controls owned by HR, Finance, Legal, Management, etc.
    Evidence is stored in the `control_evidence` collection and returned alongside
    system-collected evidence by GET /api/compliance/controls/{control_id}/evidence.
    """
    try:
        tenant_id = getattr(current_user, "tenant_id", None) or ""
        uploader = getattr(current_user, "username", "unknown")

        file_ext = os.path.splitext(file.filename or "")[1].lower()
        if not file_ext or file_ext not in _EVIDENCE_ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type '{file_ext}' not allowed.")

        content_type = (file.content_type or "").split(";")[0].strip()
        if not content_type or not any(content_type.startswith(p) for p in _EVIDENCE_ALLOWED_MIME_PREFIXES):
            raise HTTPException(status_code=400, detail=f"MIME type '{content_type}' not allowed.")

        file_content = await file.read()
        if len(file_content) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")
        if not _check_magic(file_content, file_ext):
            raise HTTPException(status_code=400, detail="File content does not match extension")

        safe_filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)
        await asyncio.to_thread(_write_binary, file_path, file_content)

        # AI validation — runs after saving so upload always succeeds regardless of verdict
        from compliance_doc_validator import validate_document
        validation = await validate_document(
            file_content=file_content,
            file_ext=file_ext,
            filename=file.filename or "",
            description=description,
            control_id=control_id,
            department=department or "General",
        )

        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "id": f"cev-{uuid.uuid4().hex}",
            "name": os.path.basename(file.filename or "evidence"),
            "url": f"/static/evidence/{safe_filename}",
            "type": file.content_type,
            "uploadedAt": timestamp,
            "controlId": control_id,
            "tenantId": tenant_id,
            "uploaded_by": uploader,
            "department": department or "General",
            "description": description,
            "source": "manual",
            "systemGenerated": False,
            "ai_validation": validation,
        }

        db = get_database()
        await db.control_evidence.insert_one({**record})
        await _append_coc_entry(
            db=db,
            evidence_id=record["id"],
            tenant_id=tenant_id,
            actor=uploader,
            action_type="create",
            snapshot_before=None,
            snapshot_after=record,
        )
        record.pop("_id", None)
        return {"success": True, "evidence": record, "validation": validation}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Control evidence upload error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/compliance/controls/{control_id}/evidence")
async def get_control_evidence(
    control_id: str,
    current_user=Depends(get_current_user),
):
    """Return all evidence for a control: manually uploaded (control_evidence collection)
    plus system-collected records from agent heartbeats (asset_compliance collection)."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    user_role = getattr(current_user, "role", "")
    is_super = user_role in _SUPER_ROLES

    manual_query: dict = {"controlId": control_id}
    asset_query: dict = {"controlId": control_id}
    # CR-03: fail closed like every sibling endpoint in this module — a missing
    # tenant_id for a non-super caller must not silently drop the tenant filter
    # and leak cross-tenant evidence.
    if not is_super:
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        manual_query["tenantId"] = tenant_id
        asset_query["tenantId"] = tenant_id

    manual_docs = await db.control_evidence.find(manual_query, {"_id": 0}).to_list(length=500)

    # Also pull system-generated evidence from asset_compliance
    pipeline = [
        {"$match": asset_query},
        {"$unwind": "$evidence"},
        {"$project": {"evidence": 1, "_id": 0}},
        {"$limit": 200},
    ]
    system_docs = []
    async for doc in db.asset_compliance.aggregate(pipeline):
        ev = doc.get("evidence", {})
        ev.pop("_id", None)
        system_docs.append(ev)

    # Staleness injection (STALE-01) — fetch threshold once, inject per record
    threshold = await get_staleness_threshold(db, tenant_id)
    for ev in system_docs:
        is_auto = bool(ev.get("systemGenerated") or ev.get("source") == "auto")
        if is_auto:
            r = compute_stale(ev.get("uploadedAt") or ev.get("uploaded_at", ""), threshold)
            ev["stale"] = r["stale"]
            ev["stale_days"] = r["stale_days"]
        else:
            ev["stale"] = False
            ev["stale_days"] = 0
    for ev in manual_docs:
        ev["stale"] = False
        ev["stale_days"] = 0

    return {"control_id": control_id, "manual": manual_docs, "system": system_docs}


@router.delete("/api/compliance/controls/{control_id}/evidence/{evidence_id}")
async def delete_control_direct_evidence(
    control_id: str,
    evidence_id: str,
    current_user=Depends(get_current_user),
):
    """Delete a manually uploaded control-level evidence record."""
    try:
        db = get_database()
        user_role = getattr(current_user, "role", "")
        is_super = user_role in _SUPER_ROLES
        caller_tenant = getattr(current_user, "tenant_id", None)
        caller_username = getattr(current_user, "username", "")

        record = await db.control_evidence.find_one({"id": evidence_id, "controlId": control_id})
        if not record:
            raise HTTPException(status_code=404, detail="Evidence not found")
        if not is_super:
            if record.get("tenantId") != caller_tenant:
                raise HTTPException(status_code=403, detail="Evidence not found in your tenant")
            if record.get("uploaded_by") != caller_username:
                raise HTTPException(status_code=403, detail="You can only delete your own evidence")

        await db.control_evidence.delete_one({"id": evidence_id})
        await _append_coc_entry(
            db=db, evidence_id=evidence_id,
            tenant_id=record.get("tenantId", ""), actor=caller_username,
            action_type="delete", snapshot_before=record, snapshot_after=None,
        )
        fname = Path(record.get("url", "")).name
        if fname and not fname.startswith("."):
            _safe_dir = Path(UPLOAD_DIR).resolve()
            resolved = (_safe_dir / fname).resolve()
            if str(resolved).startswith(str(_safe_dir) + os.sep) or resolved == _safe_dir:
                resolved.unlink(missing_ok=True)

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete control evidence error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
