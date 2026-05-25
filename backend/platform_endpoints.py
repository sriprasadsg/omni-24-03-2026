"""
Platform Endpoints
Covers: CSPM findings, Alert Rules, Data Sources, Agent Upgrade Jobs,
        Service Catalog (templates + provisioned), Developer Hub API list.
All previously stub-only features now backed by MongoDB.
"""
import os as _os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database

_SSL_VERIFY = not _os.getenv("DISABLE_SSL_VERIFY", "").lower() in ("1", "true", "yes")

router = APIRouter(prefix="/api", tags=["Platform"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# CSPM Findings
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/cspm/findings")
async def get_cspm_findings(
    tenantId: Optional[str] = None,
    _current_user: TokenData = Depends(get_current_user),
):
    """Return CSPM findings from cloud account scans."""
    db = get_database()
    query: Dict[str, Any] = {}
    if tenantId:
        query["tenantId"] = tenantId
    findings = await db.cspm_findings.find(query, {"_id": 0}).to_list(length=200)
    return findings


# ══════════════════════════════════════════════════════════════════════════════
# Alert Rules  (CRUD — replaces in-memory ALERT_RULES)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/alert-rules")
async def list_alert_rules(
    tenantId: Optional[str] = None,
    _current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    query: Dict[str, Any] = {}
    if tenantId:
        query["tenantId"] = tenantId
    rules = await db.alert_rules.find(query, {"_id": 0}).to_list(length=500)
    return rules


@router.post("/alert-rules")
async def create_alert_rule(
    rule: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    rule.setdefault("id", str(uuid.uuid4()))
    rule.setdefault("createdAt", _now())
    rule.setdefault("tenantId", getattr(current_user, "tenant_id", "default"))
    await db.alert_rules.insert_one({**rule})
    rule.pop("_id", None)
    return rule


@router.put("/alert-rules/{rule_id}")
async def update_alert_rule(
    rule_id: str,
    rule: Dict[str, Any] = Body(...),
    _current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    rule["id"] = rule_id
    rule["updatedAt"] = _now()
    result = await db.alert_rules.update_one({"id": rule_id}, {"$set": rule}, upsert=True)
    if result.matched_count == 0 and result.upserted_id is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    rule.pop("_id", None)
    return rule


@router.delete("/alert-rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    _current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    await db.alert_rules.delete_one({"id": rule_id})
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════════
# Data Sources  (CRUD — replaces in-memory DATA_SOURCES)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/data-sources")
async def list_data_sources(
    tenantId: Optional[str] = None,
    _current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    query: Dict[str, Any] = {}
    if tenantId:
        query["tenantId"] = tenantId
    sources = await db.data_sources.find(query, {"_id": 0}).to_list(length=200)
    return sources


@router.post("/data-sources")
async def create_data_source(
    source: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    source.setdefault("id", str(uuid.uuid4()))
    source.setdefault("createdAt", _now())
    source.setdefault("tenantId", getattr(current_user, "tenant_id", "default"))
    source.setdefault("status", "active")
    await db.data_sources.insert_one({**source})
    source.pop("_id", None)
    return source


@router.put("/data-sources/{source_id}")
async def update_data_source(
    source_id: str,
    source: Dict[str, Any] = Body(...),
    _current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    source["id"] = source_id
    source["updatedAt"] = _now()
    await db.data_sources.update_one({"id": source_id}, {"$set": source}, upsert=True)
    source.pop("_id", None)
    return source


@router.delete("/data-sources/{source_id}")
async def delete_data_source(
    source_id: str,
    _current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    await db.data_sources.delete_one({"id": source_id})
    return {"success": True}


@router.post("/data-sources/{source_id}/test")
async def test_data_source(
    source_id: str,
    _current_user: TokenData = Depends(get_current_user),
):
    """Attempt a lightweight connectivity check against the data source."""
    db = get_database()
    source = await db.data_sources.find_one({"id": source_id}, {"_id": 0})
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    import asyncio
    source_type = source.get("type", "").lower()
    host = source.get("host", "") or source.get("url", "")

    success = False
    message = "Connection test not implemented for this source type."

    if host and source_type in ("syslog", "tcp", "udp"):
        import socket as _socket
        port = int(source.get("port", 514))
        try:
            loop = asyncio.get_event_loop()
            conn = loop.run_in_executor(
                None,
                lambda: _socket.create_connection((host, port), timeout=3)
            )
            sock = await asyncio.wait_for(conn, timeout=5)
            sock.close()  # type: ignore
            success = True
            message = f"TCP connection to {host}:{port} succeeded."
        except Exception as exc:
            message = f"Connection failed: {exc}"
    elif host and source_type in ("http", "https", "rest"):
        try:
            import aiohttp
            url = host if host.startswith("http") else f"https://{host}"
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.head(url, ssl=_SSL_VERIFY) as resp:
                    success = resp.status < 500
                    message = f"HTTP {resp.status} from {url}"
        except Exception as exc:
            message = f"HTTP check failed: {exc}"
    else:
        success = True
        message = "Source registered (connectivity check skipped for this type)."

    await db.data_sources.update_one(
        {"id": source_id},
        {"$set": {"lastTested": _now(), "connectionStatus": "ok" if success else "error"}},
    )
    if not success:
        raise HTTPException(status_code=422, detail=message)
    return {"message": message}


# ══════════════════════════════════════════════════════════════════════════════
# Agent Upgrade Jobs
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/agents/upgrade-jobs")
async def list_upgrade_jobs(
    tenantId: Optional[str] = None,
    _current_user: TokenData = Depends(get_current_user),
):
    """List agent upgrade jobs from the database."""
    db = get_database()
    query: Dict[str, Any] = {}
    if tenantId:
        query["tenantId"] = tenantId
    jobs = await db.agent_upgrade_jobs.find(query, {"_id": 0}).sort("createdAt", -1).to_list(length=100)
    return jobs


# ══════════════════════════════════════════════════════════════════════════════
# Service Catalog
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/service-catalog/templates")
async def list_service_templates(
    _current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    templates = await db.service_templates.find({}, {"_id": 0}).to_list(length=200)
    return templates


@router.post("/service-catalog/templates")
async def create_service_template(
    template: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    template.setdefault("id", str(uuid.uuid4()))
    template.setdefault("createdAt", _now())
    template.setdefault("createdBy", getattr(current_user, "username", "system"))
    await db.service_templates.insert_one({**template})
    template.pop("_id", None)
    return template


@router.get("/service-catalog/provisioned")
async def list_provisioned_services(
    tenantId: Optional[str] = None,
    _current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    query: Dict[str, Any] = {}
    if tenantId:
        query["tenantId"] = tenantId
    services = await db.provisioned_services.find(query, {"_id": 0}).sort("provisionedAt", -1).to_list(length=200)
    return services


@router.post("/service-catalog/provisioned")
async def provision_service(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    payload.setdefault("id", str(uuid.uuid4()))
    payload.setdefault("provisionedAt", _now())
    payload.setdefault("status", "Provisioning")
    payload.setdefault("tenantId", getattr(current_user, "tenant_id", "default"))
    await db.provisioned_services.insert_one({**payload})
    payload.pop("_id", None)
    return payload


# ══════════════════════════════════════════════════════════════════════════════
# Developer Hub — API endpoint catalogue
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/developer-hub/endpoints")
async def list_api_endpoints(
    _current_user: TokenData = Depends(get_current_user),
):
    """
    Return the platform's OpenAPI endpoint list formatted for the Developer Hub UI.
    Derived at runtime from FastAPI's route registry — always up to date.
    """
    from fastapi import FastAPI
    import sys

    # Locate the running FastAPI app instance
    app_module = sys.modules.get("app")
    
    app_instance = getattr(app_module, "_fastapi_app", None)
    if not app_instance:
        app_instance = getattr(app_module, "app", None)
        
    if app_instance is None or not hasattr(app_instance, "routes"):
        return []

    endpoints = []
    seen: set = set()
    for route in app_instance.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            key = f"{method}:{path}"
            if key in seen:
                continue
            seen.add(key)
            tags = list(getattr(route, "tags", None) or [])
            endpoints.append({
                "id": key,
                "path": path,
                "method": method,
                "summary": getattr(route, "summary", "") or getattr(route, "name", ""),
                "tags": tags,
                "category": tags[0] if tags else "General",
            })
    return sorted(endpoints, key=lambda e: (e["category"], e["path"]))
