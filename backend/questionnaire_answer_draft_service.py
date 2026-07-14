"""Questionnaire answer draft service — RAG + grounded generation + validation.

This module implements the AI part of Phase 30-04: generates grounded answers from tenant-specific evidence, flags missing evidence, and ignores guardrails BLOCKED/Error strings.

It must:
1. Use tenant-scoped `rag_service.query()` (Phase 30-01)
2. Generate with `ai_service.generate_text()` (Phase 30-01)
3. Validate with AnswerDraft model (Phase 30-SPEC lines 156-247)
4. Store as pending_review in `questionnaire_answer_drafts`
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator, ValidationError
from fastapi import HTTPException

from rag_service import rag_service
from ai_service import ai_service
from database import get_database
from tenant_context import get_tenant_id, set_tenant_id

logger = logging.getLogger(__name__)

_MAX_CHUNKS = 5
_MAX_ANSWER_LENGTH = 2000


def _sanitise_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """Remove PII and irrelevant parts from a single chunk before using as prompt context."""
    content = chunk.get("content", "")
    if not isinstance(content, str):
        content = str(content or "")
    # Strip markdown fence artifacts that might come from doc ingestion
    content = content.replace("```json", "").replace("```", "").strip()
    # Basic PII scrub (email address format) — extend as needed for real personas
    import re
    content = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', "[REDACTED_EMAIL]", content)
    # Remove internal path/tracer signs
    content = re.sub(r'\b(/workspace|/home/user)/[^\s]*\b', "", content)
    # Collapse whitespace
    content = " ".join(content.split())
    return {"source": chunk.get("source", ""), "content": content[:500]}


def _build_prompt(retrieved_chunks: List[Dict[str, Any]], question: str) -> str:
    """Construct system+user prompt around cleaned evidence."""
    system = (
        "You are a security questionnaire response assistant. Answer using ONLY "
        "the evidence provided below. Cite the evidence indices you used. If the "
        "evidence does not support a confident answer, say so explicitly — do not "
        "invent claims. Respond as raw JSON: {\"answer_text\": str, "
        "\"confidence\": \"high\"|\"medium\"|\"low\"|\"insufficient_evidence\", "
        "\"cited_indices\": [int]}"
    )
    cleaned = [_sanitise_chunk(c) for c in retrieved_chunks]
    evidence = "\n".join(f"[{i}] (source: {e['source']}) {e['content']}" for i, e in enumerate(cleaned))
    user = f"<evidence>\n{evidence}\n</evidence>\n\nQUESTION: {question}"
    return f"{system}\n\n{user}"


class AnswerDraft(BaseModel):
    """Validated draft output for a single questionnaire question."""
    question_id: str
    answer_text: str
    confidence: str  # "high" | "medium" | "low" | "insufficient_evidence"
    source_evidence_ids: List[str]
    word_count: int

    @field_validator("answer_text")
    @classmethod
    def not_empty_or_error_string(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("answer_text must not be empty")
        if v.startswith(("BLOCKED:", "Error:")):
            raise ValueError(f"LLM returned error string: {v[:80]}")
        if len(v) > _MAX_ANSWER_LENGTH:
            raise ValueError(f"answer_text exceeds max length {_MAX_ANSWER_LENGTH}")
        return v

    @model_validator(mode="after")
    def grounded_or_flagged(self) -> "AnswerDraft":
        # Critical Failure Mode #1/#4: confident answer with zero cited evidence is hallucination
        if not self.source_evidence_ids and self.confidence != "insufficient_evidence":
            raise ValueError(
                "answer has no source_evidence_ids but confidence != 'insufficient_evidence'"
            )
        return self


async def draft_answer_for_question(
    question_id: str,
    question_text: str,
    tenant_id: str,
    db,
    question_set_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve tenant evidence, draft a grounded answer, hold for human review.

    Clone compliance_narrative_service.py's "Pydantic-validated output + fallback"
    pattern. Guardrail_service already wraps ai_service.generate_text under
    the tenant_context set by the caller.
    """
    set_tenant_id(tenant_id)

    # 1. Retrieve (tenant-scoped; rag_service.query is synchronous)
    retrieved = rag_service.query(question_text, _MAX_CHUNKS, tenant_id)
    if not retrieved:
        return await _insufficient_evidence_draft(question_id, tenant_id, question_text, question_set_id, db=db)

    # 2. Build prompt & generate
    prompt = _build_prompt(retrieved, question_text)
    raw = await ai_service.generate_text(prompt, source="questionnaire_auto_answer")

    # 3. Guardrail: BLOCKED:/Error: strings route to insufficient evidence
    if raw.startswith(("BLOCKED:", "Error:")):
        return await _insufficient_evidence_draft(
            question_id, tenant_id, question_text, question_set_id, reason=raw[:120], db=db
        )

    # 4. Parse JSON robustly
    try:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)
        answer_text = parsed.get("answer_text", "")
        confidence = parsed.get("confidence", "")
        cited_indices = parsed.get("cited_indices", [])
        # map indices to source strings
        cited = [retrieved[i]["source"] for i in cited_indices if i < len(retrieved)]
        # Validate, create AnswerDraft, enforce grounded rules
        draft = AnswerDraft(
            question_id=question_id,
            answer_text=answer_text,
            confidence=confidence,
            source_evidence_ids=cited,
            word_count=len(answer_text.split()),
        )
    except (ValidationError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("[QuestionnaireAutoAnswer] validation/JSON failed: %s", exc)
        return await _insufficient_evidence_draft(
            question_id, tenant_id, question_text, question_set_id, reason=str(exc)[:120], db=db
        )

    # 5. Insert draft with pending_review status (hard T3 guard: never auto-submitted)
    draft_doc = {
        "id": f"qad-{uuid.uuid4().hex}",
        "tenantId": tenant_id,
        "questionSetId": question_set_id,
        "questionId": question_id,
        "questionText": question_text,
        "answerText": draft.answer_text,
        "original_answer_text": draft.answer_text,
        "confidence": draft.confidence,
        "sourceEvidenceIds": draft.source_evidence_ids,
        "sourceEvidence": [
            {"source": c.get("source", ""), "content": c.get("content", "")}
            for c in retrieved
        ],
        "status": "pending_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
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
    doc = {
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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if reason:
        doc["reason"] = reason
    # Still insert to allow reviewer to see "insufficient evidence" as a draft record
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