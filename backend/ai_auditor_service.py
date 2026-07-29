"""Compliance AI Auditor — LangChain compatibility shim (Phase 39-06).

`get_auditor()`/`LocalAIAuditor.evaluate_evidence(framework_name, control_desc,
evidence_text)` keep their exact pre-existing signature and return shape
(`{verified, reasoning, raw_response, evaluatedAt}`) so `ai_auditor_endpoints.py`
and its Mongo write path (`evaluation_record = {..., "model_used": auditor.model_id}`)
need no change (39-CONTEXT.md: "internals swap to LangChain paths"). Internally
this now delegates to `ai_orchestration.agents.auditor.evaluate_control` — a
`create_agent`-based agent with citation validation, guardrails, and
provenance (Phase 39-06) — replacing the old raw VERDICT/REASONING text
parse and its bespoke local-Ollama-provider-selection logic.

Fail-closed contract preserved: any agent exception, or a downgraded
`insufficient_evidence` finding, returns `verified: False` with a reasoning
string — this shim never raises into `ai_auditor_endpoints.py`'s background
task, and never presents a fallback-model `pass` finding as equivalent to a
primary-model one (Failure Mode 5): those are mapped to `verified: False`
with an explicit `NEEDS_REVIEW` marker in `reasoning`, since the legacy
boolean contract has no third "pending human review" state to hold.

`evaluate_evidence`'s acting tenant/db handle come from ambient request
context (`tenant_context.get_tenant_id()` / `database.get_database()`) rather
than new required parameters — set by the same auth middleware
`ai_auditor_endpoints.py`'s dependencies already populate, so the endpoint's
call signature is unchanged.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("ai_auditor")


class LocalAIAuditor:
    """Thin async wrapper delegating to the LangChain auditor agent."""

    def __init__(self) -> None:
        # Filled in after each evaluation with the model_provenance string
        # ("primary" / "fallback:<model>") so ai_auditor_endpoints.py's
        # `evaluation_record["model_used"] = auditor.model_id` keeps working.
        self.model_id = "langchain-auditor"

    async def evaluate_evidence(
        self,
        framework_name: str,
        control_desc: str,
        evidence_text: str,
        control_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()

        try:
            from ai_orchestration.agents.auditor import evaluate_control
            from database import get_database
            from tenant_context import get_tenant_id

            tenant_id = get_tenant_id()
            db = get_database()

            result = await evaluate_control(
                framework_name=framework_name,
                control_desc=control_desc,
                evidence_text=evidence_text,
                tenant_id=tenant_id,
                db=db,
                control_id=control_id,
            )
        except Exception as e:
            logger.error("AI auditor (LangChain) inference failed: %s", e)
            return {
                "verified": False,
                "reasoning": f"AI auditor inference error: {e}",
                "raw_response": "",
                "evaluatedAt": now,
            }

        finding = result.finding
        self.model_id = result.model_provenance

        if result.needs_review:
            # Failure Mode 5: a fallback-provenance pass must never be
            # silently equal to a primary pass — fail closed to verified=False
            # with an explicit marker rather than auto-applying the score.
            verified = False
            reasoning = f"NEEDS_REVIEW (fallback model): {finding.rationale}"
        else:
            verified = finding.status == "pass"
            reasoning = finding.rationale

        raw_response = (
            f"control_id={finding.control_id} status={finding.status} "
            f"citations={len(finding.citations)} "
            f"citation_validation={result.citation_validation} "
            f"model_provenance={result.model_provenance}"
        )

        return {
            "verified": verified,
            "reasoning": reasoning,
            "raw_response": raw_response,
            "evaluatedAt": now,
            "model_used": result.model_provenance,
        }


# Singleton instance
_auditor_instance = None


def get_auditor() -> LocalAIAuditor:
    global _auditor_instance
    if _auditor_instance is None:
        _auditor_instance = LocalAIAuditor()
    return _auditor_instance
