"""Phase 39-05 — Online guardrail hooks wrapping every agent `ainvoke`.

Reuses the existing `guardrail_service.scan_and_log` stack for input/output
scanning — does NOT re-implement PII/injection scanning here (AI-SPEC
Section 6). Adds one net-new structural check, `cross_tenant_output_scan`,
as belt-and-braces defense on top of the tenant-closed tools in
`tools/retrieval.py`/`tools/evidence.py`.

These are thin hooks around the agent call — they do NOT route through the
existing `ai_service` generic-generation entry point (that would double-wrap
retries/circuit-breaking around the agent's own model call; RESEARCH.md
Anti-Pattern).
"""
import logging
from dataclasses import dataclass, field

from guardrail_service import guardrail_service

logger = logging.getLogger(__name__)


@dataclass
class GuardrailCheckResult:
    """Small result object the agent layer can act on — mirrors the shape of
    the existing `guardrail_service.GuardrailResult` (passed + findings)."""

    passed: bool
    findings: list[str] = field(default_factory=list)
    reason: str = ""


async def scan_input(text: str, surface: str) -> GuardrailCheckResult:
    """Pre-`ainvoke` hook: PII/injection scan on user input before it reaches the model."""
    scan = await guardrail_service.scan_and_log(text, f"{surface}_input")
    if not scan.passed:
        return GuardrailCheckResult(
            passed=False, findings=scan.findings, reason="input_guardrail_blocked"
        )
    return GuardrailCheckResult(passed=True)


async def scan_output(text: str, surface: str) -> GuardrailCheckResult:
    """Post-`ainvoke` hook: PII/injection scan on the agent's raw output text."""
    scan = await guardrail_service.scan_and_log(text, f"{surface}_output")
    if not scan.passed:
        return GuardrailCheckResult(
            passed=False, findings=scan.findings, reason="output_guardrail_blocked"
        )
    return GuardrailCheckResult(passed=True)


async def cross_tenant_output_scan(text: str, tenant_id: str, db) -> GuardrailCheckResult:
    """Belt-and-braces structural check: block if any OTHER tenant's identifier
    (id or name, from the `db.tenants` registry) appears in agent output text.

    This sits on top of — never instead of — `tenant_id` being closed over in
    every tool factory (T-39-05-A). A hit here is a confidentiality incident
    (AI-SPEC Section 6: "Block + page"), never a quality bug. `db.tenants` is
    tenant-isolation-EXEMPT global reference data (`database.py`), so this
    read is intentionally unscoped.

    On a lookup failure this fails OPEN (logs loudly, does not block the
    response) — this scan is defense-in-depth on top of the structural
    tenant-closure mitigation, not the sole control, so an infra hiccup here
    must not itself become an availability incident.
    """
    try:
        other_tenants = await db.tenants.find(
            {"id": {"$ne": tenant_id}}, {"id": 1, "name": 1, "_id": 0}
        ).to_list(length=None)
    except Exception as exc:
        logger.error("[Guardrails] cross_tenant_output_scan lookup failed: %s", exc)
        return GuardrailCheckResult(passed=True)

    lowered = text.lower()
    for other in other_tenants:
        for identifier in (other.get("id"), other.get("name")):
            if identifier and str(identifier).lower() in lowered:
                logger.error(
                    "[Guardrails] SECURITY INCIDENT: cross-tenant identifier '%s' "
                    "found in output generated for tenant '%s'",
                    identifier, tenant_id,
                )
                return GuardrailCheckResult(
                    passed=False,
                    findings=[f"cross_tenant_identifier:{identifier}"],
                    reason="cross_tenant_output_blocked",
                )
    return GuardrailCheckResult(passed=True)
