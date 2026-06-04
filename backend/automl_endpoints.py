from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request, Response
import logging
from typing import Dict, Any, List, Optional
from automl_service import automl_service
from rbac_utils import require_permission
from rate_limiter import limiter
import uuid
from datetime import datetime, timezone
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/automl", tags=["AutoML & Hyperparameter Optimization"])

_AUTOML_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

@router.get("/studies")
async def list_studies(
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    List all optimization studies scoped to the caller's tenant.
    """
    role = getattr(current_user, "role", "")
    tenant_id = None if role in _AUTOML_SUPER_ROLES else getattr(current_user, "tenant_id", None)
    return await automl_service.get_all_studies(tenant_id=tenant_id)

@router.post("/study")
@limiter.limit("10/minute")
async def create_study(
    http_request: Request,
    response: Response,
    request: Dict[str, str],
    current_user: dict = Depends(require_permission("manage:ai_models"))
):
    """
    Create a new study.
    Body: {"name": "Optimize CNN"}
    """
    name = request.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
        
    study_id = await automl_service.create_study(name)
    return {"study_id": study_id, "message": "Study created"}

@router.get("/study/{study_id}")
async def get_study_details(
    study_id: str,
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    Get full details of a study including all trials.
    """
    study = await automl_service.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study

@router.post("/study/{study_id}/run")
@limiter.limit("5/minute")
async def run_trials(
    http_request: Request,
    response: Response,
    study_id: str,
    request: Dict[str, int],
    current_user: dict = Depends(require_permission("manage:ai_models"))
):
    """
    Trigger trials for a study.
    Body: {"n_trials": 10}
    """
    n_trials = request.get("n_trials", 5)
    try:
        count = await automl_service.run_trials(study_id, n_trials)
        return {"message": f"Completed {n_trials} trials", "total_trials": count}
    except ValueError:
        raise HTTPException(status_code=404, detail="Study not found")


# ── Training Datasets ─────────────────────────────────────────────────────────

@router.get("/training-datasets")
async def list_training_datasets(
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """List all registered training datasets."""
    db = get_database()
    role = getattr(current_user, "role", "") or (current_user.get("role", "") if isinstance(current_user, dict) else "")
    tenant_id = getattr(current_user, "tenant_id", None) or (current_user.get("tenant_id") if isinstance(current_user, dict) else None)
    query = {} if role in _AUTOML_SUPER_ROLES else {"tenantId": tenant_id}
    docs = await db.training_datasets.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=100)
    return {"datasets": docs}


@router.post("/training-datasets")
@limiter.limit("20/minute")
async def register_training_dataset(
    request: Request,
    response: Response,
    data: Dict[str, Any],
    current_user: dict = Depends(require_permission("manage:ai_models"))
):
    """Register a new training dataset (metadata only — file upload handled separately)."""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None) or (current_user.get("tenant_id") if isinstance(current_user, dict) else None)
    dataset = {
        "id": f"ds-{uuid.uuid4().hex[:10]}",
        "name": name,
        "size_bytes": int(data.get("size_bytes", 0)),
        "records": int(data.get("records", 0)),
        "description": data.get("description", ""),
        "ecosystem": data.get("ecosystem", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.get("sub", "system"),
    }
    if tenant_id:
        dataset["tenantId"] = tenant_id
    await db.training_datasets.insert_one(dataset)
    return dataset


@router.delete("/training-datasets/{dataset_id}")
@limiter.limit("10/minute")
async def delete_training_dataset(
    request: Request,
    response: Response,
    dataset_id: str,
    current_user: dict = Depends(require_permission("manage:ai_models"))
):
    """Remove a training dataset registration."""
    db = get_database()
    role = getattr(current_user, "role", "") or (current_user.get("role", "") if isinstance(current_user, dict) else "")
    tenant_id = getattr(current_user, "tenant_id", None) or (current_user.get("tenant_id") if isinstance(current_user, dict) else None)
    ds_filter: dict = {"id": dataset_id}
    if role not in _AUTOML_SUPER_ROLES and tenant_id:
        ds_filter["tenantId"] = tenant_id
    result = await db.training_datasets.delete_one(ds_filter)
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"success": True}


@router.post("/training-datasets/upload")
@limiter.limit("5/minute")
async def upload_training_dataset(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(""),
    current_user: dict = Depends(require_permission("manage:ai_models")),
):
    """
    Upload a CSV or JSON training dataset file.
    Parses the file to count rows/columns and registers it in the DB.
    """
    import io
    import csv
    import json as _json

    allowed = {
        "text/csv": "csv",
        "application/json": "json",
        "application/octet-stream": "csv",  # generic binary — assume CSV
    }
    content_type = file.content_type or "application/octet-stream"
    ext = allowed.get(content_type) or (
        "csv" if (file.filename or "").endswith(".csv") else
        "json" if (file.filename or "").endswith(".json") else None
    )
    if ext is None:
        raise HTTPException(status_code=400, detail="Only CSV and JSON files are supported")
    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    raw = await file.read()
    size_bytes = len(raw)
    records = 0
    columns: List[str] = []

    try:
        if ext == "csv":
            text = raw.decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            columns = list(reader.fieldnames or [])
            for _ in reader:
                records += 1
        else:
            data = _json.loads(raw)
            if isinstance(data, list):
                records = len(data)
                columns = list(data[0].keys()) if data else []
            elif isinstance(data, dict):
                records = 1
                columns = list(data.keys())
    except Exception as exc:
        logger.warning("Failed to parse uploaded file: %s", exc)
        raise HTTPException(status_code=422, detail="Failed to parse uploaded file")

    db = get_database()
    dataset = {
        "id": f"ds-{uuid.uuid4().hex[:10]}",
        "name": name or (file.filename or "uploaded_dataset"),
        "filename": file.filename,
        "format": ext,
        "size_bytes": size_bytes,
        "records": records,
        "columns": columns,
        "description": description or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.get("sub", current_user.get("username", "system")),
    }
    await db.training_datasets.insert_one(dataset)
    dataset.pop("_id", None)
    return dataset
