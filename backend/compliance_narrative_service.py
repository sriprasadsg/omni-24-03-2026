"""
Phase 13 / Phase 39-09 — AI Compliance Narrative Service (LangChain shim).

`generate_executive_summary`/`generate_framework_narrative` keep their exact
pre-39-09 signatures and `str` return type (with two new *optional* trailing
`tenant_id`/`db` kwargs — see below) so `enrich_report_data`,
`scheduled_reports_service`, and the reportlab render path (`_render_narratives`)
need no change (39-CONTEXT.md: "internals swap to LangChain paths"). Both now
delegate to `ai_orchestration.agents.narrative` — a `create_agent`-based
agent producing schema-validated `NarrativeOutput` (39-03) — replacing the
old `ai_service.generate_text` + regex/word-trim path.

`tenant_id`/`db`: `enrich_report_data` already has both as real parameters
(not ambient context) and passes them explicitly to the agent layer per
RESEARCH Pitfall B ("pass tenant_id explicitly rather than relying on
ambient context"). The two trailing kwargs default to `None` so any other
existing caller of `generate_executive_summary`/`generate_framework_narrative`
keeps working unchanged — in that case tenant/db are resolved from ambient
`tenant_context.get_tenant_id()` / `database.get_database()`, mirroring
`ai_auditor_service.py`'s shim (39-06).

The fail-closed contract is unchanged: a validation failure, guardrail
block, framework-fidelity flag, or agent/gateway exception all resolve to
the same deterministic fallback narrative string inside
`ai_orchestration.agents.narrative` — this module never lets a model/gateway
failure hard-fail report generation, and the `try/except` below is an extra
safety net around ambient tenant/db resolution itself, not the primary
guarantee.

`NarrativeOutput` and `_sanitise` are re-exported from
`ai_orchestration.schemas`/`ai_orchestration.agents.narrative` for backward
compatibility with any caller (including this module's own pre-existing
test suite) that still imports them from this module's pre-39-09 location.
"""
import logging
from typing import Any, Optional

from ai_orchestration.agents.narrative import (
    _sanitise,  # noqa: F401 — backward-compat re-export
    _fallback_executive_summary,
    generate_executive,
    generate_framework,
)
from ai_orchestration.schemas import NarrativeOutput  # noqa: F401 — backward-compat re-export
from tenant_context import get_tenant_id, set_tenant_id

logger = logging.getLogger(__name__)

_CATEGORY_SEVERITY = {
    "Access Control": "Critical", "Cryptography": "Critical", "Incident Response": "Critical",
    "Audit": "High", "Configuration": "High", "Vulnerability": "High",
    "Operations": "Medium", "Risk Management": "Medium",
}
_SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def _resolve_tenant_and_db(tenant_id: Optional[str], db: Any) -> tuple:
    """Resolve tenant_id/db from ambient context when a caller does not
    supply them explicitly — mirrors `ai_auditor_service.py`'s shim
    (39-06). Callers that already have both (e.g. `enrich_report_data`)
    should always pass them explicitly per RESEARCH Pitfall B."""
    if tenant_id is None:
        tenant_id = get_tenant_id()
    if db is None:
        from database import get_database

        db = get_database()
    return tenant_id, db


async def generate_executive_summary(
    framework_name: str,
    score: float,
    failing_controls: list,
    period: str,
    tenant_id: Optional[str] = None,
    db: Any = None,
) -> str:
    resolved_tenant_id, resolved_db = _resolve_tenant_and_db(tenant_id, db)
    result = await generate_executive(
        framework_name, score, failing_controls, period, resolved_tenant_id, resolved_db
    )
    return result.text


async def generate_framework_narrative(
    framework_name: str,
    score: float,
    failing_controls: list,
    remediation_summary,
    tenant_id: Optional[str] = None,
    db: Any = None,
) -> str:
    resolved_tenant_id, resolved_db = _resolve_tenant_and_db(tenant_id, db)
    result = await generate_framework(
        framework_name, score, failing_controls, remediation_summary, resolved_tenant_id, resolved_db
    )
    return result.text


async def enrich_report_data(data: dict, db, tenant_id: str) -> None:
    # The tenant-scoped `db.asset_compliance.find(...)` below relies on ambient
    # context set by `tenant_context`. Set it explicitly here (rather than relying
    # on the one current caller to have done so already) so this function is
    # correct in isolation and fails closed if a future caller forgets.
    set_tenant_id(tenant_id)
    # Per-framework failing-controls lists, keyed by framework name (the only
    # identifier shared between this all-frameworks lookup and the tenant-scoped
    # `data["frameworks"]` entries built in `_generate_report`, which carry only
    # "name"/"score"). Kept as a local — not stored on `data` — so it doesn't leak
    # into the generic metrics table / HTML / JSON report exports.
    failing_by_framework: dict = {}
    try:
        frameworks = await db._db.compliance_frameworks.find({}).to_list(length=50)
        control_id_to_name: dict = {}
        control_id_to_severity: dict = {}
        control_id_to_framework: dict = {}
        for fw in frameworks:
            fw_key = fw.get("name") or str(fw.get("id") or fw.get("_id") or "")
            for ctrl in fw.get("controls", []):
                cid = str(ctrl.get("id") or ctrl.get("_id") or "")
                if cid:
                    control_id_to_name[cid] = ctrl.get("name", cid)
                    category = ctrl.get("category", "")
                    control_id_to_severity[cid] = _CATEGORY_SEVERITY.get(category, "Low")
                    control_id_to_framework[cid] = fw_key
        if not control_id_to_name:
            logger.warning(
                "[NarrativeService] No controls found in compliance_frameworks"
                " — top_failing_controls will be empty"
            )
        failing_docs = await db.asset_compliance.find(
            {
                "controlId": {"$in": list(control_id_to_name.keys())},
                "status": {"$in": ["Non-Compliant", "Fail", "Failed",
                                   "Not Implemented", "fail", "failed"]},
            }
        ).to_list(length=50)
        # `db.asset_compliance.find(...)` above has no explicit sort, so a control
        # name that appears more than once in the (unordered) result set must keep
        # its *most severe* occurrence — not merely the first one encountered —
        # for the ranking to be deterministic and correct regardless of DB return
        # order.
        best_severity: dict = {}  # name -> lowest (= most severe) _SEVERITY_ORDER seen
        best_severity_by_fw: dict = {}  # fw_key -> {name: lowest severity order seen}
        for doc in failing_docs:
            cid = str(doc.get("controlId", ""))
            name = control_id_to_name.get(cid, cid)
            sev_order = _SEVERITY_ORDER.get(control_id_to_severity.get(cid, "Low"), 3)
            fw_key = control_id_to_framework.get(cid)
            if not name:
                continue
            if name not in best_severity or sev_order < best_severity[name]:
                best_severity[name] = sev_order
            if fw_key is not None:
                fw_map = best_severity_by_fw.setdefault(fw_key, {})
                if name not in fw_map or sev_order < fw_map[name]:
                    fw_map[name] = sev_order
        sorted_controls = sorted(best_severity.items(), key=lambda kv: kv[1])
        data["top_failing_controls"] = [n for n, _ in sorted_controls[:7]]
        failing_by_framework = {
            fw_key: [n for n, _ in sorted(fw_map.items(), key=lambda kv: kv[1])[:7]]
            for fw_key, fw_map in best_severity_by_fw.items()
        }
    except Exception as exc:
        logger.warning("[NarrativeService] Failed to fetch failing controls: %s", exc)
        data["top_failing_controls"] = []
        failing_by_framework = {}

    try:
        fw_list = data.get("frameworks", [])
        primary = fw_list[0] if fw_list else {}
        period = f"{data.get('period_start', '')} to {data.get('period_end', '')}"
        data["ai_executive_summary"] = await generate_executive_summary(
            framework_name=primary.get("name", "N/A"),
            score=float(primary.get("score", 0.0)),
            failing_controls=data.get("top_failing_controls", []),
            period=period,
            tenant_id=tenant_id,
            db=db,
        )
    except Exception as exc:
        logger.warning("[NarrativeService] Executive summary failed: %s", exc)
        fw_name = (
            data["frameworks"][0].get("name", "N/A") if data.get("frameworks") else "N/A"
        )
        data["ai_executive_summary"] = _fallback_executive_summary(fw_name, 0.0)

    narratives: dict = {}
    for fw in data.get("frameworks", []):
        fw_name = fw.get("name", "")
        try:
            score = float(fw.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        try:
            narratives[fw_name] = await generate_framework_narrative(
                framework_name=fw_name,
                score=score,
                failing_controls=failing_by_framework.get(fw_name, []),
                remediation_summary=None,
                tenant_id=tenant_id,
                db=db,
            )
        except Exception as exc:
            logger.warning("[NarrativeService] Framework narrative failed for %s: %s", fw_name, exc)
    data["ai_framework_narratives"] = narratives


def _render_narratives(story: list, report_data: dict, styles, section: str = "all") -> None:
    from reportlab.platypus import Paragraph, Spacer
    import html as _html
    if section in ("executive", "all"):
        ai_summary = report_data.get("ai_executive_summary", "")
        if ai_summary:
            story.append(Paragraph("Executive Summary", styles["Heading2"]))
            story.append(Paragraph(_html.escape(ai_summary, quote=False), styles["Normal"]))
            story.append(Spacer(1, 12))
    if section in ("frameworks", "all"):
        for fw_name, narrative in report_data.get("ai_framework_narratives", {}).items():
            if narrative:
                story.append(Spacer(1, 8))
                story.append(Paragraph(f"{_html.escape(fw_name, quote=False)} — Findings", styles["Heading2"]))
                story.append(Paragraph(_html.escape(narrative, quote=False), styles["Normal"]))
