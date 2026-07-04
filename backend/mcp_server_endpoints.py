"""MCP Protocol Server — exposes compliance data as MCP tools for AI assistants."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from database import get_database
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mcp", tags=["MCP Protocol"])

MCP_TOOLS = {
    "list_frameworks": {
        "description": "List all compliance frameworks available for this tenant",
        "params": {},
    },
    "get_control_status": {
        "description": "Get compliance status for a specific control across assets",
        "params": {"control_id": "string"},
    },
    "run_cloud_check": {
        "description": "Run a cloud security check against a provider account",
        "params": {"provider": "string (aws/azure/gcp)", "account_id": "string"},
    },
    "list_findings": {
        "description": "List security findings with optional severity filter",
        "params": {"severity": "string (critical/high/medium/low, optional)", "limit": "integer (optional, default 20)"},
    },
    "get_compliance_score": {
        "description": "Get overall compliance score for a framework",
        "params": {"framework": "string (soc2/iso27001/pci_dss/etc)"},
    },
}


@router.get("/tools")
async def list_tools(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    return {
        "protocol": "mcp-1.0",
        "tools": [{"name": k, **v} for k, v in MCP_TOOLS.items()],
    }


@router.post("/execute/{tool_name}")
async def execute_tool(tool_name: str, params: dict = Body(default={}), current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    if tool_name not in MCP_TOOLS:
        raise HTTPException(status_code=404, detail=f"Unknown tool '{tool_name}'")
    db = get_database()
    tenant_id = get_tenant_id()

    if tool_name == "list_frameworks":
        # Global/seeded frameworks carry no tenant field at all; tenant-owned
        # custom frameworks are stamped with snake_case tenant_id (see
        # compliance_framework_mgmt_endpoints.py's /api/compliance route).
        frameworks = await db._db.compliance_frameworks.find(
            {"$or": [
                {"tenant_id": {"$exists": False}},
                {"tenant_id": ""},
                {"tenant_id": None},
                {"tenant_id": tenant_id},
            ]}, {"_id": 0}
        ).to_list(length=100)
        return {"tool": tool_name, "result": [{"id": f.get("id"), "name": f.get("name")} for f in frameworks]}

    if tool_name == "get_control_status":
        control_id = params.get("control_id")
        if not isinstance(control_id, str) or not control_id:
            raise HTTPException(status_code=400, detail="control_id must be a non-empty string")
        results = await db.asset_compliance.find({"controlId": control_id, "tenantId": tenant_id}, {"_id": 0}).to_list(length=200)
        return {"tool": tool_name, "result": {"control_id": control_id, "assets": len(results), "statuses": sorted({r.get("status") for r in results})}}

    if tool_name == "run_cloud_check":
        account_id = params.get("account_id", "")
        provider = params.get("provider", "")
        if not isinstance(account_id, str) or not account_id:
            raise HTTPException(status_code=400, detail="account_id must be a non-empty string")
        if provider not in ("aws", "azure", "gcp"):
            raise HTTPException(status_code=400, detail="provider must be aws, azure, or gcp")
        from cloud_checks_service import cloud_checks_service
        result = await cloud_checks_service.run_checks(account_id, provider, tenant_id)
        return {"tool": tool_name, "result": result}

    if tool_name == "list_findings":
        severity = params.get("severity")
        if severity is not None and (not isinstance(severity, str) or not severity):
            raise HTTPException(status_code=400, detail="severity must be a non-empty string")
        raw_limit = params.get("limit", 20)
        if not isinstance(raw_limit, int) or isinstance(raw_limit, bool) or raw_limit < 1:
            raise HTTPException(status_code=400, detail="limit must be a positive integer")
        limit = min(raw_limit, 100)
        query = {"tenantId": tenant_id}
        if severity:
            query["severity"] = severity
        findings = await db.cloud_findings.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=limit)
        return {"tool": tool_name, "result": findings}

    if tool_name == "get_compliance_score":
        framework = params.get("framework", "soc2")
        if not isinstance(framework, str) or not framework:
            raise HTTPException(status_code=400, detail="framework must be a non-empty string")
        fw = await db._db.compliance_frameworks.find_one({"id": framework}, {"_id": 0})
        if not fw:
            raise HTTPException(status_code=404, detail=f"Unknown framework '{framework}'")
        control_ids = [c.get("id") for c in fw.get("controls", []) if c.get("id")]
        if not control_ids:
            return {"tool": tool_name, "result": {"score": 0, "passing": 0, "total": 0, "framework": framework}}
        results = await db.asset_compliance.find(
            {"tenantId": tenant_id, "controlId": {"$in": control_ids}}, {"_id": 0}
        ).to_list(length=1000)
        passing = sum(1 for r in results if r.get("status") == "Compliant")
        total = len(results) or 1
        return {"tool": tool_name, "result": {"score": round(passing / total * 100), "passing": passing, "total": total, "framework": framework}}

    raise HTTPException(status_code=500, detail="Tool execution failed")
