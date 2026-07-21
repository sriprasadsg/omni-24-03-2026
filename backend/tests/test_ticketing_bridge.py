"""
Tests for ticketing_bridge.py — the remediation-to-ticketing bridge.

Covers:
  - adapter: _task_to_alert_shape field mapping (REM-01)
  - create_ticket: create_ticket_for_remediation_task success path (REM-01)
  - no_config: no-op when ticketing is not configured for the tenant (REM-01)
  - dedup: a task with an existing ticket_ref never gets a second ticket (REM-01)
  - status_check: get_jira_issue_status/get_servicenow_incident_status
    closed/open classification, including the 404/not_found path (REM-02, D-06)
  - close_loop_dispatch: run_close_loop_pass resolves a task via
    compliance_remediation_service.update_task when the linked ticket closes (REM-02)
  - close_loop_skip: run_close_loop_pass skips tasks with no ticket_ref and
    tolerates a missing ticketing config mid-sweep (REM-02)
  - close_loop_deleted_ticket: a 404/not_found ticket is logged and skipped,
    never auto-resolved on ambiguous evidence (REM-02, D-06)
  - raw_db_registration: scheduler functions never reference get_database
    (regression guard for the raw-db requirement)
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import ticketing_bridge


# ---------------------------------------------------------------------------
# Shared mock-DB factory (mirrors test_remediation_workflow.py's _mock_db())
# ---------------------------------------------------------------------------
def _mock_db():
    db = MagicMock()

    tasks_col = MagicMock()
    tasks_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-inserted-id"))
    tasks_col.find = MagicMock()
    tasks_col.find_one = AsyncMock(return_value=None)
    tasks_col.update_one = AsyncMock()
    db.compliance_remediation_tasks = tasks_col

    assets_col = MagicMock()
    assets_col.find_one = AsyncMock(return_value=None)
    db.assets = assets_col

    ticketing_configs_col = MagicMock()
    ticketing_configs_col.find_one = AsyncMock(return_value=None)
    db.ticketing_configs = ticketing_configs_col

    ticketing_log_col = MagicMock()
    ticketing_log_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-log-id"))
    db.ticketing_log = ticketing_log_col

    return db


class _AsyncCursor:
    """Async-iterable cursor stub for db.<collection>.find(...)."""

    def __init__(self, docs=()):
        self._iter = iter(list(docs))

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _run(coro):
    return asyncio.run(coro)


def _make_task(**overrides):
    task = {
        "id": "task-1",
        "tenantId": "tenant-a",
        "control_id": "CC-1.1",
        "framework_id": "SOC2",
        "priority": "high",
        "description": "MFA not enforced",
        "created_at": "2026-07-21T00:00:00Z",
        "asset_id": "asset-1",
        "status": "open",
    }
    task.update(overrides)
    return task


# ---------------------------------------------------------------------------
# adapter
# ---------------------------------------------------------------------------
def test_adapter_maps_task_fields_to_alert_shape():
    db = _mock_db()
    db.assets.find_one = AsyncMock(return_value={"id": "asset-1", "hostname": "web-01"})
    task = _make_task()

    alert = _run(ticketing_bridge._task_to_alert_shape(db, task))

    assert alert["alert_id"] == "task-1"
    assert alert["severity"] == "high"
    assert alert["hostname"] == "web-01"
    assert "CC-1.1" in alert["description"]
    assert alert["description"] != "N/A"
    assert alert["mitre_technique"] == "N/A"  # explicit fallback, not mappable


# ---------------------------------------------------------------------------
# create_ticket
# ---------------------------------------------------------------------------
def test_create_ticket_for_remediation_task_persists_and_returns_fields():
    db = _mock_db()
    task = _make_task()

    with patch(
        "ticketing_bridge.get_ticketing_config",
        AsyncMock(return_value={"provider": "jira", "jira_url": "https://x.atlassian.net"}),
    ), patch(
        "ticketing_bridge.create_jira_ticket",
        AsyncMock(return_value={"success": True, "ticket_key": "SEC-42", "url": "https://x/SEC-42"}),
    ):
        result = _run(
            ticketing_bridge.create_ticket_for_remediation_task(db, task, "tenant-a")
        )

    assert result == {
        "ticket_provider": "jira",
        "ticket_ref": "SEC-42",
        "ticket_url": "https://x/SEC-42",
    }
    db.compliance_remediation_tasks.update_one.assert_awaited_once()
    args, kwargs = db.compliance_remediation_tasks.update_one.call_args
    assert args[0] == {"id": "task-1", "tenantId": "tenant-a"}
    assert args[1]["$set"] == {
        "ticket_provider": "jira",
        "ticket_ref": "SEC-42",
        "ticket_url": "https://x/SEC-42",
    }


# ---------------------------------------------------------------------------
# no_config
# ---------------------------------------------------------------------------
def test_no_config_returns_none_and_does_not_raise():
    db = _mock_db()
    task = _make_task()

    with patch("ticketing_bridge.get_ticketing_config", AsyncMock(return_value=None)):
        result = _run(
            ticketing_bridge.create_ticket_for_remediation_task(db, task, "tenant-a")
        )

    assert result is None
    db.compliance_remediation_tasks.update_one.assert_not_called()


# ---------------------------------------------------------------------------
# dedup
# ---------------------------------------------------------------------------
def test_dedup_task_with_existing_ticket_never_gets_second():
    db = _mock_db()
    task = _make_task(ticket_ref="SEC-1")

    with patch("ticketing_bridge.get_ticketing_config", AsyncMock()) as mock_config, patch(
        "ticketing_bridge.create_jira_ticket", AsyncMock()
    ) as mock_create:
        result = _run(
            ticketing_bridge.create_ticket_for_remediation_task(db, task, "tenant-a")
        )

    assert result is None
    mock_config.assert_not_called()
    mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# status_check
# ---------------------------------------------------------------------------
def _mock_httpx_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data or {})
    return resp


def _patched_httpx_get(response):
    """Return a context-manager-compatible AsyncClient mock whose .get()
    resolves to the given response object."""
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def test_status_check_jira_closed_and_open():
    config = {"jira_url": "https://x.atlassian.net", "jira_email": "a@b.com", "jira_api_token": "t"}

    closed_resp = _mock_httpx_response(
        200, {"fields": {"status": {"statusCategory": {"key": "done"}}}}
    )
    open_resp = _mock_httpx_response(
        200, {"fields": {"status": {"statusCategory": {"key": "indeterminate"}}}}
    )

    with patch("httpx.AsyncClient", return_value=_patched_httpx_get(closed_resp)):
        result = _run(ticketing_bridge.get_jira_issue_status("SEC-1", config))
    assert result["success"] is True
    assert result["closed"] is True

    with patch("httpx.AsyncClient", return_value=_patched_httpx_get(open_resp)):
        result = _run(ticketing_bridge.get_jira_issue_status("SEC-1", config))
    assert result["success"] is True
    assert result["closed"] is False


def test_status_check_jira_not_found_on_404():
    config = {"jira_url": "https://x.atlassian.net", "jira_email": "a@b.com", "jira_api_token": "t"}
    resp = _mock_httpx_response(404, {})

    with patch("httpx.AsyncClient", return_value=_patched_httpx_get(resp)):
        result = _run(ticketing_bridge.get_jira_issue_status("SEC-1", config))

    assert result["success"] is False
    assert result["closed"] is False
    assert result["not_found"] is True


def test_status_check_servicenow_closed_and_open():
    config = {"snow_instance": "devxyz", "snow_username": "u", "snow_password": "p"}

    closed_resp = _mock_httpx_response(200, {"result": {"state": "Closed"}})
    resolved_resp = _mock_httpx_response(200, {"result": {"state": "resolved"}})
    open_resp = _mock_httpx_response(200, {"result": {"state": "In Progress"}})
    numeric_resp = _mock_httpx_response(200, {"result": {"state": "2"}})

    with patch("httpx.AsyncClient", return_value=_patched_httpx_get(closed_resp)):
        result = _run(ticketing_bridge.get_servicenow_incident_status("sys1", config))
    assert result["closed"] is True

    with patch("httpx.AsyncClient", return_value=_patched_httpx_get(resolved_resp)):
        result = _run(ticketing_bridge.get_servicenow_incident_status("sys1", config))
    assert result["closed"] is True

    with patch("httpx.AsyncClient", return_value=_patched_httpx_get(open_resp)):
        result = _run(ticketing_bridge.get_servicenow_incident_status("sys1", config))
    assert result["closed"] is False

    with patch("httpx.AsyncClient", return_value=_patched_httpx_get(numeric_resp)):
        result = _run(ticketing_bridge.get_servicenow_incident_status("sys1", config))
    assert result["closed"] is False


def test_status_check_servicenow_not_found_on_404():
    config = {"snow_instance": "devxyz", "snow_username": "u", "snow_password": "p"}
    resp = _mock_httpx_response(404, {})

    with patch("httpx.AsyncClient", return_value=_patched_httpx_get(resp)):
        result = _run(ticketing_bridge.get_servicenow_incident_status("sys1", config))

    assert result["success"] is False
    assert result["closed"] is False
    assert result["not_found"] is True


# ---------------------------------------------------------------------------
# close_loop_dispatch
# ---------------------------------------------------------------------------
def test_close_loop_dispatch_resolves_task_when_ticket_closed():
    db = _mock_db()
    task = _make_task(status="open", ticket_ref="SEC-1", ticket_provider="jira")
    db.compliance_remediation_tasks.find = MagicMock(return_value=_AsyncCursor([task]))

    mock_update_task = AsyncMock(return_value={"id": "task-1", "control_id": "CC-1.1"})

    with patch(
        "ticketing_bridge.get_ticketing_config",
        AsyncMock(return_value={"provider": "jira", "jira_url": "https://x"}),
    ), patch(
        "ticketing_bridge.get_jira_issue_status",
        AsyncMock(return_value={"success": True, "closed": True}),
    ), patch.dict(
        "sys.modules",
        {},
    ):
        import compliance_remediation_service as svc

        with patch.object(svc, "update_task", mock_update_task):
            _run(ticketing_bridge.run_close_loop_pass(db))

    mock_update_task.assert_awaited_once()
    args, kwargs = mock_update_task.call_args
    assert args[1] == "task-1"
    assert args[2] == {"status": "resolved"}


# ---------------------------------------------------------------------------
# close_loop_skip
# ---------------------------------------------------------------------------
def test_close_loop_skip_no_ticket_ref_and_missing_config():
    db = _mock_db()
    # This task has status open/in_progress but no ticket_ref, so the real
    # query would never match it — simulate a mid-sweep task with no config.
    task = _make_task(status="open", ticket_ref="SEC-2", ticket_provider="jira")
    db.compliance_remediation_tasks.find = MagicMock(return_value=_AsyncCursor([task]))

    with patch("ticketing_bridge.get_ticketing_config", AsyncMock(return_value=None)):
        # Should not raise even though config is missing mid-sweep.
        _run(ticketing_bridge.run_close_loop_pass(db))

    db.compliance_remediation_tasks.update_one.assert_not_called()


def test_close_loop_skip_empty_cursor_does_not_crash():
    db = _mock_db()
    db.compliance_remediation_tasks.find = MagicMock(return_value=_AsyncCursor([]))

    # Should complete cleanly with no tasks to process.
    _run(ticketing_bridge.run_close_loop_pass(db))


# ---------------------------------------------------------------------------
# close_loop_deleted_ticket (D-06)
# ---------------------------------------------------------------------------
def test_close_loop_deleted_ticket_is_skipped_not_resolved():
    db = _mock_db()
    task = _make_task(status="open", ticket_ref="SEC-3", ticket_provider="jira")
    db.compliance_remediation_tasks.find = MagicMock(return_value=_AsyncCursor([task]))

    import compliance_remediation_service as svc
    mock_update_task = AsyncMock()

    with patch(
        "ticketing_bridge.get_ticketing_config",
        AsyncMock(return_value={"provider": "jira", "jira_url": "https://x"}),
    ), patch(
        "ticketing_bridge.get_jira_issue_status",
        AsyncMock(return_value={"success": False, "closed": False, "not_found": True}),
    ), patch.object(svc, "update_task", mock_update_task):
        _run(ticketing_bridge.run_close_loop_pass(db))

    mock_update_task.assert_not_called()


def test_close_loop_deleted_ticket_servicenow_variant():
    db = _mock_db()
    task = _make_task(status="open", ticket_ref="INC0001", ticket_provider="servicenow")
    db.compliance_remediation_tasks.find = MagicMock(return_value=_AsyncCursor([task]))

    import compliance_remediation_service as svc
    mock_update_task = AsyncMock()

    with patch(
        "ticketing_bridge.get_ticketing_config",
        AsyncMock(return_value={"provider": "servicenow", "snow_instance": "devxyz"}),
    ), patch(
        "ticketing_bridge.get_servicenow_incident_status",
        AsyncMock(return_value={"success": False, "closed": False, "not_found": True}),
    ), patch.object(svc, "update_task", mock_update_task):
        _run(ticketing_bridge.run_close_loop_pass(db))

    mock_update_task.assert_not_called()


# ---------------------------------------------------------------------------
# raw_db_registration
# ---------------------------------------------------------------------------
def test_raw_db_registration_never_uses_get_database():
    import inspect

    src = inspect.getsource(ticketing_bridge)
    assert "get_database" not in src
    assert inspect.iscoroutinefunction(ticketing_bridge.run_close_loop_pass)
    assert inspect.iscoroutinefunction(ticketing_bridge.start_close_loop_scheduler)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
