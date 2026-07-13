# Phase 37: Spec-Compliant MCP Server - Plan

**Goal:** Replace the current REST-shaped `/api/mcp` endpoint with a spec-compliant MCP server using the official Python SDK so tools are usable by actual MCP clients (Claude Desktop, etc.).

**Requirements:** MCP-01, MCP-02

**Waves:** 3
- **Wave 1:** Infrastructure and Protocol Implementation.
- **Wave 2:** Tool Catalog Migration and Exposition.
- **Wave 3:** Testing and Verification.

---
## Plan 37-01: MCP Infrastructure and Protocol

**Goal:** Implement a spec-compliant MCP server with stdio and SSE transports.

**Tasks:**

1.  **Dependencies:**
    -   Add `mcp` (official Python SDK) to `backend/requirements.txt`.
    -   Check PyPI for `mcp` package version (likely `mcp>=1.0.0`).

2.  **Server Implementation (`backend/mcp_server.py`):**
    -   Create `backend/mcp_server.py` using the official `mcp` SDK.
    -   Implement `FastMCP` or equivalent server instance.
    -   Support **stdio transport** (for CLI/Claude Desktop) and **SSE/HTTP transport** (for web clients).
    -   Mount the SSE/HTTP transport under a new route (e.g., `/api/mcp/sse` or alongside existing REST at `/api/mcp`).

3.  **Lifecycle:**
    -   Initialize the MCP server in `backend/app.py` on startup.
    -   Ensure graceful shutdown.

**Verification:**
-   MCP server starts and accepts connections via stdio.
-   SSE endpoint is reachable.

---
## Plan 37-02: Tool Catalog Migration

**Goal:** Migrate all existing tool-catalog entries from the old REST endpoint to the new MCP server.

**Tasks:**

1.  **Inventory Tools:**
    -   Read `backend/mcp_server_endpoints.py` to inventory all current tool definitions.

2.  **Register Tools:**
    -   For each tool, register it on the `FastMCP` instance using `@mcp.tool()` decorator or equivalent API.
    -   Ensure tool signatures (input schemas) match the existing catalog exactly.
    -   Map tool implementations to the existing service functions (do not rewrite logic, just wire through).

3.  **Resource/Template Support (Optional):**
    -   If the old endpoint exposed resources or prompts, add them as MCP resources/templates.

**Verification:**
-   All existing tools appear in `mcp list_tools` (or equivalent introspection).
-   Tool calls produce identical results to the old REST endpoint.

---
## Plan 37-03: Testing and Verification

**Goal:** Verify spec compliance and backward compatibility.

**Tasks:**

1.  **Integration Tests:**
    -   Create `backend/tests/test_mcp_server.py`.
    -   Test stdio transport: initialize, list tools, call a tool.
    -   Test SSE/HTTP transport: initialize, list tools, call a tool.

2.  **Compatibility Tests:**
    -   Run a real MCP client (e.g., `mcp` CLI or a simple script) against the server.
    -   Verify tool schemas match the old REST catalog.

3.  **Human Verification:**
    -   Connect a real MCP client (Claude Desktop config pointing to the stdio server).
    -   Invoke a tool and verify response.

**Verification:**
-   All tests pass.
-   Real MCP client works end-to-end.
-   No regression in tool behavior.