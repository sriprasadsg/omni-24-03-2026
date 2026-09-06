"""Tests for the append-only control-session audit service (74-02 Task 1)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import control_session_audit_service as mod

# Same collection fake as test_remote_access._col/_db
def _col(**kw):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit-id"))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    col.delete_one = AsyncMock()
    _cur = MagicMock()
    _cur.sort = MagicMock(return_value=_cur)
    _cur.limit = MagicMock(return_value=_cur)
    _cur.to_list = AsyncMock(return_value=[])
    col.find = MagicMock(return_value=_cur)
    col.count_documents = AsyncMock(return_value=0)
    for k, v in kw.items():
        setattr(col, k, v)
    return col


def _db():
    db = MagicMock()
    db.control_session_audit = _col()
    return db


@pytest.mark.asyncio
async def test_write_audit_inserts_and_returns_string_id():
    db = _db()
    rid = await mod.write_audit(db, "tenant-1", {"session_id": "s1", "event": "session_start"})
    assert rid == "audit-id"
    assert db.control_session_audit.insert_one.called
    doc = db.control_session_audit.insert_one.call_args[0][0]
    assert doc["session_id"] == "s1"
    assert doc["tenantId"] == "tenant-1"
    assert doc["ts"].startswith("20")  # ISO-8601 default


@pytest.mark.asyncio
async def test_write_audit_respects_caller_defaults():
    db = _db()
    fixed = "2026-01-01T00:00:00+00:00"
    await mod.write_audit(db, "tenant-1", {"session_id": "s2", "ts": fixed, "tenantId": "kept"})
    doc = db.control_session_audit.insert_one.call_args[0][0]
    assert doc["ts"] == fixed
    assert doc["tenantId"] == "kept"


@pytest.mark.asyncio
async def test_write_audit_swallows_ocsf_push_failure():
    db = _db()
    with patch("soc_integration_service.push_ocsf_event", side_effect=RuntimeError("SIEM down")):
        rid = await mod.write_audit(db, "tenant-1", {"session_id": "s3"})
    assert rid == "audit-id"


@pytest.mark.asyncio
async def test_write_audit_swallows_missing_soc_module():
    db = _db()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "soc_integration_service":
            raise ImportError("no soc")
        return real_import(name, *a, **k)

    with patch("builtins.__import__", side_effect=fake_import):
        rid = await mod.write_audit(db, "tenant-1", {"session_id": "s4"})
    assert rid == "audit-id"


@pytest.mark.asyncio
async def test_list_audit_scopes_and_sorts():
    db = _db()
    db.control_session_audit.find = MagicMock(return_value=db.control_session_audit.find.return_value)
    cur = db.control_session_audit.find.return_value
    await mod.list_audit(db, "tenant-1", {"event": "session_end"}, limit=25)
    # find called with tenant-scoped query + _id projection
    q = cur.sort.call_args  # (("ts", -1),) kwargs limit
    assert cur.limit.called
    assert db.control_session_audit.find.call_args.args[0] == {"tenantId": "tenant-1", "event": "session_end"}
    assert db.control_session_audit.find.call_args.args[1] == {"_id": 0}
    assert cur.limit.call_args.args[0] == 25


def test_no_update_or_delete_exposed():
    public = {n for n in dir(mod) if not n.startswith("_")}
    assert "write_audit" in public
    assert "list_audit" in public
    bad = [n for n in public if "update" in n.lower() or "delete" in n.lower()]
    assert bad == [], f"Mutation paths leaked: {bad}"