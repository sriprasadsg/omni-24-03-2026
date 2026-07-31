"""Eval dimension: RAG-02 human-approval gate (AI-SPEC Section 5,
Questionnaire answer honesty — code half; Failure Mode 4).

Code check on the questionnaire draft state machine
(`questionnaire_answer_draft_service.py` + `questionnaire_answer_review_service.py`):
a draft can NEVER transition to `submitted` without an approver identity —

  pending_review -> approved | rejected | needs_revision   (reviewer decision)
  approved       -> submitted                              (mark_submitted only)

Asserted here: every freshly generated draft lands `pending_review`
regardless of model confidence; the ONLY query that can write
`status="submitted"` filters on `status="approved"` and stamps the
mandatory `submitted_by` identity; `"submitted"` is not a valid reviewer
decision (no decision path skips the approved state); and an approval
decision itself never advances past `approved` — i.e. no auto-advance path
exists. Extends the Phase 30-03 review-service test conventions (mock db
with dict-style collection access). Deterministic, `not llm`.
"""
import inspect
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from ai_orchestration.agents.questionnaire import DraftResult
from questionnaire_answer_draft_service import draft_answer_for_question
from questionnaire_answer_review_service import (
    create_review,
    mark_submitted,
    update_review_decision,
)

from tests.eval_langchain.conftest import EVAL_TENANT_A_ID

pytestmark = pytest.mark.eval


class MockDB:
    """Dict-style collection access matching the services' `db[...]` reads
    (same convention as test_questionnaire_answer_review_service.py)."""

    def __init__(self):
        self.reviews = AsyncMock()
        self.drafts = AsyncMock()

    def __getitem__(self, key):
        if key == "questionnaire_answer_reviews":
            return self.reviews
        if key == "questionnaire_answer_drafts":
            return self.drafts
        return AsyncMock()


def _confident_draft_result() -> DraftResult:
    return DraftResult(
        answer_text="Yes, MFA is enforced org-wide.",
        confidence="high",
        source_evidence_ids=["cev-1"],
        model_provenance="primary",
        needs_review=False,
        retrieved_evidence=[{"source": "mfa", "content": "MFA enforced."}],
    )


class TestEveryDraftLandsPendingReview:
    async def test_high_confidence_draft_still_pending_review(self):
        """Even a maximally confident agent draft is inserted
        `status="pending_review"` — confidence never bypasses the gate."""
        db = MockDB()
        with patch(
            "questionnaire_answer_draft_service.generate_draft",
            AsyncMock(return_value=_confident_draft_result()),
        ):
            doc = await draft_answer_for_question(
                question_id="q-1",
                question_text="Is MFA enforced?",
                tenant_id=EVAL_TENANT_A_ID,
                db=db,
            )
        assert doc["status"] == "pending_review"
        inserted = db.drafts.insert_one.await_args.args[0]
        assert inserted["status"] == "pending_review"

    async def test_insufficient_evidence_draft_also_pending_review(self):
        db = MockDB()
        result = DraftResult(
            answer_text="",
            confidence="insufficient_evidence",
            source_evidence_ids=[],
            model_provenance="primary",
            needs_review=False,
            reason="no_evidence_retrieved",
        )
        with patch(
            "questionnaire_answer_draft_service.generate_draft",
            AsyncMock(return_value=result),
        ):
            doc = await draft_answer_for_question(
                question_id="q-2",
                question_text="Unanswerable question",
                tenant_id=EVAL_TENANT_A_ID,
                db=db,
            )
        assert doc["status"] == "pending_review"


class TestSubmittedRequiresApprover:
    async def test_mark_submitted_only_transitions_approved_drafts(self):
        """The single query that can write `submitted` filters on
        `status="approved"` — a pending/rejected draft can never match."""
        db = MockDB()
        db.drafts.find_one_and_update = AsyncMock(return_value={"status": "submitted"})
        await mark_submitted("draft-1", db, EVAL_TENANT_A_ID, submitted_by="alice@example.com")
        query_filter, update = db.drafts.find_one_and_update.await_args.args
        assert query_filter["status"] == "approved"
        assert update["$set"]["status"] == "submitted"
        assert update["$set"]["submitted_by"] == "alice@example.com"

    async def test_mark_submitted_returns_none_for_unapproved_draft(self):
        db = MockDB()
        db.drafts.find_one_and_update = AsyncMock(return_value=None)
        result = await mark_submitted(
            "draft-1", db, EVAL_TENANT_A_ID, submitted_by="alice@example.com"
        )
        assert result is None

    def test_submitted_by_identity_is_mandatory(self):
        """`submitted_by` has no default — the submitted transition cannot
        even be invoked without an approver identity."""
        param = inspect.signature(mark_submitted).parameters["submitted_by"]
        assert param.default is inspect.Parameter.empty


class TestNoAutoAdvancePath:
    async def test_submitted_is_not_a_valid_reviewer_decision(self):
        """The reviewer decision vocabulary cannot express `submitted` — no
        decision call can jump a draft straight to the terminal state."""
        db = MockDB()
        with pytest.raises(ValueError):
            await update_review_decision(
                review_id="rev-1",
                draft_id="draft-1",
                decision="submitted",
                comment="skip ahead",
                db=db,
                tenant_id=EVAL_TENANT_A_ID,
                decided_by="alice@example.com",
            )
        db.reviews.find_one_and_update.assert_not_awaited()

    async def test_approval_decision_stops_at_approved(self):
        """Approving a review advances the draft to `approved`, never
        directly to `submitted` — submission stays a separate, identity-
        stamped human action."""
        db = MockDB()
        db.reviews.find_one_and_update = AsyncMock(
            return_value={"id": "rev-1", "draftId": "draft-1", "status": "pending"}
        )
        db.drafts.update_one = AsyncMock(return_value=None)
        db.drafts.find_one = AsyncMock(
            return_value={"id": "draft-1", "status": "approved"}
        )
        await update_review_decision(
            review_id="rev-1",
            draft_id="draft-1",
            decision="approved",
            comment=None,
            db=db,
            tenant_id=EVAL_TENANT_A_ID,
            decided_by="alice@example.com",
        )
        _, update = db.drafts.update_one.await_args.args
        assert update["$set"]["status"] == "approved"
        assert update["$set"]["reviewerId"] == "alice@example.com"

    async def test_create_review_requires_pending_review_draft(self):
        """Reviews only attach to `pending_review` drafts — the gate's entry
        point is itself state-checked."""
        db = MockDB()
        db.drafts.find_one = AsyncMock(return_value=None)
        assert await create_review("draft-x", db, EVAL_TENANT_A_ID) is None
        query_filter = db.drafts.find_one.await_args.args[0]
        assert query_filter["status"] == "pending_review"
