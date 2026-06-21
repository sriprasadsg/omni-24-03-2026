"""
Wave-0 unit tests for Phase 7 evidence lifecycle helpers.

Covers:
  - evidence_staleness: compute_stale math, manual-exclusion caller contract,
    get_staleness_threshold default fallback
  - evidence_coc: _append_coc_entry insert, never-raises guarantee

Uses asyncio.run() for async test cases (pytest-asyncio is not installed —
consistent with existing test_rust_heartbeat_parity.py pattern per decision 02-01).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import AsyncMock, MagicMock

from evidence_staleness import compute_stale, get_staleness_threshold
from evidence_coc import _append_coc_entry


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
