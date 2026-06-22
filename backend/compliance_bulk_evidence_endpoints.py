"""Bulk evidence upload — POST /api/compliance/evidence/bulk.

Validates all zip entries (extension, magic bytes, 25 MB cap, zip-slip guard)
before any file is written. Any single failure returns 422 with per-file errors
and zero commits (BULK-02 validate-all-before-commit).
"""
import zipfile
import io
import os
import uuid
import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends

from compliance_artifacts_endpoints import UPLOAD_DIR, _write_binary, _check_magic
from compliance_evidence_endpoints import _EVIDENCE_ALLOWED_EXTENSIONS
from evidence_coc import _append_coc_entry
from database import get_database
from authentication_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_BULK_FILES = 50
MAX_BULK_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_ENTRY_BYTES = 25 * 1024 * 1024  # 25 MB per file

_WRITE_ROLES: frozenset[str] = frozenset({
    "admin", "Admin", "Super Admin", "superadmin", "super_admin", "platform-admin"
})

_EXT_TO_MIME: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.post("/api/compliance/evidence/bulk")
async def bulk_upload_evidence(
    zip_file: UploadFile = File(...),
    manifest: str = Form(...),
    current_user=Depends(get_current_user),
):
    """POST /api/compliance/evidence/bulk

    Validates all zip entries against the manifest, then commits atomically.
    Any single validation failure causes 422 with per-file error report and
    zero files committed (BULK-02).
    """
    try:
        tenant_id = getattr(current_user, "tenant_id", None) or ""
        uploader = getattr(current_user, "username", "unknown")

        user_role = getattr(current_user, "role", "")
        if user_role not in _WRITE_ROLES:
            raise HTTPException(status_code=403, detail="Insufficient permissions to upload evidence")

        # --- Pass 0a: parse and validate manifest ---
        try:
            items: list[dict] = json.loads(manifest)
            if not isinstance(items, list) or not items:
                raise ValueError("manifest must be a non-empty JSON array")
            for item in items:
                if "filename" not in item or "control_id" not in item:
                    raise ValueError(
                        "each manifest entry must have 'filename' and 'control_id'"
                    )
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid manifest: {exc}")

        if len(items) > MAX_BULK_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"Manifest exceeds {MAX_BULK_FILES} entries",
            )

        # --- Pass 0b: read and validate zip container ---
        zip_content = await zip_file.read()
        if len(zip_content) > MAX_BULK_BYTES:
            raise HTTPException(status_code=413, detail="Zip file exceeds 200 MB limit")
        if not zipfile.is_zipfile(io.BytesIO(zip_content)):
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid zip")

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
            total_uncompressed = sum(i.file_size for i in zf.infolist())
            if total_uncompressed > MAX_BULK_BYTES:
                raise HTTPException(
                    status_code=413, detail="Uncompressed content exceeds 200 MB limit"
                )

            # --- Pass 1: validate all entries (no writes yet) ---
            errors: list[dict] = []
            validated: list[dict] = []

            for item in items:
                raw_name: str = item["filename"]
                control_id: str = item["control_id"]

                # Zip-slip guard: derive safe display name from zip entry name
                safe_name = os.path.basename(raw_name.replace("\\", "/"))
                if not safe_name or safe_name in (".", ".."):
                    errors.append({"filename": raw_name, "error": "Unsafe filename"})
                    continue

                ext = os.path.splitext(safe_name)[1].lower()
                if ext not in _EVIDENCE_ALLOWED_EXTENSIONS:
                    errors.append(
                        {"filename": raw_name, "error": f"Extension '{ext}' not allowed"}
                    )
                    continue

                # Read entry bytes using raw_name (as listed in zip) — bounded read
                # to prevent zip-bomb decompression attacks (CR-02).
                try:
                    buf = io.BytesIO()
                    with zf.open(raw_name) as entry_fh:
                        read = 0
                        while True:
                            chunk = entry_fh.read(65536)
                            if not chunk:
                                break
                            read += len(chunk)
                            if read > MAX_ENTRY_BYTES:
                                errors.append({"filename": raw_name, "error": "File exceeds 25 MB limit"})
                                buf = None
                                break
                            buf.write(chunk)
                except KeyError:
                    errors.append(
                        {"filename": raw_name, "error": "File not found in zip"}
                    )
                    continue

                if buf is None:
                    continue
                entry_bytes = buf.getvalue()

                if not _check_magic(entry_bytes, ext):
                    errors.append(
                        {
                            "filename": raw_name,
                            "error": "File content does not match extension",
                        }
                    )
                    continue

                validated.append(
                    {
                        "original_name": safe_name,
                        "bytes": entry_bytes,
                        "ext": ext,
                        "control_id": control_id,
                    }
                )

            # Any validation failure → reject entire batch with per-file report
            if errors:
                raise HTTPException(
                    status_code=422, detail={"errors": errors}
                )

            # --- Pass 2: commit all (only reached when errors == []) ---
            batch_id = uuid.uuid4().hex
            timestamp = datetime.now(timezone.utc).isoformat()
            db = get_database()
            committed: list[dict] = []
            written_paths: list[str] = []

            try:
                for v in validated:
                    stored_name = f"{uuid.uuid4().hex}{v['ext']}"
                    file_path = os.path.join(UPLOAD_DIR, stored_name)
                    await asyncio.to_thread(_write_binary, file_path, v["bytes"])
                    written_paths.append(file_path)

                    record: dict = {
                        "id": f"cev-bulk-{uuid.uuid4().hex}",
                        "name": v["original_name"],
                        "url": f"/static/evidence/{stored_name}",
                        "type": _EXT_TO_MIME.get(v["ext"], "application/octet-stream"),
                        "uploadedAt": timestamp,
                        "controlId": v["control_id"],
                        "tenantId": tenant_id,
                        "uploaded_by": uploader,
                        "description": f"Bulk upload batch {batch_id}",
                        "source": "manual",
                        "systemGenerated": False,
                        "bulk_batch_id": batch_id,
                    }
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
                    committed.append(record)
            except Exception:
                for p in written_paths:
                    try:
                        await asyncio.to_thread(os.unlink, p)
                    except OSError:
                        pass
                raise HTTPException(status_code=500, detail="Internal server error")

        return {
            "success": True,
            "committed": len(committed),
            "batch_id": batch_id,
            "evidence": committed,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Bulk upload error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")
