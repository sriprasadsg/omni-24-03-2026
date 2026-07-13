"""Phase 30 tests — inbound questionnaire intake (30-02).

Manual creation, tenant-scoped listing/get, and CSV upload parsing
(including the case-insensitive header match against DictReader's
original-case row keys).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication_service import get_current_user
import questionnaire_inbound_endpoints as ep_mod
from questionnaire_inbound_service import questionnaire_inbound_service

TENANT = "test_tenant"

TEST_SET = {
    "id": "qni-1", "tenantId": TENANT, "title": "T",
    "questions": [{"id": "q1", "text": "Q?", "rowIndex": 0}],
    "status": "Draft", "createdBy": "testuser",
    "created_at": "2000-01-01", "updated_at": "2000-01-01",
}

BASE = "/api/questionnaires/inbound"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    col = MagicMock()
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock()
    col.find_one = AsyncMock(return_value=None)
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    col.find = MagicMock(return_value=cursor)
    db = MagicMock()
    db.questionnaire_inbound = col
    return db


def _db_patch(db):
    """The service binds self._db = get_database at init — patch the instance attr."""
    return patch.object(questionnaire_inbound_service, "_db", MagicMock(return_value=db))


def _make_client():
    app = FastAPI()
    app.include_router(ep_mod.router)
    user = MagicMock()
    user.username = "testuser"
    user.tenant_id = TENANT
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ---------------------------------------------------------------------------
# Create / list / get
# ---------------------------------------------------------------------------

def test_create_success():
    db = _make_db()
    client = _make_client()
    with _db_patch(db):
        resp = client.post(f"{BASE}/", json={"title": "T", "questions": [{"text": "Q?"}]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"].startswith("qni-")
    assert body["status"] == "Draft"
    assert body["tenantId"] == TENANT
    db.questionnaire_inbound.insert_one.assert_awaited_once()


def test_list_empty():
    db = _make_db()
    client = _make_client()
    with _db_patch(db):
        resp = client.get(f"{BASE}/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_with_data():
    db = _make_db()
    db.questionnaire_inbound.find.return_value.to_list = AsyncMock(return_value=[TEST_SET])
    client = _make_client()
    with _db_patch(db):
        resp = client.get(f"{BASE}/")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    # tenant scoping enforced in the query
    query = db.questionnaire_inbound.find.call_args.args[0]
    assert query == {"tenantId": TENANT}


def test_get_found():
    db = _make_db()
    db.questionnaire_inbound.find_one = AsyncMock(return_value=TEST_SET)
    client = _make_client()
    with _db_patch(db):
        resp = client.get(f"{BASE}/qni-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "qni-1"


def test_get_not_found():
    db = _make_db()
    client = _make_client()
    with _db_patch(db):
        resp = client.get(f"{BASE}/qni-x")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# CSV upload
# ---------------------------------------------------------------------------

def test_upload_csv_happy():
    db = _make_db()
    db.questionnaire_inbound.find_one = AsyncMock(return_value={
        "id": "qni-1", "tenantId": TENANT, "questions": [],
    })
    client = _make_client()
    with _db_patch(db):
        resp = client.post(
            f"{BASE}/qni-1/upload",
            files={"file": ("t.csv", b"Question Text\nQ1?\nQ2?", "text/csv")},
        )

    assert resp.status_code == 200
    questions = resp.json()["questions"]
    assert len(questions) == 2
    assert questions[0]["text"] == "Q1?"
    assert questions[1]["text"] == "Q2?"
    db.questionnaire_inbound.update_one.assert_awaited_once()


def test_upload_csv_lowercase_header():
    db = _make_db()
    db.questionnaire_inbound.find_one = AsyncMock(return_value={
        "id": "qni-1", "tenantId": TENANT, "questions": [],
    })
    client = _make_client()
    with _db_patch(db):
        resp = client.post(
            f"{BASE}/qni-1/upload",
            files={"file": ("t.csv", b"question\nQ1?", "text/csv")},
        )
    assert resp.status_code == 200
    assert len(resp.json()["questions"]) == 1


def test_upload_bad_header():
    db = _make_db()
    db.questionnaire_inbound.find_one = AsyncMock(return_value={
        "id": "qni-1", "tenantId": TENANT, "questions": [],
    })
    client = _make_client()
    with _db_patch(db):
        resp = client.post(
            f"{BASE}/qni-1/upload",
            files={"file": ("t.csv", b"BadHeader\nv1\nv2", "text/csv")},
        )
    assert resp.status_code == 400
    assert "No recognized question column header" in resp.json()["detail"]


def test_upload_unsupported_type():
    db = _make_db()
    db.questionnaire_inbound.find_one = AsyncMock(return_value={
        "id": "qni-1", "tenantId": TENANT, "questions": [],
    })
    client = _make_client()
    with _db_patch(db):
        resp = client.post(
            f"{BASE}/qni-1/upload",
            files={"file": ("t.pdf", b"%PDF-", "application/pdf")},
        )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_upload_not_found():
    db = _make_db()  # find_one → None
    client = _make_client()
    with _db_patch(db):
        resp = client.post(
            f"{BASE}/qni-x/upload",
            files={"file": ("t.csv", b"Question Text\nQ?", "text/csv")},
        )
    assert resp.status_code == 404
