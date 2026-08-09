"""Questionnaire answer draft service — shim (Phase 39-08).

Delegates generation to
`ai_orchestration.agents.questionnaire.generate_draft` (create_agent +
`CitedAnswer` structured output + citation validation + guardrails,
39-08) while preserving this module's exact pre-existing contract:
`draft_answer_for_question`'s signature, the `questionnaire_answer_drafts`
Mongo document shape (id, tenantId, questionSetId, questionId, questionText,
answerText, original_answer_text, confidence, sourceEvidenceIds,
sourceEvidence, status, created_at, updated_at), and — critically — the
RAG-02 human-approval gate: every draft this module writes carries
`status="pending_review"`; this module never advances a draft to the
submitted state, by construction, not by omission (Critical Failure Mode #4).

`AnswerDraft` is re-exported as an alias for the shared `CitedAnswer`
schema (39-03) for backward compatibility with any caller that still
imports the pre-39-08 validated-output type name from this module.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ai_orchestration.agents.questionnaire import DraftResult, generate_draft
from ai_orchestration.schemas import CitedAnswer as AnswerDraft  # noqa: F401 — backward-compat re-export
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)


def _build_draft_doc(
    question_id: str,
    tenant_id: str,
    question_text: str,
    question_set_id: Optional[str],
    result: DraftResult,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    doc: Dict[str, Any] = {
        "id": f"qad-{uuid.uuid4().hex}",
        "tenantId": tenant_id,
        "questionSetId": question_set_id,
        "questionId": question_id,
        "questionText": question_text,
        "answerText": result.answer_text,
        "original_answer_text": result.answer_text,
        "confidence": result.confidence,
        "sourceEvidenceIds": result.source_evidence_ids,
        "sourceEvidence": [
            {"source": c.get("source", ""), "content": c.get("content", "")}
            for c in result.retrieved_evidence
        ],
        "status": "pending_review",
        "created_at": now,
        "updated_at": now,
    }
    if result.reason:
        doc["reason"] = result.reason
    return doc


async def draft_answer_for_question(
    question_id: str,
    question_text: str,
    tenant_id: str,
    db,
    question_set_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve tenant evidence, draft a grounded answer via the
    create_agent questionnaire surface, hold for human review.

    Signature, Mongo document shape, and the RAG-02 `pending_review` gate
    are unchanged from the pre-39-08 hand-rolled implementation; generation
    itself now runs through
    `ai_orchestration.agents.questionnaire.generate_draft` instead of a
    hand-rolled prompt + `json.loads` extraction.
    """
    set_tenant_id(tenant_id)

    result = await generate_draft(question_id, question_text, tenant_id, db, question_set_id)
    draft_doc = _build_draft_doc(question_id, tenant_id, question_text, question_set_id, result)

    # Hard T3/RAG-02 guard: this module always inserts status="pending_review"
    # and never advances a draft to submitted — no auto-advance path exists here.
    await db["questionnaire_answer_drafts"].insert_one(draft_doc)
    draft_doc.pop("_id", None)
    return draft_doc


async def _insufficient_evidence_draft(
    question_id: str,
    tenant_id: str,
    question_text: str,
    question_set_id: Optional[str] = None,
    reason: Optional[str] = None,
    db=None,
) -> Dict[str, Any]:
    """Preserved for backward compatibility with any direct caller — builds
    the same insufficient_evidence document shape without invoking the
    agent. `generate_draft` itself now handles the "no evidence" /
    guardrail-blocked / unresolvable-citation cases internally and returns
    an equivalent `DraftResult`, so `draft_answer_for_question` no longer
    calls this helper directly."""
    now = datetime.now(timezone.utc).isoformat()
    doc: Dict[str, Any] = {
        "id": f"qad-{uuid.uuid4().hex}",
        "tenantId": tenant_id,
        "questionSetId": question_set_id,
        "questionId": question_id,
        "questionText": question_text,
        "answerText": "",
        "original_answer_text": "",
        "confidence": "insufficient_evidence",
        "sourceEvidenceIds": [],
        "sourceEvidence": [],
        "status": "pending_review",
        "created_at": now,
        "updated_at": now,
    }
    if reason:
        doc["reason"] = reason
    if db is not None:
        await db["questionnaire_answer_drafts"].insert_one(doc)
        doc.pop("_id", None)
    return doc


async def list_pending_drafts(db, tenant_id: str):
    cursor = db["questionnaire_answer_drafts"].find({"tenantId": tenant_id, "status": "pending_review"}, {"_id": 0})
    return await cursor.to_list(length=None)


async def list_drafts(db, tenant_id: str):
    cursor = db["questionnaire_answer_drafts"].find({"tenantId": tenant_id}, {"_id": 0})
    return await cursor.to_list(length=None)


async def get_draft(draft_id: str, tenant_id: str, db):
    return await db["questionnaire_answer_drafts"].find_one({"id": draft_id, "tenantId": tenant_id}, {"_id": 0})


async def update_draft_status(draft_id: str, tenant_id: str, update: Dict[str, Any], db):
    return await db["questionnaire_answer_drafts"].find_one_and_update(
        {"id": draft_id, "tenantId": tenant_id}, {"$set": update}, return_document=True
    )
