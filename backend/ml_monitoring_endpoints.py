"""
ML Monitoring API Endpoints

Provides model drift detection and monitoring capabilities for AI systems.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from ml_monitoring_service import get_ml_monitoring_service
from rbac_utils import require_permission
import logging

logger = logging.getLogger(__name__)

def _get(user, key, default=None):
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)

router = APIRouter(prefix="/api/ml-monitoring", tags=["ML Monitoring"])

def _get(user, key, default=None):
    if isinstance(user, dict): return user.get(key, default)
    return getattr(user, key, default)



# Request/Response Models
class DriftDetectionRequest(BaseModel):
    model_id: str
    tenant_id: str
    baseline_window_days: int = 30
    current_window_days: int = 7


class DriftDetectionResult(BaseModel):
    model_id: str
    tenant_id: str
    drift_detected: bool
    severity: str
    metrics: Dict[str, float]
    baseline_samples: int
    current_samples: int
    detected_at: str
    recommendation: str


# Endpoints
@router.post("/train")
async def train_predictive_model(
    current_user: dict = Depends(require_permission("manage:ai_systems"))
):
    """Manually triggers retraining of the Patch Failure Prediction Model and Anomaly Model"""
    from ml_service import MLPredictionService
    db = get_database()
    ml_service = MLPredictionService(db)
    
    patch_result = await ml_service.train_model()
    anomaly_result = await ml_service.train_anomaly_model()
    
    return {
        "patch_model": patch_result,
        "anomaly_model": anomaly_result
    }

@router.post("/detect-drift", response_model=DriftDetectionResult)
async def detect_model_drift(
    request: DriftDetectionRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:ai_systems"))
):
    """
    Detect drift in a specific AI model
    
    Analyzes prediction distribution and performance metrics to detect drift
    """
    service = get_ml_monitoring_service(db)
    
    result = await service.detect_drift(
        model_id=request.model_id,
        tenant_id=request.tenant_id,
        baseline_window_days=request.baseline_window_days,
        current_window_days=request.current_window_days
    )
    
    return DriftDetectionResult(**result)


@router.get("/drift-history/{model_id}")
async def get_drift_history(
    model_id: str,
    tenant_id: Optional[str] = None,
    limit: int = 30,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    Get historical drift detections for a model
    
    Returns timeline of drift detections with metrics
    """
    if not tenant_id and _get(current_user, 'role') != "Super Admin":
        tenant_id = _get(current_user, "tenantId")
    
    service = get_ml_monitoring_service(db)
    history = await service.get_drift_history(
        model_id=model_id,
        tenant_id=tenant_id or _get(current_user, "tenantId"),
        limit=limit
    )
    
    return history


@router.get("/drift")
async def get_drift_scores(
    tenant_id: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:ai_systems")),
):
    """
    Return drift scores per registered AI model.
    Tests: O6 — GET /api/ml-monitoring/drift → Drift scores per model
    """
    caller_role = _get(current_user, "role", "")
    caller_tenant = _get(current_user, "tenantId") or _get(current_user, "tenant_id")
    # Only super-admins may cross tenant boundaries via the query param
    effective_tenant = (tenant_id if caller_role == "Super Admin" else caller_tenant) or caller_tenant
    query: Dict[str, Any] = {}
    if caller_role != "Super Admin" and effective_tenant:
        query["tenantId"] = effective_tenant

    ai_systems = await db.ai_systems.find(query, {"_id": 0, "id": 1, "name": 1, "type": 1}).to_list(length=100)
    drift_records = await db.model_drift.find(query, {"_id": 0}).sort("detected_at", -1).to_list(length=200)

    drift_by_model: Dict[str, Any] = {}
    for r in drift_records:
        mid = r.get("model_id") or r.get("systemId", "")
        if mid and mid not in drift_by_model:
            drift_by_model[mid] = {
                "model_id": mid,
                "drift_score": r.get("drift_score", r.get("driftScore", 0)),
                "drift_detected": r.get("drift_detected", False),
                "detected_at": r.get("detected_at"),
                "metric": r.get("metric", "feature_drift"),
            }

    result = []
    for sys in ai_systems:
        mid = sys["id"]
        drift = drift_by_model.get(mid, {"drift_score": 0, "drift_detected": False, "detected_at": None, "metric": "none"})
        result.append({"model_id": mid, "model_name": sys.get("name", mid), **drift})

    for mid, drift in drift_by_model.items():
        if not any(r["model_id"] == mid for r in result):
            result.append({"model_id": mid, "model_name": mid, **drift})

    return {"drift_scores": result, "total": len(result)}


@router.get("/models-status")
async def get_all_models_drift_status(
    tenant_id: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    Get drift status for all models in a tenant
    
    Returns summary of drift status across all AI systems
    """
    if not tenant_id and _get(current_user, 'role') != "Super Admin":
        tenant_id = _get(current_user, "tenantId")
    
    service = get_ml_monitoring_service(db)
    try:
        status = await service.get_all_models_drift_status(
            tenant_id=tenant_id or _get(current_user, "tenantId")
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("ML drift status check failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")

    return status


@router.post("/analyze-all")
async def analyze_all_models(
    tenant_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:ai_systems"))
):
    """
    Trigger drift analysis for all models in a tenant
    
    Runs in background and returns immediately
    """
    async def run_analysis():
        service = get_ml_monitoring_service(db)
        
        # Get all AI systems
        cursor = db.ai_systems.find({"tenantId": tenant_id})
        
        async for system in cursor:
            try:
                await service.detect_drift(
                    model_id=system.get("id"),
                    tenant_id=tenant_id
                )
            except Exception as e:
                logger.error("Error analyzing model %s: %s", system.get("id"), e)
    
    background_tasks.add_task(run_analysis)
    
    return {
        "message": "Drift analysis started for all models",
        "tenant_id": tenant_id
    }


@router.post("/record-prediction")
async def record_prediction(
    model_id: str,
    prediction: float,
    actual: Optional[float] = None,
    features: Optional[Dict[str, Any]] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:ai_systems"))
):
    """
    Record a model prediction for drift monitoring
    
    Stores prediction data for future drift analysis
    """
    from datetime import datetime, timezone
    
    prediction_doc = {
        "model_id": model_id,
        "tenant_id": _get(current_user, "tenantId"),
        "prediction": prediction,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": features or {}
    }
    
    if actual is not None:
        prediction_doc["actual"] = actual
        prediction_doc["accuracy"] = 1.0 if abs(prediction - actual) < 0.1 else 0.0
    
    await db.model_predictions.insert_one(prediction_doc)
    
    return {"message": "Prediction recorded successfully"}
