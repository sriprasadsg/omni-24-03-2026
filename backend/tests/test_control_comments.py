"""Tests for control comment threads (Phase 42, CMT-01).

Uses the FastAPI TestClient + dependency_overrides + patch("...get_database")
convention established in test_evidence_review.py.
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_user(tenant_id="tenant-a", role="admin", username="reviewer1"):
    u = MagicMock()
    u.tenant_id = tenant_id
    u.role = role
    u.username = username
    return u


def _make_mock_db(seeded_comments=None):
    """Return a mock DB whose only surface is `control_comments` — no other
    collection should ever be touched by the service/endpoints under test."""
    db = MagicMock()
    db.control_comments = MagicMock()
    db.control_comments.insert_one = AsyncMock(return_value=MagicMock(inserted_id="cc-1"))
    db.control_comments.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=seeded_comments or [])
    ))))
    return db


_active_patchers = []


def _build_client(mock_db, current_user):
    import control_comments_endpoints as mod
    from authentication_service import get_current_user

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: current_user

    patcher = patch("control_comments_endpoints.get_database", return_value=mock_db)
    patcher.start()
    _active_patchers.append(patcher)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _stop_patchers():
    yield
    while _active_patchers:
        _active_patchers.pop().stop()


# ── Test 1: Role gate ───────────────────────────────────────────────────────────


def test_non_author_role_forbidden():
    """A non-reviewer role (plain 'user') gets 403 on POST."""
    db = _make_mock_db()
    user = _make_user("tenant-a", "user")
    client = _build_client(db, user)

    resp = client.post(
        "/api/control-comments",
        json={"control_id": "ctrl-1", "text": "hello"},
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    db.control_comments.insert_one.assert_not_awaited()


# ── Test 2: Post + list ─────────────────────────────────────────────────────────


def test_post_and_list_comment():
    """Admin can POST a comment (200, persisted) and GET it back."""
    db = _make_mock_db()
    user = _make_user("tenant-a", "admin", username="admin1")
    client = _build_client(db, user)

    resp = client.post(
        "/api/control-comments",
        json={"control_id": "ctrl-1", "text": "Looks compliant."},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    db.control_comments.insert_one.assert_awaited()
    inserted_doc = db.control_comments.insert_one.await_args.args[0]
    assert inserted_doc["control_id"] == "ctrl-1"
    assert inserted_doc["author"] == "admin1"
    assert inserted_doc["text"] == "Looks compliant."
    assert "created_at" in inserted_doc

    # Now GET — seed the mock with what would have been persisted.
    db2 = _make_mock_db(seeded_comments=[inserted_doc])
    client2 = _build_client(db2, user)
    resp2 = client2.get("/api/control-comments", params={"control_id": "ctrl-1"})
    assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.text}"
    data = resp2.json()
    assert len(data) == 1
    assert data[0]["control_id"] == "ctrl-1"
    assert data[0]["text"] == "Looks compliant."


# ── Test 3: Tenant isolation via dedicated collection ───────────────────────────


def test_tenant_isolation():
    """Comments route exclusively through db.control_comments (never the
    shared/exempt db.compliance_controls document), and the endpoint always
    obtains its db handle via get_database() — the tenant-isolated wrapper —
    so cross-tenant isolation is delegated to that wrapper, not manual
    per-request filtering."""
    import control_comments_endpoints as endpoints_mod
    import control_comments_service as service_mod
    import inspect

    # The endpoints module must call get_database() to obtain its db handle.
    endpoints_src = inspect.getsource(endpoints_mod)
    assert "get_database()" in endpoints_src

    # Neither the service nor the endpoints module ever references the
    # shared/exempt compliance_controls collection.
    service_src = inspect.getsource(service_mod)
    assert "compliance_controls" not in service_src
    assert "compliance_controls" not in endpoints_src

    # Functional check: seed two tenants' worth of comments in separate mock
    # DBs (as get_database() would return a tenant-scoped handle per
    # request) and confirm each tenant only ever sees its own data through
    # the endpoint — i.e. the service never merges across db instances.
    db_a = _make_mock_db(seeded_comments=[
        {"id": "c1", "control_id": "ctrl-1", "author": "u1", "text": "tenant A comment", "created_at": "2026-01-01T00:00:00Z"}
    ])
    user_a = _make_user("tenant-a", "admin")
    client_a = _build_client(db_a, user_a)
    resp_a = client_a.get("/api/control-comments", params={"control_id": "ctrl-1"})
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert len(data_a) == 1
    assert data_a[0]["text"] == "tenant A comment"

    db_b = _make_mock_db(seeded_comments=[])
    user_b = _make_user("tenant-b", "admin")
    client_b = _build_client(db_b, user_b)
    resp_b = client_b.get("/api/control-comments", params={"control_id": "ctrl-1"})
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b == []
