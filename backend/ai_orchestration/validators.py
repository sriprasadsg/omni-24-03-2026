"""Shared citation + control-ID resolution validator (39-AI-SPEC Section 6).

One async `validate_citations` callable resolves every citation on a finding
or answer against the acting tenant's real evidence records, and resolves
`control_id` (when present) against the seeded framework registry — never a
hardcoded map (39-RESEARCH.md Pattern 3). This is the single guardrail the
auditor, questionnaire, and chat surfaces all call; do not fork per-surface
copies (39-RESEARCH.md "Don't Hand-Roll").

Resolution targets (RESEARCH Pattern 3 / `ai_auditor_endpoints.py`):
- `db.compliance_frameworks` — controls registry, the same
  `{c["id"]: c for c in framework.get("controls", [])}` shape
  `ai_auditor_endpoints.py` already builds.
- `db.control_evidence` / `db.asset_compliance` — the evidence collections
  the auditor endpoint already reads via `controlId $in [...]`.

All DB access here is tenant-scoped (acting tenant + the `global` KB) and
read-only — never an unfiltered `find` on either evidence collection.
"""
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

FAILURE_REASON = "citation_validation_failed"

# Heuristic control-ID-shaped token: 2-8 uppercase letters immediately
# followed by a hyphen+digits or digits directly (optionally dotted
# sub-parts) — e.g. "CIS-5.2", "AC-2", "CC6.1". Deliberately does NOT match
# a bare "<letters> <space> <number>" shape (e.g. "SOC 2", "ISO 27001")
# so a narrative merely *naming* a framework doesn't false-positive as a
# fabricated control ID. Used only to sweep free narrative/rationale text
# for tokens that look like control IDs (AI-SPEC Section 5 "framework
# fidelity" dimension) — not the source of truth for a finding's own
# `control_id` field.
_CONTROL_ID_TOKEN_RE = re.compile(r"\b[A-Z]{2,8}-\d+(?:\.\d+)*\b|\b[A-Z]{2,8}\d+(?:\.\d+)*\b")


@dataclass
class CitationValidationResult:
    """Outcome of a `validate_citations` / `validate_framework_fidelity` call."""

    ok: bool
    reason: Optional[str] = None
    detail: Optional[str] = None


def _normalize_control_id(control_id: str) -> str:
    return re.sub(r"\s+", "", str(control_id)).upper()


def _tenant_scope_query(tenant_id: str) -> dict:
    """Acting tenant + the shared `global` KB — never unscoped."""
    return {"$or": [{"tenantId": tenant_id}, {"tenantId": "global"}]}


async def _load_known_control_ids(tenant_id: str, db) -> set:
    """Load every control id from the tenant-scoped (+ global) framework
    registry — the same `compliance_frameworks` collection
    `ai_auditor_endpoints.py` already queries, never a static/hardcoded map.
    """
    frameworks = await db.compliance_frameworks.find(_tenant_scope_query(tenant_id)).to_list(
        length=200
    )
    known: set = set()
    for framework in frameworks:
        for control in framework.get("controls", []) or []:
            control_id = control.get("id")
            if control_id:
                known.add(_normalize_control_id(control_id))
    return known


async def _resolve_control_id(control_id: str, tenant_id: str, db) -> bool:
    known = await _load_known_control_ids(tenant_id, db)
    return _normalize_control_id(control_id) in known


async def _resolve_chunk_id(chunk_id: str, tenant_id: str, db) -> bool:
    """Resolve a citation's `chunk_id` against the tenant's (+ global)
    evidence records in `control_evidence` (manual uploads) and
    `asset_compliance` (system-collected evidence array)."""
    scope = _tenant_scope_query(tenant_id)

    manual = await db.control_evidence.find_one({"id": chunk_id, **scope})
    if manual:
        return True

    system = await db.asset_compliance.find_one({"evidence.id": chunk_id, **scope})
    return system is not None


def _downgrade(obj: Any) -> Any:
    """Return a copy of `obj` downgraded to `insufficient_evidence` — the
    caller must persist/display this copy instead of the original untrusted
    object (AI-SPEC Section 6: block + downgrade, never silently pass)."""
    if hasattr(obj, "status"):
        return obj.model_copy(update={"status": "insufficient_evidence"})
    if hasattr(obj, "confidence"):
        return obj.model_copy(update={"confidence": "insufficient_evidence"})
    return obj


async def validate_citations(obj: Any, tenant_id: str, db) -> Tuple[CitationValidationResult, Any]:
    """Resolve every citation on `obj` (and its `control_id`, if present)
    against real tenant evidence + the framework registry.

    `obj` is duck-typed: any `AuditFinding`/`CitedAnswer`-shaped object
    exposing a `.citations` list of `Citation`-shaped items (`.chunk_id`)
    and, optionally, a `.control_id`. On the first unresolvable citation or
    control_id, returns a failing result plus a downgraded copy of `obj`
    that the caller must persist/display in place of the original — never
    the unvalidated object.

    Returns:
        (result, possibly_downgraded_obj) — `result.ok` is False with
        `reason == FAILURE_REASON` on any unresolved id; the second element
        is `obj` unchanged when `result.ok` is True.
    """
    control_id = getattr(obj, "control_id", None)
    if control_id:
        if not await _resolve_control_id(control_id, tenant_id, db):
            return (
                CitationValidationResult(
                    ok=False,
                    reason=FAILURE_REASON,
                    detail=f"control_id '{control_id}' not found in compliance_frameworks registry",
                ),
                _downgrade(obj),
            )

    citations = getattr(obj, "citations", None) or []
    for citation in citations:
        chunk_id = getattr(citation, "chunk_id", None)
        if not chunk_id or not await _resolve_chunk_id(chunk_id, tenant_id, db):
            return (
                CitationValidationResult(
                    ok=False,
                    reason=FAILURE_REASON,
                    detail=f"citation chunk_id '{chunk_id}' does not resolve to tenant evidence",
                ),
                _downgrade(obj),
            )

    return CitationValidationResult(ok=True), obj


def extract_control_id_tokens(text: str) -> List[str]:
    """Regex-sweep free output text for control-ID-shaped tokens, independent
    of any structured `control_id` field (AI-SPEC Section 5 "framework
    fidelity": catches invented IDs mentioned only in prose/rationale)."""
    return _CONTROL_ID_TOKEN_RE.findall(text or "")


async def validate_framework_fidelity(
    text: str, tenant_id: str, db
) -> CitationValidationResult:
    """Validate every control-ID-shaped token found in free text against the
    tenant-scoped (+ global) framework registry. Returns ok=True when no
    such tokens are present — this is a sweep for *invented* IDs, not a
    requirement that narrative text mention any."""
    tokens = extract_control_id_tokens(text)
    if not tokens:
        return CitationValidationResult(ok=True)

    known = await _load_known_control_ids(tenant_id, db)
    unknown = sorted({t for t in tokens if _normalize_control_id(t) not in known})
    if unknown:
        return CitationValidationResult(
            ok=False,
            reason=FAILURE_REASON,
            detail=f"unrecognized control-ID-shaped token(s) not in registry: {unknown}",
        )
    return CitationValidationResult(ok=True)
