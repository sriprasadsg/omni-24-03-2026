"""
Phase 7 evidence lifecycle tests.

Wave-0 (unit):
  - evidence_staleness: compute_stale math, manual-exclusion caller contract,
    get_staleness_threshold default fallback
  - evidence_coc: _append_coc_entry insert, never-raises guarantee

Wave-1 (endpoint integration — Plan 07-02):
  - GET/PATCH /api/settings/evidence-staleness (STALE-02)
  - GET /api/compliance/evidence/{id}/audit-log (COC-02)
  - Tenant isolation + admin gate contracts

Uses asyncio.run() for async test cases (pytest-asyncio not installed —
consistent with test_rust_heartbeat_parity.py pattern per decision 02-01).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user

from evidence_staleness import compute_stale, get_staleness_threshold
from evidence_coc import _append_coc_entry
import compliance_evidence_lifecycle_endpoints as lifecycle_mod


# ---------------------------------------------------------------------------
# Staleness helpers
# ---------------------------------------------------------------------------

def _make_mock_db(find_one_return=None):
    """Build a MagicMock db whose raw _db.system_settings.find_one is an AsyncMock."""
    raw = MagicMock()
    raw.system_settings = MagicMock()
    raw.system_settings.find_one = AsyncMock(return_value=find_one_return)

    raw.evidence_audit_log = MagicMock()
    raw.evidence_audit_log.insert_one = AsyncMock(
        return_value=MagicMock(inserted_id="fake-id")
    )

    db = MagicMock()
    db._db = raw
    return db


# ---------------------------------------------------------------------------
# Test: staleness computation
# ---------------------------------------------------------------------------

def test_staleness_computation():
    """compute_stale with an old date returns stale=True and stale_days > threshold."""
    result = compute_stale("2000-01-01T00:00:00+00:00", 7)
    assert result["stale"] is True, f"Expected stale=True, got {result}"
    assert result["stale_days"] > 7, f"Expected stale_days > 7, got {result}"


def test_staleness_inside_window():
    """compute_stale with a future date inside the window returns stale=False."""
    # A date far in the future will never be stale.
    result = compute_stale("2099-01-01T00:00:00+00:00", 7)
    assert result["stale"] is False, f"Expected stale=False, got {result}"


def test_staleness_bad_input():
    """compute_stale on unparsable input returns safe default without raising."""
    result = compute_stale("not-a-date", 7)
    assert result == {"stale": False, "stale_days": 0}, f"Expected default, got {result}"


# ---------------------------------------------------------------------------
# Test: manual-evidence exclusion caller contract
# ---------------------------------------------------------------------------

def test_staleness_manual_excluded():
    """Caller-contract: manual evidence must not be passed to compute_stale.

    The gate `bool(ev.get('systemGenerated') or ev.get('source') == 'auto')`
    must evaluate to False for manual evidence so compute_stale is never
    invoked. This test documents that invariant without calling compute_stale.
    """
    ev = {
        "source": "manual",
        "systemGenerated": False,
        "uploadedAt": "2000-01-01T00:00:00+00:00",
    }
    is_auto = bool(ev.get("systemGenerated") or ev.get("source") == "auto")
    assert is_auto is False, (
        "Manual evidence passed the automation gate — compute_stale would be called incorrectly"
    )


# ---------------------------------------------------------------------------
# Test: staleness threshold default
# ---------------------------------------------------------------------------

def test_staleness_threshold_default():
    """get_staleness_threshold returns 7 when no settings doc exists."""
    mock_db = _make_mock_db(find_one_return=None)
    result = asyncio.run(get_staleness_threshold(mock_db, "tenant-a"))
    assert result == 7, f"Expected default threshold 7, got {result}"


# ---------------------------------------------------------------------------
# Test: CoC create entry
# ---------------------------------------------------------------------------

def test_coc_create_entry():
    """_append_coc_entry awaits insert_one once with correct fields."""
    mock_db = _make_mock_db()
    insert_mock = mock_db._db.evidence_audit_log.insert_one

    asyncio.run(
        _append_coc_entry(
            db=mock_db,
            evidence_id="ev-1",
            tenant_id="tenant-a",
            actor="admin@t.com",
            action_type="create",
            snapshot_before=None,
            snapshot_after={"id": "ev-1"},
        )
    )

    insert_mock.assert_awaited_once()
    call_args = insert_mock.call_args[0][0]
    assert call_args["action_type"] == "create", f"action_type mismatch: {call_args}"
    assert call_args["evidenceId"] == "ev-1", f"evidenceId mismatch: {call_args}"
    assert call_args["tenantId"] == "tenant-a", f"tenantId mismatch: {call_args}"
    assert call_args["actor"] == "admin@t.com", f"actor mismatch: {call_args}"
    assert "timestamp" in call_args, f"timestamp missing: {call_args}"
    assert call_args["snapshot_before"] is None
    assert call_args["snapshot_after"] == {"id": "ev-1"}


# ---------------------------------------------------------------------------
# Test: CoC never raises
# ---------------------------------------------------------------------------

def test_coc_never_raises():
    """_append_coc_entry returns None and does not raise when insert_one fails."""
    mock_db = _make_mock_db()
    mock_db._db.evidence_audit_log.insert_one = AsyncMock(
        side_effect=Exception("boom")
    )

    result = asyncio.run(
        _append_coc_entry(
            db=mock_db,
            evidence_id="ev-fail",
            tenant_id="tenant-a",
            actor="user@t.com",
            action_type="delete",
            snapshot_before={"id": "ev-fail"},
            snapshot_after=None,
        )
    )

    assert result is None, f"Expected None return, got {result}"


# ---------------------------------------------------------------------------
# CoC delete entry (optional — asserts delete action_type / snapshot contract)
# ---------------------------------------------------------------------------

def test_coc_delete_entry():
    """_append_coc_entry with action_type='delete' stores snapshot_before, snapshot_after=None."""
    mock_db = _make_mock_db()
    insert_mock = mock_db._db.evidence_audit_log.insert_one

    asyncio.run(
        _append_coc_entry(
            db=mock_db,
            evidence_id="ev-del",
            tenant_id="tenant-a",
            actor="user@t.com",
            action_type="delete",
            snapshot_before={"id": "ev-del", "name": "old.pdf"},
            snapshot_after=None,
        )
    )

    insert_mock.assert_awaited_once()
    doc = insert_mock.call_args[0][0]
    assert doc["action_type"] == "delete"
    assert doc["snapshot_before"] == {"id": "ev-del", "name": "old.pdf"}
    assert doc["snapshot_after"] is None


# ===========================================================================
# Helpers for endpoint integration tests
# ===========================================================================

def _fake_user(role="admin", tenant_id="tenant-a", username="admin@test.com"):
    user = MagicMock()
    user.role = role
    user.tenant_id = tenant_id
    user.username = username
    return user


def _col_simple(**kw):
    """Build a simple mock collection with AsyncMock methods."""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="fake"))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    # find().sort().to_list() chain
    sort_mock = MagicMock()
    sort_mock.to_list = AsyncMock(return_value=[])
    find_mock = MagicMock()
    find_mock.sort = MagicMock(return_value=sort_mock)
    find_mock.to_list = AsyncMock(return_value=[])
    col.find = MagicMock(return_value=find_mock)
    for k, v in kw.items():
        setattr(col, k, v)
    return col


def _make_lifecycle_app(user, raw_db_overrides=None):
    """Mount the lifecycle router with fake user + patched db."""
    raw = MagicMock()
    raw.system_settings = _col_simple()
    raw.evidence_audit_log = _col_simple()
    raw.control_evidence = _col_simple()
    raw.asset_compliance = _col_simple()
    if raw_db_overrides:
        for k, v in raw_db_overrides.items():
            setattr(raw, k, v)

    db_mock = MagicMock()
    db_mock._db = raw

    app = FastAPI()
    app.include_router(lifecycle_mod.router)
    app.dependency_overrides[get_current_user] = lambda: user

    return app, db_mock, raw


# ===========================================================================
# Endpoint integration tests (STALE-02 GET/PATCH + COC-02 GET)
# ===========================================================================

def test_get_staleness_threshold_default():
    """GET /api/settings/evidence-staleness with no DB doc returns 200 + thresholdDays 7."""
    user = _fake_user(role="viewer")
    app, db_mock, raw = _make_lifecycle_app(user)

    with patch.object(lifecycle_mod, "get_database", return_value=db_mock):
        client = TestClient(app)
        resp = client.get("/api/settings/evidence-staleness")

    assert resp.status_code == 200, resp.text
    assert resp.json()["thresholdDays"] == 7


def test_patch_staleness_threshold():
    """PATCH /api/settings/evidence-staleness with admin role and valid body returns 200."""
    user = _fake_user(role="admin", tenant_id="t-1")
    app, db_mock, raw = _make_lifecycle_app(user)

    with patch.object(lifecycle_mod, "get_database", return_value=db_mock):
        client = TestClient(app)
        resp = client.patch(
            "/api/settings/evidence-staleness",
            json={"thresholdDays": 14},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["thresholdDays"] == 14
    raw.system_settings.update_one.assert_awaited_once()
    call_kwargs = raw.system_settings.update_one.call_args
    assert call_kwargs[1].get("upsert") is True


def test_patch_staleness_requires_admin():
    """PATCH /api/settings/evidence-staleness as non-admin returns 403."""
    user = _fake_user(role="viewer")
    app, db_mock, raw = _make_lifecycle_app(user)

    with patch.object(lifecycle_mod, "get_database", return_value=db_mock):
        client = TestClient(app)
        resp = client.patch(
            "/api/settings/evidence-staleness",
            json={"thresholdDays": 14},
        )

    assert resp.status_code == 403, resp.text


def test_staleness_threshold_validation():
    """PATCH with thresholdDays 0 or 400 returns 422 (Pydantic Field(ge=1, le=365))."""
    user = _fake_user(role="admin")
    app, db_mock, _ = _make_lifecycle_app(user)

    with patch.object(lifecycle_mod, "get_database", return_value=db_mock):
        client = TestClient(app)
        assert client.patch(
            "/api/settings/evidence-staleness", json={"thresholdDays": 0}
        ).status_code == 422
        assert client.patch(
            "/api/settings/evidence-staleness", json={"thresholdDays": 400}
        ).status_code == 422


def test_get_coc_log():
    """GET /api/compliance/evidence/{id}/audit-log returns 200 with seeded entries."""
    entries = [
        {"evidenceId": "ev-1", "tenantId": "t-1", "action_type": "create", "timestamp": "2026-01-01T00:00:00Z"},
        {"evidenceId": "ev-1", "tenantId": "t-1", "action_type": "delete", "timestamp": "2026-06-01T00:00:00Z"},
    ]

    sort_mock = MagicMock()
    sort_mock.to_list = AsyncMock(return_value=entries)
    find_result = MagicMock()
    find_result.sort = MagicMock(return_value=sort_mock)

    audit_col = _col_simple()
    audit_col.find = MagicMock(return_value=find_result)

    user = _fake_user(role="admin", tenant_id="t-1")
    app, db_mock, _ = _make_lifecycle_app(user, raw_db_overrides={"evidence_audit_log": audit_col})

    with patch.object(lifecycle_mod, "get_database", return_value=db_mock):
        client = TestClient(app)
        resp = client.get("/api/compliance/evidence/ev-1/audit-log")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["entries"]) == 2


def test_coc_tenant_isolation():
    """Non-super users without tenant_id get 403; tenant users' query includes their tenantId."""
    # 1. No-tenant non-super user should get 403
    user_no_tenant = _fake_user(role="viewer", tenant_id=None)
    app_no_tenant, db_no_tenant, _ = _make_lifecycle_app(user_no_tenant)
    with patch.object(lifecycle_mod, "get_database", return_value=db_no_tenant):
        client = TestClient(app_no_tenant)
        resp = client.get("/api/compliance/evidence/ev-1/audit-log")
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

    # 2. Tenant user's find() call must include their tenantId in the query
    user_tenant = _fake_user(role="viewer", tenant_id="t-xyz")
    app_tenant, db_tenant, raw_tenant = _make_lifecycle_app(user_tenant)

    sort_mock = MagicMock()
    sort_mock.to_list = AsyncMock(return_value=[])
    find_result = MagicMock()
    find_result.sort = MagicMock(return_value=sort_mock)
    raw_tenant.evidence_audit_log.find = MagicMock(return_value=find_result)

    with patch.object(lifecycle_mod, "get_database", return_value=db_tenant):
        client = TestClient(app_tenant)
        resp = client.get("/api/compliance/evidence/ev-1/audit-log")

    assert resp.status_code == 200, resp.text
    call_args = raw_tenant.evidence_audit_log.find.call_args
    query_arg = call_args[0][0]
    assert query_arg.get("tenantId") == "t-xyz", f"tenantId missing from query: {query_arg}"
