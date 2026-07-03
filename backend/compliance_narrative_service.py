"""
Phase 13 — AI Compliance Narrative Service.
Generates LLM-backed executive summaries and per-framework narratives for scheduled PDF reports.
"""
import re
import html as _html
import logging
from pydantic import BaseModel, field_validator, model_validator, ValidationError

from ai_service import ai_service
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[<>{}\[\]\\]")
_NEWLINES = re.compile(r"[\r\n]+")

_CATEGORY_SEVERITY = {
    "Access Control": "Critical", "Cryptography": "Critical", "Incident Response": "Critical",
    "Audit": "High", "Configuration": "High", "Vulnerability": "High",
    "Operations": "Medium", "Risk Management": "Medium",
}
_SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def _sanitise(value: str, max_len: int = 200) -> str:
    # Collapse embedded newlines first so a crafted control/framework name can't
    # inject new "instruction" lines inside the <compliance_data> block.
    value = _NEWLINES.sub(" ", str(value))
    return _UNSAFE.sub("", value).strip()[:max_len]


def _trim_to_words(text: str, limit: int) -> str:
    words = text.split()
    return " ".join(words[:limit]) if len(words) > limit else text


class NarrativeOutput(BaseModel):
    text: str
    word_count: int
    limit: int = 200

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("narrative text must not be empty")
        if v.startswith(("BLOCKED:", "Error:")):
            raise ValueError(f"LLM returned error string: {v[:80]}")
        return v

    @model_validator(mode="after")
    def within_budget(self) -> "NarrativeOutput":
        # `limit` is the call-site-specific budget (executive: 150 words,
        # framework: 200 words). _trim_to_words is the primary enforcer;
        # this validator catches any bypass against the *actual* limit that
        # applies, rather than a shared hardcoded ceiling.
        if self.word_count > self.limit:
            raise ValueError(
                f"narrative exceeds word budget: {self.word_count} words (limit {self.limit})"
            )
        return self

    @classmethod
    def from_raw(cls, raw: str, limit: int = 200) -> "NarrativeOutput":
        words = raw.split()
        return cls(text=raw.strip(), word_count=len(words), limit=limit)


def _validated_narrative(raw: str, fallback: str, limit: int = 200) -> str:
    try:
        output = NarrativeOutput.from_raw(raw, limit=limit)
        return output.text
    except ValidationError as exc:
        logger.warning("[NarrativeService] Pydantic validation failed: %s", exc)
        return fallback


def _fallback_executive_summary(framework: str, score: float) -> str:
    return (
        f"This report presents the {framework} compliance posture for the reporting period. "
        f"The overall compliance score is {score:.1f}%. "
        "Detailed findings are available in the per-framework section below. "
        "Please review the failing controls and engage your compliance team for remediation guidance."
    )


async def generate_executive_summary(
    framework_name: str,
    score: float,
    failing_controls: list,
    period: str,
) -> str:
    safe_fw = _sanitise(framework_name)
    safe_controls = [_sanitise(c, 80) for c in failing_controls[:5]]
    controls_block = "\n".join(f"- {c}" for c in safe_controls) or "- None recorded"
    fallback = _fallback_executive_summary(safe_fw, score)
    system_part = (
        "You are a compliance analyst writing an executive summary for a PDF report. "
        "Write in clear, non-technical prose suitable for a C-level audience. "
        "Do not invent control names, scores, or findings not present in the data below. "
        "Respond with the summary text only — no preamble, no markdown, no bullet points."
    )
    user_part = (
        f"<compliance_data>\nFramework: {safe_fw}\nCompliance score: {score:.1f}%\n"
        f"Reporting period: {period}\nTop failing controls:\n{controls_block}\n"
        "</compliance_data>\n\nWrite an executive summary of no more than 150 words."
    )
    result = await ai_service.generate_text(
        f"{system_part}\n\n{user_part}", source="compliance_narrative"
    )
    if result.startswith(("BLOCKED:", "Error:")):
        logger.warning("[NarrativeService] generate_text failed: %s", result[:80])
        return fallback
    trimmed = _trim_to_words(result.strip(), 150)
    return _validated_narrative(trimmed, fallback, limit=150)


async def generate_framework_narrative(
    framework_name: str,
    score: float,
    failing_controls: list,
    remediation_summary,
) -> str:
    safe_fw = _sanitise(framework_name)
    safe_controls = [_sanitise(c, 80) for c in failing_controls[:7]]
    ctrl_block = "\n".join(f"- {c}" for c in safe_controls) or "- None recorded"
    safe_rem = _sanitise(str(remediation_summary or ""), 300) or "None provided"
    fallback = (
        f"The {safe_fw} framework scored {score:.1f}%. "
        "Detailed findings are available in the attached control table."
    )
    system_part = (
        "You are a compliance analyst writing a findings narrative for a PDF report. "
        "Write factual, concise prose. Do not reference controls not listed below. "
        "Respond with narrative text only — no headings, no markdown."
    )
    user_part = (
        f"<compliance_data>\nFramework: {safe_fw}\nScore: {score:.1f}%\n"
        f"Failing controls:\n{ctrl_block}\nRemediation notes: {safe_rem}\n"
        "</compliance_data>\n\nWrite a findings narrative of no more than 200 words."
    )
    result = await ai_service.generate_text(
        f"{system_part}\n\n{user_part}", source="compliance_narrative_framework"
    )
    if result.startswith(("BLOCKED:", "Error:")):
        logger.warning("[NarrativeService] framework generate_text failed: %s", result[:80])
        return fallback
    trimmed = _trim_to_words(result.strip(), 200)
    return _validated_narrative(trimmed, fallback, limit=200)


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
        seen: set = set()
        sorted_controls: list = []
        seen_by_fw: dict = {}
        raw_by_fw: dict = {}
        for doc in failing_docs:
            cid = str(doc.get("controlId", ""))
            name = control_id_to_name.get(cid, cid)
            sev = control_id_to_severity.get(cid, "Low")
            fw_key = control_id_to_framework.get(cid)
            if name and name not in seen:
                seen.add(name)
                sorted_controls.append((_SEVERITY_ORDER.get(sev, 3), name))
            if name and fw_key is not None:
                fw_seen = seen_by_fw.setdefault(fw_key, set())
                if name not in fw_seen:
                    fw_seen.add(name)
                    raw_by_fw.setdefault(fw_key, []).append((_SEVERITY_ORDER.get(sev, 3), name))
        sorted_controls.sort(key=lambda x: x[0])
        data["top_failing_controls"] = [n for _, n in sorted_controls[:7]]
        failing_by_framework = {
            fw_key: [n for _, n in sorted(lst, key=lambda x: x[0])[:7]]
            for fw_key, lst in raw_by_fw.items()
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
            )
        except Exception as exc:
            logger.warning("[NarrativeService] Framework narrative failed for %s: %s", fw_name, exc)
    data["ai_framework_narratives"] = narratives


def _render_narratives(story: list, report_data: dict, styles, section: str = "all") -> None:
    from reportlab.platypus import Paragraph, Spacer
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
