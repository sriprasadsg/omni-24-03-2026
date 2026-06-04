from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from local_ip import ollama_default_url
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTS = {
    "169.254.169.254",       # AWS/Azure/GCP instance metadata
    "metadata.google.internal",
    "metadata.internal",
}


def _is_safe_host(host: str) -> bool:
    """Block cloud metadata endpoints and link-local IPs."""
    if not host:
        return False
    h = host.strip().lower()
    if h in _BLOCKED_HOSTS:
        return False
    try:
        addr = ipaddress.ip_address(h)
        if addr.is_link_local:
            return False
    except ValueError:
        pass
    return True

router = APIRouter(prefix="/api/settings", tags=["Settings"])

_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin"}


def _require_admin(user: TokenData) -> None:
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")


@router.get("/database")
async def get_database_settings(current_user: TokenData = Depends(get_current_user)):
    """Get database settings"""
    db = get_database()
    settings = await db.system_settings.find_one({"type": "database"}, {"_id": 0})
    return settings or {}

@router.post("/database")
async def save_database_settings(settings: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    """Save database settings — admin only"""
    _require_admin(current_user)
    db = get_database()
    # Add type identifier
    settings["type"] = "database"
    await db.system_settings.update_one(
        {"type": "database"},
        {"$set": settings},
        upsert=True
    )
    return settings

@router.get("/llm")
async def get_llm_settings(current_user: TokenData = Depends(get_current_user)):
    """Get LLM settings — tenant-specific, with auto-detected defaults for new tenants"""
    db = get_database()
    settings = await db.system_settings.find_one({"type": "llm"}, {"_id": 0})
    if not settings:
        import os as _os
        _url = _os.getenv("OLLAMA_URL", ollama_default_url())
        _model = _os.getenv("OLLAMA_MODEL", _os.getenv("LLM_MODEL", "llama3.2:3b"))
        settings = {
            "type":        "llm",
            "provider":    "Local",
            "ollamaUrl":   _url,
            "ollamaModel": _model,
            "model":       _model,
            "host":        _url.replace("http://", "").replace("https://", ""),
            "temperature": 0.7,
            "timeout":     30,
        }
    # Normalise legacy "Ollama (Local)" label → "Local"
    if settings.get("provider") == "Ollama (Local)":
        settings["provider"] = "Local"
    return settings

@router.post("/llm")
async def save_llm_settings(settings: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    """Save LLM settings — admin only"""
    _require_admin(current_user)
    db = get_database()
    # Add type identifier
    settings["type"] = "llm"
    await db.system_settings.update_one(
        {"type": "llm"},
        {"$set": settings},
        upsert=True
    )
    # Re-initialize AI service if possible (optional, but good practice)
    from ai_service import ai_service
    await ai_service.initialize()

    return settings


@router.post("/test-db-connection")
async def test_db_connection(
    settings: Dict[str, Any],
    current_user: TokenData = Depends(get_current_user),
):
    """
    Test connectivity to the specified database host/port.
    Performs a TCP socket probe (host + port reachable) plus a lightweight
    driver-level ping for MongoDB when the motor client is available.
    """
    host = settings.get("host", "").strip()
    port = int(settings.get("port", 0))
    db_type = settings.get("type", "MongoDB")

    if not host or not port:
        return {"success": False, "message": "Host and port are required"}

    if not _is_safe_host(host):
        raise HTTPException(status_code=400, detail="Connections to this host are not permitted")

    # 1. TCP reachability check (works for all DB types)
    loop = asyncio.get_event_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(
                None, lambda: socket.create_connection((host, port), timeout=3)
            ),
            timeout=4.0,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        return {"success": False, "message": f"Cannot reach {host}:{port} — {exc}"}

    # 2. For MongoDB, attempt a lightweight server_info ping
    if db_type == "MongoDB":
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            username = settings.get("username", "")
            db_name = settings.get("databaseName", "test")
            if username:
                uri = f"mongodb://{username}@{host}:{port}/{db_name}?serverSelectionTimeoutMS=3000"
            else:
                uri = f"mongodb://{host}:{port}/{db_name}?serverSelectionTimeoutMS=3000"
            client = AsyncIOMotorClient(uri)
            await asyncio.wait_for(client.server_info(), timeout=4.0)
            client.close()
            return {"success": True, "message": f"Successfully connected to MongoDB at {host}:{port}"}
        except Exception as exc:
            return {"success": False, "message": f"MongoDB ping failed: {exc}"}

    # For PostgreSQL / MySQL — TCP probe passed, that's sufficient without the driver
    return {"success": True, "message": f"TCP connection to {db_type} at {host}:{port} succeeded"}


@router.post("/test-llm-connection")
async def test_llm_connection(
    settings: Dict[str, Any],
    current_user: TokenData = Depends(get_current_user),
):
    """Test connectivity to the configured LLM provider (Ollama or Gemini)."""
    provider = settings.get("provider", "").lower()
    if provider in ("local", "ollama"):
        ollama_url = (settings.get("ollamaUrl") or ollama_default_url()).rstrip("/")
        parsed = urlparse(ollama_url)
        if not _is_safe_host(parsed.hostname or ""):
            raise HTTPException(status_code=400, detail="Connections to this host are not permitted")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{ollama_url}/api/tags")
                if resp.status_code == 200:
                    models = [m.get("name") for m in resp.json().get("models", [])]
                    return {"success": True, "message": f"Connected to Ollama at {ollama_url}", "models": models}
                return {"success": False, "message": f"Ollama returned status {resp.status_code}"}
        except Exception as exc:
            return {"success": False, "message": f"Cannot reach Ollama at {ollama_url}: {exc}"}

    if provider == "gemini":
        api_key = settings.get("apiKey", "")
        if not api_key or "*" in api_key:
            return {"success": False, "message": "A valid Gemini API key is required"}
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            model_name = settings.get("model", "gemini-2.0-flash")
            response = client.models.generate_content(model=model_name, contents='Say "test successful"')
            if response.text:
                return {"success": True, "message": "Gemini connection successful"}
            return {"success": False, "message": "Gemini returned empty response"}
        except Exception as exc:
            return {"success": False, "message": f"Gemini test failed: {exc}"}

    if provider in ("anthropic", "anthropic claude"):
        api_key = settings.get("apiKey", "")
        if not api_key or "*" in api_key:
            return {"success": False, "message": "A valid Anthropic API key is required"}
        try:
            import httpx
            model_name = settings.get("model", "claude-haiku-4-5-20251001")
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "max_tokens": 16,
                        "messages": [{"role": "user", "content": 'Say "test successful"'}],
                    },
                )
                if resp.status_code == 200:
                    return {"success": True, "message": f"Anthropic Claude connection successful (model: {model_name})"}
                return {"success": False, "message": f"Anthropic returned status {resp.status_code}: {resp.text[:200]}"}
        except Exception as exc:
            return {"success": False, "message": f"Anthropic test failed: {exc}"}

    return {"success": False, "message": f"Unknown provider: {provider}"}
