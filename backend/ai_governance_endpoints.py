from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Dict, Any, Optional
from ai_governance_service import get_ai_governance_service
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from models import AiPolicy, AiModel

router = APIRouter(prefix="/api/ai-governance", tags=["AI Governance"])

def get_tid(user: Any) -> Optional[str]:
    if not user:
        return None
    tid = None
    if isinstance(user, dict):
        tid = user.get("tenant_id") or "default"
    else:
        tid = getattr(user, "tenant_id", None) or "default"
    import logging
    logging.warning(f"[DEBUG] get_tid - User: {getattr(user, 'username', 'N/A')}, Tenant ID: {tid}")
    return tid

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
