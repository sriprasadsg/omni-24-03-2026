from fastapi import APIRouter, HTTPException, Body, Depends
from typing import Dict, Any
from ai_playbook_service import ai_playbook_service
from ai_remediation_service import ai_remediation_service
from ai_service import ai_service
from authentication_service import get_current_user

router = APIRouter(prefix="/api/ai", tags=["AI Automation"])

from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

@router.get("")
@router.get("/")
async def ai_service_status(current_user=Depends(get_current_user)):
    """Get AI automation service status including active provider."""
    provider_name = getattr(getattr(ai_service, "provider", None), "name", None)
    is_mock = provider_name == "Chitti (Mock)" if provider_name else not ai_service.is_configured
    return {
        "status": "operational",
        "services": ["remediation", "playbook_generation", "chat_assistant"],
        "version": "1.0.0",
        "provider": provider_name or "unconfigured",
        "is_mock_mode": is_mock,
        "mock_mode_reason": (
            "No LLM provider configured. Set GEMINI_API_KEY or OLLAMA_URL environment variable, "
            "or configure via Settings > LLM Provider."
        ) if is_mock else None,
    }


@router.post("/remediation/cspm")
async def generate_cspm_remediation(
    finding: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("remediate:agents"))
):
    """Generate remediation for CSPM finding"""
    return await ai_remediation_service.generate_cspm_remediation(finding)

@router.post("/remediation/iac")
async def generate_iac_fix(
    finding: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("remediate:agents"))
):
    """Generate IaC fix for CSPM finding"""
    return await ai_remediation_service.generate_iac_fix(finding)

@router.post("/chat")
async def chat_assistant(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))
):
    """Chat with AI Assistant"""
    message = payload.get("message")
    context = payload.get("context", {})
    # Inject tenant_id into context for scoped chat if needed
    context["tenantId"] = get_tenant_id()
    return {"response": await ai_service.chat(message, context)}

@router.post("/generate-playbook")
async def generate_playbook(
    payload: Dict[str, str] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:security_playbooks"))
):
    """Generate a playbook using AI"""
    prompt = payload.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    tenant_id = get_tenant_id()

    playbook = await ai_playbook_service.generate_playbook(prompt, tenant_id)
    return playbook


@router.post("/analyze-impact")
async def analyze_impact(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
):
    """
    Analyze the blast radius / business impact of a security finding or change.
    Body: { "finding": {...}, "context": {...} }
    """
    finding = payload.get("finding") or payload
    context = payload.get("context", {})
    context["tenantId"] = get_tenant_id()

    prompt = (
        "You are a senior security analyst. Analyze the blast radius and business impact "
        "of the following security finding. Return a JSON object with keys: "
        "'impact_summary' (string), 'affected_systems' (list of strings), "
        "'risk_score' (0-100 integer), 'recommended_actions' (list of strings), "
        "'urgency' ('low'|'medium'|'high'|'critical').\n\n"
        f"Finding:\n{__import__('json').dumps(finding, default=str, indent=2)}"
    )
    try:
        raw = await ai_service.generate_text(prompt, source="analyze_impact")
        import json as _json, re as _re
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        match = _re.search(r"\{[\s\S]+\}", cleaned)
        result = _json.loads(match.group(0)) if match else {"impact_summary": cleaned}
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).error("AI impact analysis error: %s", exc)
        result = {
            "impact_summary": "AI impact analysis unavailable.",
            "affected_systems": [],
            "risk_score": 50,
            "recommended_actions": ["Manual review required"],
            "urgency": "medium",
        }
    return result


@router.post("/threat-hunt")
async def ai_threat_hunt(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("view:threat_hunting")),
):
    """
    AI-powered threat hunting: translate a natural-language query into a MongoDB
    aggregation pipeline, execute it against security_events, and return matches.
    Body: { "query": "show me failed logins from last 24h" }
    """
    import json as _json
    import re as _re
    from datetime import datetime, timezone, timedelta
    from database import get_database

    query_text = payload.get("query", "").strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query is required")
    # Cap length and strip characters that could break prompt structure
    query_text = query_text[:500]
    query_text = _re.sub(r'[^\w\s\-\.\,\:\(\)\']', ' ', query_text).strip()

    tenant_id = get_tenant_id()
    db = get_database()

    # Step 1: Ask AI to generate a MongoDB match filter
    pipeline_prompt = (
        "You are an expert SIEM analyst. Convert the following natural-language threat hunt query "
        "into a MongoDB `$match` filter (JSON) that can be applied to a `security_events` collection. "
        "The collection has these fields: tenantId, time (ISO8601 string), severity (Critical/High/Medium/Low), "
        "metadata.product (source system), message (string), category_name, class_name, activity_name.\n\n"
        "Rules:\n"
        "- Output ONLY a valid JSON object (the $match filter). No explanation.\n"
        "- Use $regex for keyword searches on message/category_name.\n"
        "- For time ranges, use $gte/$lte on the `time` field as ISO8601 strings.\n"
        "- Always include { \"tenantId\": \"" + tenant_id + "\" } in the filter.\n\n"
        f"Query: {query_text}\n\nJSON filter:"
    )

    match_filter: Dict[str, Any] = {"tenantId": tenant_id}
    generated_pipeline: list = []

    try:
        raw = await ai_service.generate_text(pipeline_prompt, source="threat_hunt")
        # Extract JSON from LLM response
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        m = _re.search(r"\{[\s\S]+\}", cleaned)
        if m:
            ai_filter = _json.loads(m.group(0))
            # Whitelist known fields only — strips MongoDB operators and unknown keys
            _SAFE_FIELDS = frozenset({
                "message", "severity", "time", "category_name",
                "source", "host", "ip", "user", "action", "tenantId",
            })
            ai_filter = {k: v for k, v in ai_filter.items() if k in _SAFE_FIELDS}
            ai_filter["tenantId"] = tenant_id
            match_filter = ai_filter
            generated_pipeline = [{"$match": match_filter}, {"$sort": {"time": -1}}, {"$limit": 200}]
    except Exception:
        # Fall back: keyword regex over message field
        match_filter = {
            "tenantId": tenant_id,
            "message": {"$regex": _re.escape(query_text[:100]), "$options": "i"},
        }
        generated_pipeline = [{"$match": match_filter}, {"$sort": {"time": -1}}, {"$limit": 200}]

    # Step 2: Execute the query
    try:
        cursor = db.security_events.find(match_filter, {"_id": 0}).sort("time", -1).limit(200)
        events = await cursor.to_list(length=200)
        return {
            "success": True,
            "data": events,
            "generated_pipeline": generated_pipeline,
            "total": len(events),
        }
    except Exception as exc:
        # If the AI filter is malformed, fall back to simple message regex
        try:
            safe_filter = {
                "tenantId": tenant_id,
                "message": {"$regex": _re.escape(query_text[:80]), "$options": "i"},
            }
            cursor = db.security_events.find(safe_filter, {"_id": 0}).sort("time", -1).limit(200)
            events = await cursor.to_list(length=200)
            return {
                "success": True,
                "data": events,
                "generated_pipeline": [{"$match": safe_filter}],
                "total": len(events),
                "fallback": True,
            }
        except Exception as exc2:
            import logging as _logging
            _logging.getLogger(__name__).error("Threat hunt fallback query error: %s", exc2)
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/feedback")
async def record_ai_feedback(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
):
    """
    Record quality feedback for an AI-generated response.
    Used to build a dataset for fine-tuning and to drive LLM self-tuning.
    Body: { "prompt_id": str, "response_preview": str, "rating": 1-5, "helpful": bool, "comment": str }
    """
    from database import get_database
    from datetime import datetime, timezone
    import uuid as _uuid
    db = get_database()
    doc = {
        "id": str(_uuid.uuid4()),
        "prompt_id": payload.get("prompt_id"),
        "response_preview": payload.get("response_preview", "")[:500],
        "rating": payload.get("rating"),
        "helpful": payload.get("helpful"),
        "comment": payload.get("comment", ""),
        "tenant_id": get_tenant_id(),
        "submitted_by": getattr(current_user, "email", str(current_user)),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.ai_feedback.insert_one(doc)
    return {"status": "recorded", "feedback_id": doc["id"]}
