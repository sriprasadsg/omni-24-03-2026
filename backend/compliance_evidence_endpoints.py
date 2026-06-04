from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends
from fastapi.responses import FileResponse, Response
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from compliance_artifacts_endpoints import UPLOAD_DIR, _write_binary

logger = logging.getLogger(__name__)

router = APIRouter()


_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


@router.post("/api/assets/{asset_id}/compliance/evidence")
async def upload_compliance_evidence(
    asset_id: str,
    file: UploadFile = File(...),
    control_id: str = Form(...),
    current_user=Depends(get_current_user),
):
    try:
        # Verify the asset belongs to the caller's tenant (non-admins only)
        user_role = getattr(current_user, "role", "")
        if user_role not in _SUPER_ROLES:
            tenant_id = getattr(current_user, "tenant_id", None) or ""
            db = get_database()
            asset = await db.assets.find_one({"id": asset_id, "tenantId": tenant_id})
            if not asset:
                raise HTTPException(status_code=403, detail="Asset not found in your tenant")

        file_ext = os.path.splitext(file.filename or "")[1]
        safe_filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        file_content = await file.read()
        await asyncio.to_thread(_write_binary, file_path, file_content)

        file_url = f"/static/evidence/{safe_filename}"
        timestamp = datetime.now(timezone.utc).isoformat()

        evidence_record = {
            "id": f"ev-{timestamp}",
            "name": file.filename,
            "url": file_url,
            "type": file.content_type,
            "uploadedAt": timestamp,
            "assetId": asset_id,
            "controlId": control_id,
        }

        db = get_database()
        await db.asset_compliance.update_one(
            {"assetId": asset_id, "controlId": control_id},
            {
                "$set": {
                    "status": "Pending_Review",
                    "lastUpdated": timestamp,
                },
                "$push": {"evidence": evidence_record},
            },
            upsert=True,
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
    is_super_admin = user_role in {"Super Admin", "superadmin", "super_admin", "platform-admin"}

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
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
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
        filename = f"{evidence['name'].replace(' ', '_').replace(':', '')}.md"
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    file_url = evidence.get("url", "")
    possible_filename = os.path.basename(file_url)
    if not possible_filename or possible_filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid evidence file reference")

    file_path = os.path.join(UPLOAD_DIR, possible_filename)
    if not os.path.exists(file_path):
        raw_name = evidence.get("name") or ""
        safe_name = os.path.basename(raw_name)
        if not safe_name or safe_name.startswith("."):
            raise HTTPException(status_code=404, detail="Evidence file not found on server")
        fallback_path = os.path.join(UPLOAD_DIR, safe_name)
        if os.path.exists(fallback_path):
            file_path = fallback_path
        else:
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
