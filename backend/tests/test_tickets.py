"""
Tests for /api/tickets endpoints and tickets_service helpers.

Covers:
 - Basic CRUD routing and HTTP status codes
 - The get_history bug (must return 404, not [] for missing tickets)
 - The _compute_sla helper including the malformed-date edge case we fixed
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData


# ---------------------------------------------------------------------------
# Async cursor stub — supports Motor's .sort().skip().limit() chain + async for
# ---------------------------------------------------------------------------

class _AsyncCursor:
    def __init__(self, docs=()):
        self._iter = iter(list(docs))

    def sort(self, *a, **kw):  return self
    def skip(self, *a, **kw):  return self
    def limit(self, *a, **kw): return self
    def __aiter__(self):       return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


# ---------------------------------------------------------------------------
# Collection / database mocks
# ---------------------------------------------------------------------------

def _mock_col(*, docs=(), count=0, find_one_doc=None):
    col = MagicMock()
    col.count_documents = AsyncMock(return_value=count)
    col.find_one       = AsyncMock(return_value=find_one_doc)
    col.insert_one     = AsyncMock(return_value=MagicMock(inserted_id="new-id"))
    col.update_one     = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one     = AsyncMock(return_value=MagicMock(deleted_count=1))
    col.find           = MagicMock(return_value=_AsyncCursor(docs))
    col.aggregate      = MagicMock(return_value=_AsyncCursor())
    return col


def _mock_db(**col_overrides):
    """Return a mock TenantIsolatedDatabase. __getitem__ always returns the same col."""
    col = _mock_col(**col_overrides)
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)
    db._col = col  # expose for assertions
    return db


def _mock_rbac_db():
    """Minimal DB mock for rbac_service — roles.find_one returns None (use defaults)."""
    db = MagicMock()
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(return_value=None)
    return db


@contextmanager
def _patched(tickets_db=None):
    """Patch get_database in all modules touched by a ticket request."""
    db = tickets_db or _mock_db()
    with patch("tickets_service.get_database", return_value=db):
        with patch("tickets_config_mixin.get_database", return_value=db):
            with patch("rbac_service.get_database", return_value=_mock_rbac_db()):
                yield


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_VIEWER = TokenData(username="v@test.com", role="user",        tenant_id="t1",   mfa_verified=True)
_SUPER  = TokenData(username="s@test.com", role="Super Admin", tenant_id=None,   mfa_verified=True)


def _app(user: TokenData):
    import tickets_endpoints
    app = FastAPI()
    app.include_router(tickets_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


# ===========================================================================
# GET /api/tickets  — list
# ===========================================================================

class TestListTickets:

    def test_empty_collection_returns_200_with_structure(self):
        with _patched():
            with TestClient(_app(_VIEWER)) as client:
                r = client.get("/api/tickets")
        assert r.status_code == 200
        body = r.json()
        assert body["tickets"] == []
        assert body["total"] == 0
        assert body["page"] == 1

    def test_super_admin_can_list_all(self):
        with _patched():
            with TestClient(_app(_SUPER)) as client:
                r = client.get("/api/tickets")
        assert r.status_code == 200

    def test_docs_are_returned_when_present(self):
        doc = {
            "id": "t1", "ticket_number": "TKT-0001", "title": "X",
            "status": "open", "priority": "medium",
        }
        with _patched(_mock_db(docs=[doc], count=1)):
            with TestClient(_app(_VIEWER)) as client:
                r = client.get("/api/tickets")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert len(r.json()["tickets"]) == 1

    def test_invalid_sort_dir_returns_422(self):
        with _patched():
            with TestClient(_app(_VIEWER)) as client:
                r = client.get("/api/tickets?sort_dir=desc")
        assert r.status_code == 422


# ===========================================================================
# POST /api/tickets  — create
# ===========================================================================

class TestCreateTicket:

    def test_creates_ticket_returns_200(self):
        db = _mock_db()
        db._col.count_documents = AsyncMock(return_value=0)
        with _patched(db):
            with TestClient(_app(_VIEWER)) as client:
                r = client.post("/api/tickets", json={"title": "Fix login"})
        assert r.status_code == 200
        body = r.json()
        assert body["title"] == "Fix login"
        assert body["status"] == "open"
        assert body["ticket_number"] == "TKT-0001"
        assert "id" in body

    def test_missing_title_returns_422(self):
        with _patched():
            with TestClient(_app(_VIEWER)) as client:
                r = client.post("/api/tickets", json={"description": "no title here"})
        assert r.status_code == 422

    def test_priority_defaults_to_medium(self):
        db = _mock_db()
        db._col.count_documents = AsyncMock(return_value=0)
        with _patched(db):
            with TestClient(_app(_VIEWER)) as client:
                r = client.post("/api/tickets", json={"title": "T"})
        assert r.json()["priority"] == "medium"


# ===========================================================================
# GET /api/tickets/{id}  — fetch single
# ===========================================================================

class TestGetTicket:

    def test_missing_ticket_returns_404(self):
        with _patched(_mock_db(find_one_doc=None)):
            with TestClient(_app(_VIEWER)) as client:
                r = client.get("/api/tickets/nonexistent")
        assert r.status_code == 404

    def test_found_ticket_returns_200(self):
        doc = {
            "id": "abc", "ticket_number": "TKT-0001", "title": "Bug",
            "status": "open", "priority": "high",
        }
        with _patched(_mock_db(find_one_doc=doc)):
            with TestClient(_app(_VIEWER)) as client:
                r = client.get("/api/tickets/abc")
        assert r.status_code == 200
        assert r.json()["id"] == "abc"


# ===========================================================================
# GET /api/tickets/{id}/history
# Bug fix: get_history must return None (not []) for missing tickets so
# the endpoint can raise the correct 404.
# ===========================================================================

class TestTicketHistory:

    def test_missing_ticket_returns_404_not_empty_list(self):
        """Core regression: before the fix, this returned 200 with []."""
        with _patched(_mock_db(find_one_doc=None)):
            with TestClient(_app(_VIEWER)) as client:
                r = client.get("/api/tickets/ghost/history")
        assert r.status_code == 404

    def test_existing_ticket_with_history_returns_list(self):
        doc = {
            "id": "t1", "title": "X", "status": "open",
            "history": [
                {"id": "h1", "actor": "a@b.com", "action": "created",
                 "changes": {}, "created_at": "2026-01-01T00:00:00+00:00"},
            ],
        }
        with _patched(_mock_db(find_one_doc=doc)):
            with TestClient(_app(_VIEWER)) as client:
                r = client.get("/api/tickets/t1/history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert r.json()[0]["action"] == "created"

    def test_existing_ticket_with_no_history_returns_empty_list(self):
        doc = {"id": "t2", "title": "Y", "status": "open", "history": []}
        with _patched(_mock_db(find_one_doc=doc)):
            with TestClient(_app(_VIEWER)) as client:
                r = client.get("/api/tickets/t2/history")
        assert r.status_code == 200
        assert r.json() == []


# ===========================================================================
# _compute_sla  — unit tests (no HTTP)
# ===========================================================================

class TestComputeSla:
    """Tests for the _compute_sla helper including edge cases from the fix."""

    def _sla(self, ticket):
        from tickets_service import _compute_sla
        return _compute_sla(dict(ticket))

    def test_no_due_date_gives_none_status(self):
        assert self._sla({"status": "open"})["sla_status"] == "none"

    def test_past_due_date_gives_breached(self):
        t = self._sla({"status": "open", "due_date": "2020-01-01T00:00:00+00:00"})
        assert t["sla_status"] == "breached"
        assert t["sla_remaining_minutes"] == 0

    def test_future_due_date_gives_ok(self):
        assert self._sla({"status": "open", "due_date": "2099-01-01T00:00:00+00:00"})["sla_status"] == "ok"

    def test_resolved_ticket_is_always_met(self):
        assert self._sla({"status": "resolved", "due_date": "2020-01-01T00:00:00+00:00"})["sla_status"] == "met"

    def test_closed_ticket_is_always_met(self):
        assert self._sla({"status": "closed", "due_date": "2020-01-01T00:00:00+00:00"})["sla_status"] == "met"

    def test_malformed_due_date_returns_none_not_crash(self):
        """Regression: before the fix, a bad due_date would raise ValueError."""
        assert self._sla({"status": "open", "due_date": "not-a-date"})["sla_status"] == "none"

    def test_datetime_object_due_date_is_handled(self):
        """Regression: Motor may return a datetime object instead of a string."""
        from datetime import datetime, timezone, timedelta
        future = datetime.now(timezone.utc) + timedelta(hours=48)
        assert self._sla({"status": "open", "due_date": future})["sla_status"] == "ok"
