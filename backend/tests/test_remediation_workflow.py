"""
Remediation workflow test scaffold — RED until 04-01/04-02 land.

Requirements covered:
  REM-01 — create_task persists a new remediation task with correct fields
  REM-02 — list_tasks filters by tenant and status
  REM-03 — resolving a task dispatches a 'Run Compliance Scan' agent instruction
  REM-04 — broadcast_remediation_update emits a 'remediation_update' Socket.IO event

All tests in this file are expected to FAIL (error on import or assertion) until
Wave 1 (04-01) creates compliance_remediation_service and Wave 2 (04-02) wires
the endpoints.  REM-04 is the exception — it passes once Task 3 of 04-00 adds
broadcast_remediation_update to websocket_manager.py.
"""
import asyncio
import os
import sys

# Ensure backend/ is on sys.path so websocket_manager and the not-yet-created
# compliance_remediation_service can be imported.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Shared mock-DB factory (mirrors pattern from test_rust_heartbeat_parity.py)
# ---------------------------------------------------------------------------
def _mock_db():
    from unittest.mock import AsyncMock, MagicMock

    db = MagicMock()

    # compliance_remediation_tasks collection
    tasks_col = MagicMock()
    tasks_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-inserted-id"))
    tasks_col.find = MagicMock()
    tasks_col.find_one = AsyncMock(return_value=None)
    tasks_col.update_one = AsyncMock()
    db.compliance_remediation_tasks = tasks_col

    # assets collection
    assets_col = MagicMock()
    assets_col.find_one = AsyncMock(return_value=None)
    db.assets = assets_col

    # agents collection
    agents_col = MagicMock()
    agents_col.find_one = AsyncMock(return_value=None)
    db.agents = agents_col

    # agent_instructions collection
    instructions_col = MagicMock()
    instructions_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-instr-id"))
    db.agent_instructions = instructions_col

    return db


# ---------------------------------------------------------------------------
# REM-01: create_task persists document with correct fields
# ---------------------------------------------------------------------------
def test_rem01_create_task_persists():
    """
    REM-01: compliance_remediation_service.create_task inserts a doc with:
      - an id (non-empty string)
      - status == 'open'
      - tenantId == 't1'
      - title matching the input
    Expected to FAIL (ImportError) until Wave 1 creates compliance_remediation_service.
    """
    import compliance_remediation_service  # noqa: PLC0415 — intentional late import for RED

    db = _mock_db()
    tenant_filter = {"tenantId": "t1"}
    task_data = {
        "title": "Enable MFA for admin accounts",
        "control_id": "CC6.1",
        "asset_id": "asset-001",
        "framework_id": "soc2",
        "priority": "high",
        "due_date": "2026-07-01",
        "description": "Multi-factor authentication must be enabled for all admin accounts.",
    }

    result = asyncio.run(
        compliance_remediation_service.create_task(
            db, task_data, tenant_filter=tenant_filter, created_by="u@example.com"
        )
    )

    assert result is not None, "create_task returned None"
    assert result.get("id"), "Task doc missing 'id' field"
    assert result.get("status") == "open", f"Expected status='open', got {result.get('status')!r}"
    assert result.get("tenantId") == "t1", f"Expected tenantId='t1', got {result.get('tenantId')!r}"
    assert result.get("title") == task_data["title"], (
        f"Title mismatch: {result.get('title')!r} != {task_data['title']!r}"
    )
    # Verify insert_one was awaited at all
    db.compliance_remediation_tasks.insert_one.assert_awaited()


# ---------------------------------------------------------------------------
# REM-02: list_tasks passes status and tenant filter to Motor query
# ---------------------------------------------------------------------------
def test_rem02_list_tasks_filters_by_status():
    """
    REM-02: list_tasks calls db.compliance_remediation_tasks.find(query) where
      query includes both status='open' and the tenant filter {'tenantId': 't1'}.
    Expected to FAIL (ImportError) until Wave 1 creates compliance_remediation_service.
    """
    import compliance_remediation_service  # noqa: PLC0415

    from unittest.mock import MagicMock, AsyncMock

    db = _mock_db()
    tenant_filter = {"tenantId": "t1"}

    # find() returns a cursor-like; make it async-iterable or return a list
    cursor_mock = MagicMock()
    cursor_mock.__aiter__ = MagicMock(return_value=iter([]))
    # Support both cursor.to_list() pattern and async-for pattern
    cursor_mock.to_list = AsyncMock(return_value=[])
    db.compliance_remediation_tasks.find = MagicMock(return_value=cursor_mock)

    asyncio.run(
        compliance_remediation_service.list_tasks(db, tenant_filter, status="open")
    )

    # The find() must have been called with a filter containing status and tenantId
    db.compliance_remediation_tasks.find.assert_called()
    call_args = db.compliance_remediation_tasks.find.call_args
    # Positional first arg or keyword 'filter'
    query = (call_args[0][0] if call_args[0] else None) or call_args[1].get("filter", {})
    assert query.get("status") == "open", (
        f"find() query missing status='open': {query}"
    )
    assert query.get("tenantId") == "t1", (
        f"find() query missing tenantId='t1': {query}"
    )


# ---------------------------------------------------------------------------
# REM-03: resolving a task dispatches "Run Compliance Scan" instruction
# ---------------------------------------------------------------------------
def test_rem03_resolve_dispatches_rescan():
    """
    REM-03: update_task(db, task_id, {'status':'resolved'}, tenant_filter) where the
    stored task has asset_id resolving (via assets.find_one) to an agentId must
    insert a doc into db.agent_instructions with instruction == 'Run Compliance Scan'
    and control_id matching the task's control_id.
    Expected to FAIL (ImportError) until Wave 1 creates compliance_remediation_service.
    """
    import compliance_remediation_service  # noqa: PLC0415

    db = _mock_db()
    tenant_filter = {"tenantId": "t1"}
    task_id = "task-abc-123"
    control_id = "CC6.1"

    # Simulate the stored task that update_task will load
    db.compliance_remediation_tasks.find_one = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
        return_value={
            "id": task_id,
            "tenantId": "t1",
            "asset_id": "asset-001",
            "control_id": control_id,
            "status": "open",
        }
    )

    # Simulate assets.find_one returning an asset with agentId
    db.assets.find_one = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
        return_value={"id": "asset-001", "agentId": "agent-xyz"}
    )

    asyncio.run(
        compliance_remediation_service.update_task(
            db, task_id, {"status": "resolved"}, tenant_filter
        )
    )

    # agent_instructions.insert_one must have been awaited
    db.agent_instructions.insert_one.assert_awaited()

    # Inspect the inserted document
    call_args = db.agent_instructions.insert_one.call_args
    inserted_doc = call_args[0][0] if call_args[0] else call_args[1].get("document", {})
    assert inserted_doc.get("instruction") == "Run Compliance Scan", (
        f"Expected instruction='Run Compliance Scan', got {inserted_doc.get('instruction')!r}"
    )
    assert inserted_doc.get("control_id") == control_id, (
        f"Expected control_id={control_id!r}, got {inserted_doc.get('control_id')!r}"
    )


# ---------------------------------------------------------------------------
# REM-04: broadcast_remediation_update emits 'remediation_update' event
# ---------------------------------------------------------------------------
def test_rem04_broadcast_remediation_update_emits_event():
    """
    REM-04: broadcast_remediation_update('t1', payload) emits a 'remediation_update'
    Socket.IO event to each sid in connected_clients['t1'].
    This test passes once Task 3 of 04-00 adds the function to websocket_manager.py.
    """
    from unittest.mock import AsyncMock, patch
    import websocket_manager

    # Monkeypatch connected_clients so we control which sids are "connected"
    mock_clients = {"t1": {"sid1"}}
    mock_emit = AsyncMock()

    with patch.object(websocket_manager, "connected_clients", mock_clients):
        with patch.object(websocket_manager.sio, "emit", mock_emit):
            asyncio.run(
                websocket_manager.broadcast_remediation_update(
                    "t1", {"task_id": "x", "status": "resolved"}
                )
            )

    mock_emit.assert_awaited()
    first_call_args = mock_emit.call_args_list[0]
    event_name = first_call_args[0][0] if first_call_args[0] else first_call_args[1].get("event")
    assert event_name == "remediation_update", (
        f"Expected first emit arg 'remediation_update', got {event_name!r}"
    )
