from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import uuid
import datetime
import os
import logging
from google import genai
from database import get_database
from ai_guardrails import scan_text
from local_ip import ollama_default_url
from rbac_utils import require_permission
from auth_types import TokenData
from fastapi import Depends
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-proxy", tags=["ai-governance"])

class LlmPrompt(BaseModel):
    provider: str # "openai", "azure", "anthropic", "gemini" 
    model: str
    messages: List[Dict[str, str]]
    temperature: float = 0.7

class PolicyConfig(BaseModel):
    block_pii: bool = True
    block_injection: bool = True
    allowed_models: List[str] = ["gpt-3.5-turbo", "gpt-4", "claude-3-opus", "gemini-2.0-flash", "gemini-1.5-pro"]

@router.post("/chat/completions")
async def proxy_chat_completion(
    prompt: LlmPrompt, 
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(require_permission("view:ai_governance"))
):
    """
    Intercepts LLM requests, scans for PII/Injection, logs audit, and forwards to provider.
    """
    db = get_database()
    
    # 1. Check Governance Policy (Tenant Specific or Global)
    settings = await db.ai_settings.find_one({"tenant_id": current_user.tenant_id})
    if not settings:
        settings = await db.ai_settings.find_one({"tenant_id": "global"}) or {}
    
    policy = PolicyConfig(**settings.get("policy", {}))
    
    # 2. Input Scanning (Guardrails)
    full_text = " ".join([m["content"] for m in prompt.messages])
    scan_result = scan_text(full_text, policy.block_pii, policy.block_injection)
    
    if not scan_result.passed:
        # Block request
        background_tasks.add_task(log_audit_event, db, prompt, "blocked", scan_result.findings, current_user.username, current_user.tenant_id)
        raise HTTPException(status_code=400, detail=f"Governance Policy Violation: {', '.join(scan_result.findings)}")
        
    # 3. Forward to LLM Provider
    response_content = ""
    provider = prompt.provider.lower()
    
    try:
        if provider == "ollama":
            # Forward to local Ollama
            ollama_url = os.getenv("OLLAMA_URL") or ollama_default_url()
            async with httpx.AsyncClient(timeout=60.0) as client:
                ollama_resp = await client.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model": prompt.model,
                        "messages": prompt.messages,
                        "stream": False,
                        "options": {"temperature": prompt.temperature}
                    }
                )
                ollama_resp.raise_for_status()
                response_content = ollama_resp.json().get("message", {}).get("content", "")
                finish_reason = "stop"

        elif provider == "openai" or os.getenv("LLM_PROVIDER", "gemini").lower() == "openai":
            # OpenAI / Azure OpenAI
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                sys_settings = await db.system_settings.find_one({"type": "llm"})
                if sys_settings:
                    openai_key = sys_settings.get("openaiApiKey")
            if not openai_key:
                raise Exception("OpenAI API Key not configured")

            async with httpx.AsyncClient(timeout=60.0) as client:
                openai_resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                    json={
                        "model": prompt.model if "gpt" in prompt.model else "gpt-3.5-turbo",
                        "messages": prompt.messages,
                        "temperature": prompt.temperature,
                    }
                )
                openai_resp.raise_for_status()
                data = openai_resp.json()
                response_content = data["choices"][0]["message"]["content"]
                finish_reason = data["choices"][0].get("finish_reason", "stop")

        else:
            # Default: Respect LLM_PROVIDER or fallback to Gemini
            configured_provider = os.getenv("LLM_PROVIDER", "gemini").lower()
            
            if configured_provider == "ollama":
                ollama_url = os.getenv("OLLAMA_URL") or ollama_default_url()
                model_name = prompt.model if "llama" in prompt.model or "mistral" in prompt.model else os.getenv("LLM_MODEL", "llama3.2:3b")
                async with httpx.AsyncClient(timeout=60.0) as client:
                    ollama_resp = await client.post(
                        f"{ollama_url}/api/chat",
                        json={
                            "model": model_name,
                            "messages": prompt.messages,
                            "stream": False,
                            "options": {"temperature": prompt.temperature}
                        }
                    )
                    ollama_resp.raise_for_status()
                    response_content = ollama_resp.json().get("message", {}).get("content", "")
                    finish_reason = "stop"
            else:
                # Default to Google Gemini
                api_key = os.getenv("GEMINI_API_KEY")
                if not api_key:
                    sys_settings = await db.system_settings.find_one({"type": "llm"})
                    if sys_settings:
                        api_key = sys_settings.get("apiKey")

                if not api_key:
                    raise Exception("LLM Provider API Key not configured. Set GEMINI_API_KEY or OPENAI_API_KEY in .env")

                client = genai.Client(api_key=api_key)
                model_name = prompt.model if "gemini" in prompt.model else os.getenv("LLM_MODEL", "gemini-2.0-flash")
                # Build context from message history
                system_msgs = [m["content"] for m in prompt.messages if m["role"] == "system"]
                user_msgs = [m["content"] for m in reversed(prompt.messages) if m["role"] == "user"]
                context = "\n".join(system_msgs)
                user_message = user_msgs[0] if user_msgs else full_text
                input_text = f"{context}\n\n{user_message}" if context else user_message
                provider_resp = client.models.generate_content(
                    model=model_name,
                    contents=input_text
                )
                response_content = provider_resp.text
                finish_reason = "stop"

            
    except Exception as e:
        background_tasks.add_task(log_audit_event, db, prompt, "error", [str(e)], current_user.username, current_user.tenant_id)
        raise HTTPException(status_code=502, detail="Upstream Provider Error")
    
    # Construct OpenAI-compatible response
    llm_response = {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(datetime.datetime.now().timestamp()),
        "model": prompt.model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response_content
            },
            "finish_reason": finish_reason
        }],
        "usage": {"prompt_tokens": len(full_text.split()), "completion_tokens": len(response_content.split()), "total_tokens": 0}
    }
    
    # 4. Log Success
    background_tasks.add_task(log_audit_event, db, prompt, "allowed", [], current_user.username, current_user.tenant_id, llm_response)
    
    return llm_response

async def log_audit_event(db, prompt, status, findings, user_id, tenant_id, response=None):
    event = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.now().isoformat(),
        "provider": prompt.provider,
        "model": prompt.model,
        "prompt_length": sum(len(m["content"]) for m in prompt.messages),
        "status": status,
        "findings": findings,
        "user_id": user_id,
        "tenant_id": tenant_id
    }
    await db.ai_audit_logs.insert_one(event)

@router.get("/policy")
async def get_guardrail_policy(current_user: TokenData = Depends(require_permission("view:ai_governance"))):
    """Return the current guardrail policy for this tenant (or global fallback)."""
    db = get_database()
    tid = getattr(current_user, "tenant_id", None)
    settings = (await db.ai_settings.find_one({"tenant_id": tid}, {"_id": 0})) or \
               (await db.ai_settings.find_one({"tenant_id": "global"}, {"_id": 0})) or {}
    return PolicyConfig(**settings.get("policy", {})).dict()


@router.put("/policy")
async def update_guardrail_policy(
    policy: PolicyConfig,
    current_user: TokenData = Depends(require_permission("manage:ai_governance")),
):
    """Save guardrail policy for this tenant."""
    db = get_database()
    tid = getattr(current_user, "tenant_id", None) or "global"
    await db.ai_settings.update_one(
        {"tenant_id": tid},
        {"$set": {"policy": policy.dict(), "updated_at": datetime.datetime.utcnow().isoformat()}},
        upsert=True,
    )
    return {"success": True, **policy.dict()}


class TestPromptRequest(BaseModel):
    prompt: str = Field(..., max_length=8_000)


@router.post("/test")
async def test_guardrail_policy(
    req: TestPromptRequest,
    current_user: TokenData = Depends(require_permission("view:ai_governance")),
):
    """Test a prompt against the current guardrail policy and return scan findings."""
    db = get_database()
    tid = getattr(current_user, "tenant_id", None)
    settings = (await db.ai_settings.find_one({"tenant_id": tid}, {"_id": 0})) or \
               (await db.ai_settings.find_one({"tenant_id": "global"}, {"_id": 0})) or {}
    policy = PolicyConfig(**settings.get("policy", {}))
    result = scan_text(req.prompt, block_pii=policy.block_pii, block_injection=policy.block_injection)
    return {
        "passed": result.passed,
        "findings": result.findings,
        "prompt_length": len(req.prompt),
        "policy_applied": policy.dict(),
    }


@router.get("/audit-logs")
async def get_audit_logs(current_user: TokenData = Depends(require_permission("manage:ai_governance"))):
    db = get_database()
    filt = {} if getattr(current_user, "role", "") in {"Super Admin", "super_admin", "platform-admin"} \
        else {"tenant_id": getattr(current_user, "tenant_id", None)}
    logs = await db.ai_audit_logs.find(filt, {"_id": 0}).sort("timestamp", -1).to_list(length=100)
    return logs


# ── Convenience /api/ai/chat endpoint (used by ChatAssistant widget) ──────────
chat_router = APIRouter(prefix="/api/ai", tags=["AI Chat"])

class ChatRequest(BaseModel):
    message: str = Field(..., max_length=32_000)
    context: Optional[str] = Field(
        default="You are a helpful enterprise security assistant for the Omni-Agent platform.",
        max_length=4_000,
    )
    history: Optional[List[Dict[str, str]]] = Field(default_factory=list, max_length=100)
    provider: Optional[str] = Field(default="gemini", max_length=50)
    model: Optional[str] = Field(default=None, max_length=100)

@chat_router.post("/chat")
async def ai_chat(req: ChatRequest, current_user: TokenData = Depends(require_permission("view:dashboard"))):
    """General-purpose AI chat endpoint used by the Chat Assistant widget."""
    db = get_database()

    # Resolve API key
    provider = req.provider or os.getenv("LLM_PROVIDER", "gemini")
    response_text = ""

    try:
        from ai_service import ai_service
        # Use context from request if available, otherwise default to dashboard
        view = "dashboard"
        if req.context and isinstance(req.context, dict):
            view = req.context.get("currentView", "dashboard")
        elif req.context and isinstance(req.context, str):
            # If context is a string summary, we still default view but keep context info
            view = "dashboard"
            
        response_text = await ai_service.chat(req.message, {"currentView": view, "userId": current_user.username})
    except Exception as e:
        logger.error(f"AI Chat error: {e}")
        response_text = f"AI service temporarily unavailable. Error: {str(e)[:100]}"

    # Log chat to audit log
    await db.ai_audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "provider": provider,
        "model": req.model or "auto",
        "prompt_length": len(req.message),
        "status": "allowed",
        "findings": [],
        "user_id": current_user.username,
        "tenant_id": current_user.tenant_id,
        "type": "chat"
    })

    return {
        "response": response_text,
        "provider": provider,
        "configured": True
    }

@chat_router.get("/config")
async def get_ai_config(current_user: TokenData = Depends(require_permission("manage:settings"))):
    """Get current AI configuration status."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    return {
        "provider": os.getenv("LLM_PROVIDER", "gemini"),
        "model": os.getenv("LLM_MODEL", "gemini-2.0-flash"),
        "gemini_configured": bool(gemini_key),
        "openai_configured": bool(openai_key),
        "ollama_url": os.getenv("OLLAMA_URL") or ollama_default_url(),
    }
