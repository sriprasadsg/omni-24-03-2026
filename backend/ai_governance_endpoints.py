from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Dict, Any
from ai_governance_service import get_ai_governance_service
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from models import AiPolicy, AiModel

router = APIRouter(prefix="/api/ai-governance", tags=["AI Governance"])

def get_tid(user: Any) -> str:
    if not user:
        return "default"
    if isinstance(user, dict):
        return user.get("tenant_id") or "default"
    return getattr(user, "tenant_id", None) or "default"

@router.get("/policies")
async def list_policies(current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    return await service.list_policies(get_tid(current_user))

@router.post("/policies")
async def create_policy(policy: AiPolicy, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    policy.tenantId = get_tid(current_user)
    return await service.create_policy(policy)

@router.post("/evaluate/{model_id}")
async def evaluate_model(model_id: str, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    report = await service.evaluate_model_compliance(model_id, get_tid(current_user))
    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])
    return report

@router.post("/expert-evaluate/{model_id}")
async def expert_evaluate_model(model_id: str, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    tid = get_tid(current_user)
    print(f"[DEBUG] Expert Evaluate Model ID: {model_id}, Tenant ID: {tid}")
    report = await service.run_ai_expert_evaluation(model_id, tid)
    if "error" in report:
        raise HTTPException(status_code=500, detail=report["error"])
    return report

@router.get("/models")
async def list_models(current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    return await service.list_models(get_tid(current_user))

@router.get("/dashboard")
async def governance_dashboard(current_user: TokenData = Depends(get_current_user)):
    """Aggregated AI governance health: compliance rate, risk distribution, violation counts."""
    db = get_database()
    service = get_ai_governance_service(db)
    return await service.get_governance_dashboard(get_tid(current_user))

@router.post("/register-model")
async def register_model(model_data: Dict[str, Any] = Body(...), current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    model_data["tenantId"] = get_tid(current_user)
    try:
        model = AiModel(**model_data)
        return await service.register_model(model)
    except Exception as e:
        print(f"[ERROR] Model registration failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/bias/{model_id}")
async def get_bias_metrics(model_id: str, current_user: TokenData = Depends(get_current_user)):
    """Compute and return fairness/bias metrics for a registered AI model."""
    db = get_database()
    service = get_ai_governance_service(db)
    result = await service.compute_bias_metrics(model_id, get_tid(current_user))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/shadow-ai/event")
async def receive_shadow_ai_event(
    event_data: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user)
):
    """Receive Shadow AI blocked events from agents"""
    import uuid
    from datetime import datetime, timezone
    db = get_database()
    
    event_doc = {
        "id": f"shadow_ai_{uuid.uuid4().hex[:12]}",
        "tenantId": get_tid(current_user),
        "endpoint": event_data.get("endpoint", "unknown"),
        "process": event_data.get("process", "unknown"),
        "pii_types": event_data.get("pii_types", []),
        "action_taken": event_data.get("action_taken", "monitored"),
        "agent_id": event_data.get("agent_id"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.shadow_ai_events.insert_one(event_doc)
    return {"success": True, "event_id": event_doc["id"]}
