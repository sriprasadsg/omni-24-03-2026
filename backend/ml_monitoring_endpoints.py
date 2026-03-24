"""
ML Monitoring API Endpoints

Provides model drift detection and monitoring capabilities for AI systems.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from ml_monitoring_service import get_ml_monitoring_service
from rbac_utils import require_permission

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
    """Manually triggers retraining of the Patch Failure Prediction Model"""
    from ml_service import MLPredictionService
    db = get_database()
    ml_service = MLPredictionService(db)
    
    result = await ml_service.train_model()
    return result

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
    except Exception:
        status = {"models": [], "drift_detected_count": 0, "healthy_count": 0}
    
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
                print(f"Error analyzing model {system.get('id')}: {e}")
    
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
