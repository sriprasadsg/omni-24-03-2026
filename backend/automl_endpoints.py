from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import Dict, Any, List, Optional
from automl_service import automl_service
from rbac_utils import require_permission
import uuid
from datetime import datetime, timezone
from database import get_database

router = APIRouter(prefix="/api/automl", tags=["AutoML & Hyperparameter Optimization"])

@router.get("/studies")
async def list_studies(
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    List all optimization studies.
    """
    return await automl_service.get_all_studies()

@router.post("/study")
async def create_study(
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
async def run_trials(
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
    docs = await db.training_datasets.find({}, {"_id": 0}).sort("created_at", -1).to_list(length=100)
    return {"datasets": docs}


@router.post("/training-datasets")
async def register_training_dataset(
    data: Dict[str, Any],
    current_user: dict = Depends(require_permission("manage:ai_models"))
):
    """Register a new training dataset (metadata only — file upload handled separately)."""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    db = get_database()
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
    await db.training_datasets.insert_one(dataset)
    return dataset


@router.delete("/training-datasets/{dataset_id}")
async def delete_training_dataset(
    dataset_id: str,
    current_user: dict = Depends(require_permission("manage:ai_models"))
):
    """Remove a training dataset registration."""
    db = get_database()
    result = await db.training_datasets.delete_one({"id": dataset_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"success": True}


@router.post("/training-datasets/upload")
async def upload_training_dataset(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(""),
    current_user: dict = Depends(require_permission("manage:ai_models")),
):
    """
    Upload a CSV or JSON training dataset file.
    Parses the file to count rows/columns and registers it in the DB.
    """
    import io, csv, json as _json

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
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}")

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
