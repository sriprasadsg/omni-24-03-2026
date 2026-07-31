"""Phase 39-05 — Shared AI-decision audit-log writer (Option (a), RESEARCH Pitfall D).

`log_ai_decision` writes a surface-discriminated decision document into the
EXISTING decision-audit collection (`source="langchain"`) rather than a new
collection — reusing its indexes, tenant scoping, and no-TTL retention
(SOC 2 CC6.1). It deliberately omits the per-agent discriminator field and
the tool-name field that the pre-existing agentic decision reader
(`agentic_tasks_endpoints.py`'s dashboard-read route) filters its lookups on
— so a document written by this module can never satisfy that reader's query
shape and therefore never surfaces there. See this plan's objective
(39-05-PLAN.md) for the full reconciliation rationale and the reader-compat
test in `test_ai_orchestration_substrate.py`.

Mirrors `agentic_service.py::_log_decision`'s never-re-raise contract: any
insert failure is logged at ERROR ("AUDIT WRITE FAILURE") and swallowed —
audit failure must never block an agent response. Does NOT set `tenantId`
manually; `TenantIsolatedCollection` auto-injects it from ambient request
context (per the existing `_log_decision` docstring, T-12-05).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def log_ai_decision(
    db,
    surface: str,
    *,
    outcome: str,
    prompt_version: str,
    model_provenance: str = "primary",
    citation_validation: str = "",
    ref: Optional[dict[str, str]] = None,
    source: str = "langchain",
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> None:
    """Insert a Phase 39 surface-discriminated decision doc into `agent_ai_decisions`.

    Parameters
    ----------
    db: tenant-scoped database handle (TenantIsolatedCollection auto-injects tenantId).
    surface: one of "auditor" | "chat" | "questionnaire" | "narrative".
    outcome: e.g. "pass" | "fail" | "insufficient_evidence" | "blocked".
    prompt_version: the PROMPT_VERSION constant active for this generation (prompts.py).
    model_provenance: "primary" | "fallback:<model>" (ai_orchestration.models.model_provenance).
    citation_validation: "pass" | "blocked" (from validators.validate_citations).
    ref: surface-specific reference id, e.g. {"control_id": "AC-1"},
        {"question_id": "Q-1"}, or {"thread_id": "tenant-a:conv-1"}. Merged
        directly into the document — never a hardcoded key name so each
        surface can use its own natural reference field name.

    NEVER re-raises — any insert failure is logged loudly and swallowed so a
    decision-log failure can never block the surface's own agent response.
    """
    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "surface": surface,
        "source": source,
        "model_provenance": model_provenance,
        "prompt_version": prompt_version,
        "outcome": outcome,
        "citation_validation": citation_validation,
        "started_at": (started_at or now).isoformat(),
        "completed_at": (completed_at or now).isoformat(),
    }
    if ref:
        doc.update(ref)

    try:
        await db.agent_ai_decisions.insert_one(doc)
    except Exception as exc:
        # CRITICAL: never suppress silently — mirrors agentic_service.py's
        # Critical Failure Mode #3 handling.
        logger.error(
            "[AIOrchestration] AUDIT WRITE FAILURE for surface '%s' decision: %s",
            surface, exc,
        )
        # Do NOT re-raise — audit failure must not block an agent response.
