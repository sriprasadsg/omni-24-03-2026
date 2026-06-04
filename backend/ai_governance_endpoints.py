from fastapi import APIRouter, HTTPException, Depends, Body, Request, Response
import logging
from typing import Dict, Any
from ai_governance_service import get_ai_governance_service
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from models import AiPolicy, AiModel
from rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-governance", tags=["AI Governance"])

def get_tid(user: Any):
    if not user:
        return None
    if isinstance(user, dict):
        return user.get("tenant_id") or user.get("tenantId") or None
    return getattr(user, "tenant_id", None) or None

@router.get("/policies")
async def list_policies(current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    return await service.list_policies(get_tid(current_user))

@router.post("/policies")
@limiter.limit("10/minute")
async def create_policy(request: Request, response: Response, policy: AiPolicy, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    policy.tenantId = get_tid(current_user)
    return await service.create_policy(policy)

@router.post("/evaluate")
@limiter.limit("20/minute")
async def evaluate_policy_action(
    request: Request,
    response: Response,
    body: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Evaluate whether an action is allowed for a model under active AI governance policies.
    Uses ast.literal_eval for safe condition evaluation — eval() is never called.

    Body: { model_id: str, action: str, context?: dict }
    Returns: { allowed: bool, policy_id?, reason? }
    """
    import ast

    model_id = body.get("model_id", "")
    action = body.get("action", "")
    ctx: dict = body.get("context") or {}

    if not model_id or not action:
        raise HTTPException(status_code=422, detail="model_id and action are required")

    db = get_database()
    tenant_id = get_tid(current_user)
    policy_filter: dict = {"$or": [{"tenantId": tenant_id}, {"tenantId": None}], "enabled": True}
    policies = await db.ai_policies.find(policy_filter, {"_id": 0}).to_list(length=100)

    def _safe_eval_condition(condition: str, eval_ctx: dict) -> bool:
        """
        Evaluate a simple boolean condition string against eval_ctx.
        Only supports: membership test (<var> in <literal_list>) and
        comparison (<var> <op> <literal>).
        Raises ValueError for any expression that cannot be parsed as a safe literal.
        """
        if not condition or not condition.strip():
            return True

        # Substitute context variables using word-boundary replacement so that a
        # key like "on" does not corrupt substrings like "action" or "condition".
        import re as _re
        substituted = condition
        for k, v in eval_ctx.items():
            pattern = r'\b' + _re.escape(k) + r'\b'
            if isinstance(v, str):
                substituted = _re.sub(pattern, repr(v), substituted)
            elif isinstance(v, (int, float, bool)):
                substituted = _re.sub(pattern, str(v), substituted)

        # Now try to evaluate the resulting pure-literal expression
        try:
            result = ast.literal_eval(substituted)
            if isinstance(result, bool):
                return result
        except (ValueError, SyntaxError):
            pass

        # Handle `x in [...]` and `x not in [...]` patterns explicitly
        import re
        m = re.match(r"^\s*(.+?)\s+(not\s+in|in)\s+(.+)\s*$", substituted.strip(), re.IGNORECASE)
        if m:
            left_str, op, right_str = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            try:
                left = ast.literal_eval(left_str)
                right = ast.literal_eval(right_str)
                return (left not in right) if "not" in op else (left in right)
            except (ValueError, SyntaxError) as exc:
                raise ValueError(f"Unsafe or unparseable condition: {condition!r}") from exc

        raise ValueError(f"Condition cannot be safely evaluated: {condition!r}")

    for policy in policies:
        rules = policy.get("rules", [])
        for rule in rules:
            if rule.get("action") != action and rule.get("action") != "*":
                continue
            condition = rule.get("condition", "")
            try:
                allowed = _safe_eval_condition(condition, ctx)
            except ValueError as exc:
                logger.warning("Policy condition rejected (unsafe): %s", exc)
                return {"allowed": False, "policy_id": policy.get("id"), "reason": str(exc)}

            if not allowed:
                return {"allowed": False, "policy_id": policy.get("id"), "reason": rule.get("reason", "Policy condition not met")}

    return {"allowed": True}


@router.post("/evaluate/{model_id}")
@limiter.limit("20/minute")
async def evaluate_model(request: Request, response: Response, model_id: str, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    report = await service.evaluate_model_compliance(model_id, get_tid(current_user))
    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])
    return report

@router.post("/expert-evaluate/{model_id}")
@limiter.limit("5/minute")
async def expert_evaluate_model(request: Request, response: Response, model_id: str, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    tid = get_tid(current_user)
    logger.debug("Expert Evaluate Model ID: %s, Tenant ID: %s", model_id, tid)
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
@limiter.limit("10/minute")
async def register_model(request: Request, response: Response, model_data: Dict[str, Any] = Body(...), current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    service = get_ai_governance_service(db)
    model_data["tenantId"] = get_tid(current_user)
    try:
        model = AiModel(**model_data)
        return await service.register_model(model)
    except Exception as e:
        logger.error("Model registration failed: %s", e)
        raise HTTPException(status_code=400, detail="Bad request")

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
@limiter.limit("100/minute")
async def receive_shadow_ai_event(
    request: Request,
    response: Response,
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
