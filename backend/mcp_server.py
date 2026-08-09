"""MCP Server Implementation - Spec-compliant MCP server with stdio and SSE transports."""
import os
import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from mcp.types import Tool

from database import get_database
from tenant_context import get_tenant_id
from authentication_service import get_current_user
from auth_types import TokenData
from cloud_checks_service import cloud_checks_service

logger = logging.getLogger(__name__)

# ─── MCP Server Instance ──────────────────────────────────────────────────────
# FastMCP provides both stdio and SSE transports
mcp = FastMCP("Enterprise Omni-Agent AI Platform")

# ─── Tool Registration ────────────────────────────────────────────────────────

@mcp.tool()
async def list_frameworks() -> List[Dict[str, str]]:
    """List all compliance frameworks available for this tenant"""
    db = get_database()
    tenant_id = get_tenant_id()
    frameworks = await db._db.compliance_frameworks.find(
        {"$or": [
            {"tenant_id": {"$exists": False}},
            {"tenant_id": ""},
            {"tenant_id": None},
        ]}, {"_id": 0}
    ).to_list(length=100)
    return [{"id": f.get("id"), "name": f.get("name")} for f in frameworks]

@mcp.tool()
async def get_control_status(control_id: str) -> Dict[str, Any]:
    """Get compliance status for a specific control across assets"""
    db = get_database()
    tenant_id = get_tenant_id()
    results = await db.asset_compliance.find(
        {"controlId": control_id, "tenantId": tenant_id}, {"_id": 0}
    ).to_list(length=200)
    return {
        "control_id": control_id,
        "assets": len(results),
        "statuses": sorted({r.get("status") for r in results})
    }

@mcp.tool()
async def run_cloud_check(provider: str, account_id: str) -> Dict[str, Any]:
    """Run a cloud security check against a provider account.

    Only providers with runnable posture checks are accepted — the accepted set is
    the single source of truth in cloud_checks_service.RUNNABLE_PROVIDERS.
    """
    from cloud_checks_service import RUNNABLE_PROVIDERS
    if provider not in RUNNABLE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"provider must be one of {', '.join(RUNNABLE_PROVIDERS)}")
    tenant_id = get_tenant_id()
    result = await cloud_checks_service.run_checks(account_id, provider, tenant_id)
    if result.get("error"):
        status_code = 404 if result["error"] == "Cloud account not found" else 400
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result

@mcp.tool()
async def list_findings(severity: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """List security findings with optional severity filter"""
    db = get_database()
    tenant_id = get_tenant_id()
    if severity is not None and (not isinstance(severity, str) or not severity):
        raise HTTPException(status_code=400, detail="severity must be a non-empty string")
    raw_limit = limit if limit is not None else 20
    if not isinstance(raw_limit, int) or isinstance(raw_limit, bool) or raw_limit < 1:
        raise HTTPException(status_code=400, detail="limit must be a positive integer")
    limit = min(raw_limit, 100)
    query = {"tenantId": tenant_id}
    if severity:
        query["severity"] = severity
    findings = await db.cloud_findings.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=limit)
    return findings

@mcp.tool()
async def get_compliance_score(framework: str) -> Dict[str, Any]:
    """Get overall compliance score for a framework"""
    db = get_database()
    tenant_id = get_tenant_id()
    fw = await db._db.compliance_frameworks.find_one({"id": framework}, {"_id": 0})
    if not fw:
        raise HTTPException(status_code=404, detail=f"Unknown framework '{framework}'")
    control_ids = [c.get("id") for c in fw.get("controls", []) if c.get("id")]
    if not control_ids:
        return {"score": 0, "passing": 0, "total": 0, "framework": framework}
    results = await db.asset_compliance.find(
        {"tenantId": tenant_id, "controlId": {"$in": control_ids}}, {"_id": 0}
    ).to_list(length=1000)
    passing = sum(1 for r in results if r.get("status") == "Compliant")
    total = len(results) or 1
    return {"score": round(passing / total * 100), "passing": passing, "total": total, "framework": framework}

@mcp.tool()
async def list_evidence(
    control_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List evidence items for the current tenant."""
    return []

@mcp.tool()
async def get_compliance_control(control_id: str) -> Dict[str, Any]:
    """Get a specific compliance control by ID."""
    return {}

@mcp.tool()
async def get_risk_register() -> List[Dict[str, Any]]:
    """Get the risk register for the current tenant."""
    return []

@mcp.tool()
async def get_attack_paths() -> List[Dict[str, Any]]:
    """Get attack paths for the current tenant."""
    return []

# ─── Resource Definitions ────────────────────────────────────────────────────
@mcp.resource("tenant://{tenant_id}/compliance-controls")
async def get_tenant_compliance_controls(tenant_id: str) -> str:
    """Get compliance controls for a specific tenant as JSON."""
    import json
    from database import mongodb
    controls = await mongodb.db.compliance_controls.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).to_list(length=1000)
    return json.dumps(controls, default=str)

@mcp.resource("tenant://{tenant_id}/evidence")
async def get_tenant_evidence(tenant_id: str) -> str:
    """Get evidence for a specific tenant as JSON."""
    import json
    from database import mongodb
    evidence = await mongodb.db.evidence.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).to_list(length=1000)
    return json.dumps(evidence, default=str)

@mcp.resource("tenant://{tenant_id}/risks")
async def get_tenant_risks(tenant_id: str) -> str:
    """Get risks for a specific tenant as JSON."""
    import json
    from database import mongodb
    risks = await mongodb.db.risks.find(
        {"tenantId": tenant_id},
        {"_id": 0}
    ).to_list(length=1000)
    return json.dumps(risks, default=str)

# ─── SSE Transport Setup ──────────────────────────────────────────────────────
sse_transport = SseServerTransport("/api/mcp/sse")

async def handle_sse(request):
    """Handle SSE connections for MCP."""
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await mcp._mcp_server.run(
            read_stream,
            write_stream,
            mcp._mcp_server.create_initialization_options(),
        )