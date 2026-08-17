"""AI auditor entry point (replacing deprecated ai_auditor_service.py).

Exposes `audit_control` and `generate_narrative` async functions used by
endpoints and by scheduled jobs. Delegates heavy lifting to
`ai_orchestration.agents.auditor.evaluate_control` which implements
the LangChain agent evaluation flow described in 39-AI-SPEC.md.

All execution failures degrade gracefully: log error, fallback to
static templates where appropriate, and surface generic diagnostics to
clients without exposing raw stack traces.
"""
import logging
from typing import Optional

from datetime import datetime
from uuid import uuid4

from ai_orchestration.decision_log import log_ai_decision
from ai_orchestration.guardrails import cross_tenant_output_scan, scan_input, scan_output
from ai_orchestration.memory import make_thread_id
from ai_orchestration.validators import extract_control_id_tokens, validate_citations
from ai_orchestration.models import build_model_for_tenant
from ai_orchestration.schemas import AuditFinding, Citation

logger = logging.getLogger(__name__)

async def audit_control(
    framework_name: str,
    control_desc: str,
    evidence_text: str,
    tenant_id: Optional[str],
    db: Any,
    control_id: Optional[str] = None,
) -> AuditFinding:
    """
    Evaluate a single control using the LangChain auditor agent (39-01).
    Returns an `AuditFinding` structured output, validated against schema.
    Errors are caught and translated to conservative failures (insufficient_evidence)
    with clear diagnostic messages.
    """
    try:
        from .agents.auditor import evaluate_control  # Lazily imported agent
        result = await evaluate_control(
            framework_name=framework_name,
            control_desc=control_desc,
            evidence_text=evidence_text,
            tenant_id=tenant_id,
            db=db,
            control_id=control_id,
        )
        # result is AuditEvaluationResult dataclass; we only need .finding
        return result.finding
    except Exception as exc:
        logger.error(
            "[audit_control] unexpected failure for tenant=%s framework=%s control=%s",
            tenant_id, framework_name, control_desc, exc, exc_info=True
        )
        # Fail-closed: return a structured Finding with insufficient_evidence
        finding = AuditFinding(
            control_id=control_id or extract_control_id_tokens(control_desc)[0]
            if control_desc
            else "UNKNOWN",
            status="insufficient_evidence",
            rationale="Failed to evaluate due to internal error (audit engine down).",
            citations=[Citation(source="ai_auditor_service.py", chunk_id="n/a")],
        )
        return finding

async def generate_narrative(
    framework_name: str,
    controls_summary: dict,
    tenant_id: Optional[str] = None,
) -> str:
    """
    Generate an AI-written executive summary (≤ 150 words) for a scheduled
    compliance report. Uses the draft_report_agent defined in
    `compliance_narrative_service.py`; any failure logs and returns a
    static template so report delivery never crashes.
    """
    try:
        from compliance_narrative_service import generate_report_text
        return generate_report_text(
            framework_summary=controls_summary,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.error("[generate_narrative] failed: %s", exc)
        # Return minimal fallback template
        return ("Compliance report generated, but narrative generation "
                "failed due to an internal issue. The evaluation data is "
                "still available on the Reports page.")
