"""Shared validated-LLM-output Pydantic schemas for Phase 39 LangChain surfaces.

These are plain Pydantic models — no LangChain import here — consumed as
`response_format=` targets by `create_agent` (AI-SPEC Section 4b). They
generalize three pre-existing, independently hand-rolled validator shapes
found in this codebase (RESEARCH.md "Don't Hand-Roll"):

- `questionnaire_answer_draft_service.AnswerDraft` -> `CitedAnswer`
- `compliance_narrative_service.NarrativeOutput` -> `NarrativeOutput`
- `ai_auditor_service`'s line-based VERDICT/REASONING parser -> `AuditFinding`

Every schema here rejects the two guardrail sentinel error strings
(`BLOCKED:`, `Error:`) so a suppressed/blocked generation can never silently
pass through as a validated finding or answer, and every finding-shaped
schema requires at least one citation (`min_length=1`) — "no evidence
cited" is a validation failure here, not a silent hallucination.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

_ERROR_PREFIXES = ("BLOCKED:", "Error:")
_MAX_ANSWER_LENGTH = 2000


def _reject_empty_or_error_string(value: str, field_name: str) -> str:
    """Shared invariant: strip, reject empty, reject guardrail error strings.

    Generalizes `AnswerDraft.not_empty_or_error_string` and
    `NarrativeOutput.text_not_empty` verbatim in intent.
    """
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if value.startswith(_ERROR_PREFIXES):
        raise ValueError(f"{field_name} contains an LLM guardrail error string: {value[:80]}")
    return value


class Citation(BaseModel):
    """A single evidence citation backing a finding or answer."""

    source: str = Field(description="Source name from the [source] tag in retrieved evidence")
    chunk_id: str = Field(description="Chunk/evidence id from the [id] tag")


class AuditFinding(BaseModel):
    """A single control assessment produced by the AI auditor surface.

    `citations` requires at least one entry (`min_length=1`): the framework
    re-prompts the model rather than allowing an uncited finding to validate
    (AI-SPEC Section 4b/6, Critical Failure Mode 2).
    """

    control_id: str
    status: Literal["pass", "fail", "partial", "insufficient_evidence"]
    rationale: str
    citations: List[Citation] = Field(min_length=1, description="Evidence backing this finding")
    suggested_action: Optional[str] = None

    @field_validator("control_id")
    @classmethod
    def control_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("control_id must not be empty")
        return v

    @field_validator("rationale")
    @classmethod
    def rationale_not_empty_or_error(cls, v: str) -> str:
        return _reject_empty_or_error_string(v, "rationale")


class CitedAnswer(BaseModel):
    """Generalizes `questionnaire_answer_draft_service.AnswerDraft` for any
    surface (questionnaire, chat) answering a question grounded in tenant
    evidence, with an additional structured `citations` list alongside the
    original `source_evidence_ids`.
    """

    question_id: str
    answer_text: str
    confidence: Literal["high", "medium", "low", "insufficient_evidence"]
    source_evidence_ids: List[str] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)

    @field_validator("answer_text")
    @classmethod
    def answer_text_not_empty_or_error(cls, v: str) -> str:
        v = _reject_empty_or_error_string(v, "answer_text")
        if len(v) > _MAX_ANSWER_LENGTH:
            raise ValueError(f"answer_text exceeds max length {_MAX_ANSWER_LENGTH}")
        return v

    @model_validator(mode="after")
    def grounded_or_flagged(self) -> "CitedAnswer":
        # Critical Failure Mode #1/#4: a confident answer with zero cited
        # evidence is hallucination. Verbatim generalization of
        # `AnswerDraft.grounded_or_flagged`.
        if not self.source_evidence_ids and self.confidence != "insufficient_evidence":
            raise ValueError(
                "answer has no source_evidence_ids but confidence != 'insufficient_evidence'"
            )
        return self


class NarrativeOutput(BaseModel):
    """Generalizes `compliance_narrative_service.NarrativeOutput` for any
    free-text narrative surface with a per-call-site word budget."""

    text: str
    word_count: int
    limit: int = 200

    @field_validator("text")
    @classmethod
    def text_not_empty_or_error(cls, v: str) -> str:
        return _reject_empty_or_error_string(v, "text")

    @model_validator(mode="after")
    def within_budget(self) -> "NarrativeOutput":
        if self.word_count > self.limit:
            raise ValueError(
                f"narrative exceeds word budget: {self.word_count} words (limit {self.limit})"
            )
        return self

    @classmethod
    def from_raw(cls, raw: str, limit: int = 200) -> "NarrativeOutput":
        words = raw.split()
        return cls(text=raw.strip(), word_count=len(words), limit=limit)


class RoutingDecision(BaseModel):
    """Supervisor structured output — picks which agent surface should handle a
    free-form request and extracts whatever structured parameters the request
    carried. `surface` is the only required field; the params are best-effort
    and may be absent, in which case the supervisor degrades to `chat` rather
    than invoking a structured surface with missing inputs."""

    surface: Literal["chat", "auditor", "questionnaire", "narrative"] = Field(
        description="The single best agent surface to handle this request"
    )
    reason: str = Field(description="One sentence explaining the routing choice")
    framework_name: Optional[str] = Field(
        default=None, description="Compliance framework named in the request, if any (auditor/narrative)"
    )
    control_desc: Optional[str] = Field(
        default=None, description="The control requirement text to audit, if the request is an audit (auditor)"
    )
    question_text: Optional[str] = Field(
        default=None, description="The single questionnaire question to draft an answer for (questionnaire)"
    )
