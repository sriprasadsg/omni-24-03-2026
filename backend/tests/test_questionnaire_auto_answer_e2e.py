"""Phase 30 e2e — AI questionnaire auto-answer pipeline.

Drives the full path over HTTP against a mocked db/RAG/LLM:
create question set → generate grounded draft → create review → approve →
submit. Also asserts the T3 guard: a draft that never reached "approved"
cannot be submitted.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication_service import get_current_user
import questionnaire_inbound_endpoints as inbound_mod
import questionnaire_answer_draft_endpoints as draft_ep_mod
import questionnaire_answer_review_endpoints as review_ep_mod
from questionnaire_inbound_service import questionnaire_inbound_service

TENANT = "tenant-123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_col():
    col = MagicMock()
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock()
    col.find_one = AsyncMock(return_value=None)
    col.find_one_and_update = AsyncMock(return_value=None)
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[])
    col.find = MagicMock(return_value=cursor)
    return col


def _make_db():
    """Supports both attribute access (draft service) and subscription (review service)."""
    cols = {
        "questionnaire_inbound": _make_col(),
        "questionnaire_answer_drafts": _make_col(),
        "questionnaire_answer_reviews": _make_col(),
    }
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=cols.__getitem__)
    for name, col in cols.items():
        setattr(db, name, col)
    return db, cols


def _make_client():
    app = FastAPI()
    app.include_router(inbound_mod.router)
    app.include_router(draft_ep_mod.router)
    app.include_router(review_ep_mod.router)
    user = MagicMock()
    user.username = "testuser"
    user.tenant_id = TENANT
    user.role = "admin"
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _pipeline_patches(db, confidence="high", answer_text="Yes, we have MFA.", source_ids=None):
    """Phase 39-08: generation moved from a hand-rolled prompt + JSON parse
    (`questionnaire_answer_draft_service.rag_service`/`.ai_service`) to
    `ai_orchestration.agents.questionnaire.generate_draft`. This e2e file's
    job is exercising the HTTP pipeline (generate -> review -> approve ->
    submit + the T3 bypass guard), not draft-generation internals — those
    are covered by `test_questionnaire_agent.py`'s hermetic unit tests — so
    the mock boundary is retargeted onto the shim's own call to
    `generate_draft` rather than the removed `rag_service`/`ai_service`
    module attributes."""
    from ai_orchestration.agents.questionnaire import DraftResult

    is_insufficient = confidence == "insufficient_evidence"
    canned = DraftResult(
        answer_text=answer_text,
        confidence=confidence,
        source_evidence_ids=[] if is_insufficient else (source_ids if source_ids is not None else ["doc1"]),
        model_provenance="primary",
        needs_review=False,
        retrieved_evidence=[] if is_insufficient else [
            {"id": "ev1", "content": "MFA is required for all users.", "source": "doc1",
             "tenantId": TENANT, "relevance": 0.1},
        ],
    )
    gen = AsyncMock(return_value=canned)
    get_db = MagicMock(return_value=db)
    return (
        patch("questionnaire_answer_draft_service.generate_draft", gen),
        patch("questionnaire_answer_draft_endpoints.get_database", get_db),
        patch("questionnaire_answer_review_endpoints.get_database", get_db),
        patch.object(questionnaire_inbound_service, "_db", get_db),
        gen,
    )


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def test_questionnaire_pipeline_e2e():
    db, cols = _make_db()
    client = _make_client()
    p1, p2, p3, p4, gen = _pipeline_patches(db)

    with p1, p2, p3, p4:
        # 1. Create inbound question set
        resp = client.post("/api/questionnaires/inbound/", json={"title": "Test Set"})
        assert resp.status_code == 200

        # 2. Generate grounded draft (RAG + LLM, held for review)
        resp = client.post(
            "/api/questionnaire-answer-drafts/generate",
            params={"question_id": "q1", "question_text": "Do you have MFA?"},
        )
        assert resp.status_code == 200
        draft = resp.json()
        qad_id = draft["id"]
        assert draft["status"] == "pending_review"
        assert draft["answerText"] == "Yes, we have MFA."
        assert draft["sourceEvidenceIds"] == ["doc1"]
        # generation was invoked tenant-scoped
        assert gen.call_args.args[2] == TENANT

        # 3. Create review (draft must be pending_review)
        cols["questionnaire_answer_drafts"].find_one = AsyncMock(return_value={
            "id": qad_id, "tenantId": TENANT, "status": "pending_review",
        })
        resp = client.post(f"/api/questionnaire-answer-drafts/{qad_id}/review")
        assert resp.status_code == 200
        qar_id = resp.json()["id"]

        # 4. Approve
        cols["questionnaire_answer_reviews"].find_one_and_update = AsyncMock(return_value={
            "id": qar_id, "draftId": qad_id, "status": "pending",
        })
        cols["questionnaire_answer_drafts"].find_one = AsyncMock(return_value={
            "id": qad_id, "tenantId": TENANT, "status": "approved",
        })
        resp = client.patch(
            f"/api/questionnaire-answer-drafts/{qad_id}/review/{qar_id}",
            json={"decision": "approved", "comment": "Verified."},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        # 5. Submit (T3: transition query filters on approved)
        cols["questionnaire_answer_drafts"].find_one_and_update = AsyncMock(return_value={
            "id": qad_id, "tenantId": TENANT, "status": "submitted",
        })
        resp = client.post(f"/api/questionnaire-answer-drafts/{qad_id}/submit")
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"
        query = cols["questionnaire_answer_drafts"].find_one_and_update.call_args.args[0]
        assert query["status"] == "approved"


def test_questionnaire_submit_bypass_rejection():
    """T3 guard: a pending_review draft can never be submitted directly."""
    db, cols = _make_db()
    client = _make_client()
    # find_one_and_update filters on status "approved" → no match → None
    cols["questionnaire_answer_drafts"].find_one_and_update = AsyncMock(return_value=None)

    with patch("questionnaire_answer_review_endpoints.get_database", MagicMock(return_value=db)):
        resp = client.post("/api/questionnaire-answer-drafts/qad-bypass/submit")

    assert resp.status_code == 409
    assert "must be in approved state" in resp.json()["detail"]


def test_generate_insufficient_evidence_when_rag_empty():
    """No retrieved evidence → insufficient_evidence draft, still pending_review."""
    db, _ = _make_db()
    client = _make_client()
    p1, p2, p3, p4, gen = _pipeline_patches(db, confidence="insufficient_evidence", answer_text="")

    with p1, p2, p3, p4:
        resp = client.post(
            "/api/questionnaire-answer-drafts/generate",
            params={"question_id": "q2", "question_text": "Do you have SOC3?"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["confidence"] == "insufficient_evidence"
    assert body["status"] == "pending_review"
    assert body["answerText"] == ""


def test_generate_hallucination_guard():
    """A confident answer with no resolvable citations is downgraded to
    insufficient_evidence by `generate_draft`'s own citation-validation
    wiring (39-08; unit-tested directly in test_questionnaire_agent.py) —
    this e2e test only asserts the shim/endpoint surfaces that downgraded
    result unchanged through to the HTTP response."""
    db, _ = _make_db()
    client = _make_client()
    p1, p2, p3, p4, gen = _pipeline_patches(
        db, confidence="insufficient_evidence", answer_text="", source_ids=[]
    )

    with p1, p2, p3, p4:
        resp = client.post(
            "/api/questionnaire-answer-drafts/generate",
            params={"question_id": "q3", "question_text": "Are you ISO 42001 certified?"},
        )

    assert resp.status_code == 200
    assert resp.json()["confidence"] == "insufficient_evidence"
