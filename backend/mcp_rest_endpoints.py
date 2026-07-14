"""REST bridge for MCP tools — POST /api/mcp/execute/{tool_name}.

Phase 37 exposes the tool logic through a standalone FastMCP server (stdio/SSE),
which browser clients can't call directly. This thin bridge lets the in-app
ApiExtensions dashboard invoke the same tool coroutines over authenticated HTTP,
reusing the exact implementations from mcp_server (no logic duplication).
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Any, Dict

from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import set_tenant_id
import mcp_server

router = APIRouter(prefix="/api/mcp", tags=["MCP"])

# Only tools the UI is allowed to invoke over REST. Maps tool name → coroutine.
_ALLOWED_TOOLS = {
    "list_frameworks": mcp_server.list_frameworks,
    "get_control_status": mcp_server.get_control_status,
    "run_cloud_check": mcp_server.run_cloud_check,
    "list_findings": mcp_server.list_findings,
    "get_compliance_score": mcp_server.get_compliance_score,
}


@router.post("/execute/{tool_name}")
async def execute_mcp_tool(
    tool_name: str,
    params: Dict[str, Any] = Body(default={}),
    current_user: TokenData = Depends(get_current_user),
):
    """Execute a whitelisted MCP tool with JSON params, scoped to the caller's tenant."""
    func = _ALLOWED_TOOLS.get(tool_name)
    if func is None:
        raise HTTPException(status_code=404, detail=f"Unknown or unsupported tool '{tool_name}'")

    # MCP tool coroutines read tenant from the context var, not an argument.
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id and getattr(current_user, "role", "") not in ("Super Admin", "super_admin", "platform-admin"):
        raise HTTPException(status_code=403, detail="Tenant context required")
    set_tenant_id(tenant_id)

    if not isinstance(params, dict):
        raise HTTPException(status_code=422, detail="params must be a JSON object")

    try:
        return await func(**params)
    except HTTPException:
        raise
    except TypeError as exc:
        # Bad/missing params for the tool signature.
        raise HTTPException(status_code=422, detail=f"Invalid parameters for '{tool_name}': {exc}")
