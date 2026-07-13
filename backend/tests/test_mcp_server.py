"""Phase 37 tests — spec-compliant MCP server (FastMCP).

Verifies against the real `mcp_server.mcp` FastMCP instance:
- tool registration (names exposed over the MCP protocol)
- resource template registration
- SSE transport wiring
- tool execution through the protocol layer with mocked db/tenant
- tool input validation and error mapping
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import mcp_server as srv


EXPECTED_TOOLS = {
    "list_frameworks",
    "get_control_status",
    "run_cloud_check",
    "list_findings",
    "get_compliance_score",
    "list_evidence",
    "get_compliance_control",
    "get_risk_register",
    "get_attack_paths",
}

EXPECTED_RESOURCE_TEMPLATES = {
    "tenant://{tenant_id}/compliance-controls",
    "tenant://{tenant_id}/evidence",
    "tenant://{tenant_id}/risks",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cursor(docs):
    """Motor-style cursor: find()/sort() are sync, to_list() is awaited."""
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    cursor.sort = MagicMock(return_value=cursor)
    return cursor


def _tenant_patch(tenant_id="test-tenant"):
    return patch("mcp_server.get_tenant_id", MagicMock(return_value=tenant_id))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

async def test_mcp_tools_registered():
    tools = await srv.mcp.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS


async def test_mcp_resource_templates_registered():
    templates = await srv.mcp.list_resource_templates()
    assert {t.uriTemplate for t in templates} == EXPECTED_RESOURCE_TEMPLATES


def test_sse_transport_configured():
    assert srv.sse_transport is not None
    assert callable(srv.handle_sse)


# ---------------------------------------------------------------------------
# Tool execution (through the MCP protocol layer)
# ---------------------------------------------------------------------------

async def test_call_tool_get_control_status():
    db = MagicMock()
    db.asset_compliance.find = MagicMock(return_value=_make_cursor(
        [{"status": "Compliant"}, {"status": "Non-Compliant"}]
    ))
    with patch("mcp_server.get_database", MagicMock(return_value=db)), _tenant_patch():
        content, structured = await srv.mcp.call_tool("get_control_status", {"control_id": "AC-1"})

    assert json.loads(content[0].text) == structured["result"]
    result = structured["result"]
    assert result["control_id"] == "AC-1"
    assert result["assets"] == 2
    assert result["statuses"] == ["Compliant", "Non-Compliant"]


async def test_call_tool_list_frameworks():
    raw = MagicMock()
    raw.compliance_frameworks.find = MagicMock(return_value=_make_cursor(
        [{"id": "soc2", "name": "SOC 2"}, {"id": "iso27001", "name": "ISO 27001"}]
    ))
    db = MagicMock()
    db._db = raw
    with patch("mcp_server.get_database", MagicMock(return_value=db)), _tenant_patch():
        _, structured = await srv.mcp.call_tool("list_frameworks", {})

    names = {f["id"] for f in structured["result"]}
    assert names == {"soc2", "iso27001"}


async def test_get_compliance_score():
    raw = MagicMock()
    raw.compliance_frameworks.find_one = AsyncMock(return_value={
        "id": "soc2", "controls": [{"id": "AC-1"}, {"id": "AC-2"}],
    })
    db = MagicMock()
    db._db = raw
    db.asset_compliance.find = MagicMock(return_value=_make_cursor(
        [{"status": "Compliant"}, {"status": "Non-Compliant"}]
    ))
    with patch("mcp_server.get_database", MagicMock(return_value=db)), _tenant_patch():
        result = await srv.get_compliance_score("soc2")

    assert result == {"score": 50, "passing": 1, "total": 2, "framework": "soc2"}


async def test_run_cloud_check_delegates_to_service():
    checks = AsyncMock()
    checks.run_checks = AsyncMock(return_value={"status": "completed", "ran": 3})
    with patch("mcp_server.cloud_checks_service", checks), _tenant_patch():
        result = await srv.run_cloud_check("aws", "12345")

    assert result["status"] == "completed"
    checks.run_checks.assert_awaited_once_with("12345", "aws", "test-tenant")


async def test_list_findings_filters_and_limits():
    db = MagicMock()
    cursor = _make_cursor([{"id": "finding1", "severity": "high"}])
    db.cloud_findings.find = MagicMock(return_value=cursor)
    with patch("mcp_server.get_database", MagicMock(return_value=db)), _tenant_patch():
        findings = await srv.list_findings(severity="high", limit=10)

    assert findings == [{"id": "finding1", "severity": "high"}]
    query = db.cloud_findings.find.call_args.args[0]
    assert query == {"tenantId": "test-tenant", "severity": "high"}


# ---------------------------------------------------------------------------
# Validation and error mapping
# ---------------------------------------------------------------------------

async def test_run_cloud_check_invalid_provider():
    with _tenant_patch():
        with pytest.raises(HTTPException) as exc:
            await srv.run_cloud_check("invalid", "12345")
    assert exc.value.status_code == 400
    assert "provider must be" in exc.value.detail


async def test_run_cloud_check_account_not_found():
    checks = AsyncMock()
    checks.run_checks = AsyncMock(return_value={"error": "Cloud account not found"})
    with patch("mcp_server.cloud_checks_service", checks), _tenant_patch():
        with pytest.raises(HTTPException) as exc:
            await srv.run_cloud_check("aws", "nonexistent")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Cloud account not found"


async def test_list_findings_invalid_limit():
    db = MagicMock()
    db.cloud_findings.find = MagicMock(return_value=_make_cursor([]))
    with patch("mcp_server.get_database", MagicMock(return_value=db)), _tenant_patch():
        with pytest.raises(HTTPException) as exc:
            await srv.list_findings(limit=0)
    assert exc.value.status_code == 400
    assert "limit must be a positive integer" in exc.value.detail


async def test_get_compliance_score_unknown_framework():
    raw = MagicMock()
    raw.compliance_frameworks.find_one = AsyncMock(return_value=None)
    db = MagicMock()
    db._db = raw
    with patch("mcp_server.get_database", MagicMock(return_value=db)), _tenant_patch():
        with pytest.raises(HTTPException) as exc:
            await srv.get_compliance_score("unknown_fw")
    assert exc.value.status_code == 404
    assert "Unknown framework" in exc.value.detail
