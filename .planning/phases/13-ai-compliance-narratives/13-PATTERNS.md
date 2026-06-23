# Phase 13: AI Compliance Narratives — Pattern Map

**Mapped:** 2026-06-23
**Files analyzed:** 4
**Analogs found:** 4 / 4

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/compliance_narrative_service.py` | service | request-response (LLM) | `backend/agentic_service.py` | role-match (same: singleton import, Pydantic v2 validation, fallback pattern, `generate_text` delegation) |
| `backend/scheduled_reports_service.py` | service | CRUD + batch | self (already exists) | exact — modify existing |
| `backend/ai_service.py` | service | request-response | self (already exists, read-only pattern source) | exact |
| `backend/tests/test_compliance_narrative_service.py` | test | — | `backend/tests/test_agentic_ai.py` | exact (asyncio.run pattern, AsyncMock, lazy imports inside test methods) |

---

## Pattern Assignments

### `backend/compliance_narrative_service.py` (new service, LLM request-response)

**Status:** ALREADY IMPLEMENTED (lines 1–230 exist). Pattern map is for reference and verification.

**Analog:** `backend/agentic_service.py`

**Imports pattern** (`compliance_narrative_service.py` lines 1–11):
```python
import re
import logging
from pydantic import BaseModel, field_validator, ValidationError

from ai_service import ai_service   # module-level IncidentAnalyzer singleton (ai_service.py line 500)

logger = logging.getLogger(__name__)
```

**Pydantic v2 validation pattern** (`agentic_service.py` uses same `field_validator` / `ValidationError` pattern):
```python
# From agentic_service.py lines 28-29 (import):
from pydantic import BaseModel, field_validator, ValidationError

# NarrativeOutput pattern (compliance_narrative_service.py lines 32–58):
class NarrativeOutput(BaseModel):
    text: str
    word_count: int

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("narrative text must not be empty")
        if v.startswith(("BLOCKED:", "Error:")):
            raise ValueError(f"LLM returned error string: {v[:80]}")
        return v

    @field_validator("word_count")
    @classmethod
    def within_budget(cls, v: int) -> int:
        if v > 200:
            raise ValueError(f"narrative exceeds word budget: {v} words")
        return v

    @classmethod
    def from_raw(cls, raw: str) -> "NarrativeOutput":
        words = raw.split()
        return cls(text=raw.strip(), word_count=len(words))
```

**Fallback / never-raise pattern** (analog: `agentic_service._rule_based_fallback`):
```python
# compliance_narrative_service.py lines 61–67
def _validated_narrative(raw: str, fallback: str) -> str:
    try:
        output = NarrativeOutput.from_raw(raw)
        return output.text
    except ValidationError as exc:
        logger.warning("[NarrativeService] Pydantic validation failed: %s", exc)
        return fallback
```

**Core `generate_text` call pattern** (`ai_service.py` lines 205–210 — only `prompt` and `source` passed):
```python
# compliance_narrative_service.py lines 100–107
result = await ai_service.generate_text(
    f"{system_part}\n\n{user_part}", source="compliance_narrative"
)
if result.startswith(("BLOCKED:", "Error:")):
    logger.warning("[NarrativeService] generate_text failed: %s", result[:80])
    return fallback
trimmed = _trim_to_words(result.strip(), 150)
return _validated_narrative(trimmed, fallback)
```

**Input sanitisation pattern** (`compliance_narrative_service.py` lines 13–24):
```python
_UNSAFE = re.compile(r"[<>{}\[\]\\]")

def _sanitise(value: str, max_len: int = 200) -> str:
    return _UNSAFE.sub("", str(value)).strip()[:max_len]
```

**`enrich_report_data` — data enrichment entry point** (lines 144–213):
- Called from `scheduled_reports_service._generate_report` with one `await`
- Queries `db._db.compliance_frameworks` (raw Motor) for control metadata
- Queries `db.asset_compliance` with status filter for failing controls
- Populates `data["top_failing_controls"]`, `data["ai_executive_summary"]`, `data["ai_framework_narratives"]`
- All three blocks wrapped in `try/except Exception` — no exception propagates to caller

---

### `backend/scheduled_reports_service.py` (existing service, modified)

**Status:** ALREADY MODIFIED. Narrative injection is wired.

**Analog:** self

**`_generate_report` integration point** (lines 328–332 — the compliance_summary branch):
```python
# scheduled_reports_service.py lines 328-332
if report_type == "compliance_summary":
    frameworks = await db.compliance_frameworks.find({"tenant_id": tenant_id}).to_list(length=20)
    data["frameworks"] = [{"name": f.get("name"), "score": f.get("compliance_score", 0)} for f in frameworks]
    if not schedule.get("framework_id"):
        await enrich_report_data(data, db, tenant_id)
```

**`_build_pdf` narrative rendering** (lines 373–397):
```python
# After Spacer(1, 24) — before metrics Table:
_render_narratives(story, report_data, styles, section="executive")

# skip set — narrative keys excluded from metrics table:
skip = {"report_type", "report_name", "generated_at", "tenant_id", "period_start", "period_end",
        "ai_executive_summary", "ai_framework_narratives", "top_failing_controls"}

# After metrics Table:
_render_narratives(story, report_data, styles, section="frameworks")
```

**`_render_narratives` helper** (delegated to `compliance_narrative_service.py` lines 216–229):
```python
def _render_narratives(story: list, report_data: dict, styles, section: str = "all") -> None:
    from reportlab.platypus import Paragraph, Spacer
    if section in ("executive", "all"):
        ai_summary = report_data.get("ai_executive_summary", "")
        if ai_summary:
            story.append(Paragraph("Executive Summary", styles["Heading2"]))
            story.append(Paragraph(ai_summary, styles["Normal"]))
            story.append(Spacer(1, 12))
    if section in ("frameworks", "all"):
        for fw_name, narrative in report_data.get("ai_framework_narratives", {}).items():
            if narrative:
                story.append(Spacer(1, 8))
                story.append(Paragraph(f"{fw_name} — Findings", styles["Heading2"]))
                story.append(Paragraph(narrative, styles["Normal"]))
```

---

### `backend/ai_service.py` (pattern source, read-only)

**Singleton pattern** (line 500 — referenced by all callers):
```python
ai_service = IncidentAnalyzer()
```

**`generate_text` signature** (lines 205–210):
```python
async def generate_text(
    self,
    prompt: str,
    source: str = "generic",
    _retries: int = 3,
    provider: Optional[AIProvider] = None,
) -> str:
```

**BLOCKED/Error prefix convention** (lines 221, 294, 300):
- `"BLOCKED: ..."` — guardrail scan failed (input or output)
- `"Error: ..."` — generation failed after retries or circuit breaker open
- Callers must check `result.startswith(("BLOCKED:", "Error:"))` and return fallback

---

### `backend/tests/test_compliance_narrative_service.py` (new test, existing)

**Status:** ALREADY EXISTS (8 test classes).

**Analog:** `backend/tests/test_agentic_ai.py`

**Test file header pattern** (matches `test_agentic_ai.py` lines 1–17):
```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError
```

**Async test pattern — NO pytest-asyncio** (matches `test_agentic_ai.py` line 109):
```python
# test_compliance_narrative_service.py lines 22–40
class TestGenerateExecutiveSummary:
    def test_returns_str_on_success(self):
        async def run():
            with patch("compliance_narrative_service.ai_service") as mock_svc:
                mock_svc.generate_text = AsyncMock(
                    return_value="The SOC 2 compliance posture is sound."
                )
                from compliance_narrative_service import generate_executive_summary
                result = await generate_executive_summary(
                    framework_name="SOC 2",
                    score=85.0,
                    failing_controls=["CC6.1"],
                    period="2026-06-01 to 2026-06-23",
                )
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        assert isinstance(result, str)
        assert len(result.split()) <= 150
```

**Key rule:** Imports of the module under test happen INSIDE the `async def run()` closure (lazy import), not at the top of the test file. This enables TDD RED phase without cascading ImportError.

**Mock collection helper pattern** (from `test_scheduled_reports.py` lines 23–38 — reuse for integration tests):
```python
def _col():
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="fake-id"))
    _find_cursor = MagicMock()
    _find_cursor.to_list = AsyncMock(return_value=[])
    _find_cursor.sort = MagicMock(return_value=_find_cursor)
    col.find = MagicMock(return_value=_find_cursor)
    return col
```

---

## Shared Patterns

### Module-Level Logger
**Source:** Every backend service (`ai_service.py` line 15, `agentic_service.py` line 33)
**Apply to:** `compliance_narrative_service.py`
```python
logger = logging.getLogger(__name__)
```

### Fallback-on-Exception (Never Re-Raise)
**Source:** `agentic_service._rule_based_fallback` pattern; `ai_service.generate_text` lines 293–301
**Apply to:** All three `try` blocks in `enrich_report_data`
- Each block catches `Exception as exc`, logs at `WARNING`, sets a safe default value in `data`
- No exception propagates to `_generate_report` or `_deliver_report`

### BLOCKED/Error Prefix Guard
**Source:** `ai_service.generate_text` return conventions (lines 221, 294, 300)
**Apply to:** Both `generate_executive_summary` and `generate_framework_narrative`
```python
if result.startswith(("BLOCKED:", "Error:")):
    logger.warning("[NarrativeService] generate_text failed: %s", result[:80])
    return fallback
```

### PDF Story Pattern (`reportlab.platypus`)
**Source:** `scheduled_reports_service._build_pdf` lines 351–403
**Apply to:** `_render_narratives` in `compliance_narrative_service.py`
- `story` is a `list` — append `Paragraph`, `Spacer`, `Table` objects
- `styles = getSampleStyleSheet()` — use `styles["Heading2"]` and `styles["Normal"]`
- `Paragraph(text, style)` accepts plain str (no HTML escaping needed for prose output)

### Skip Set in `_build_pdf`
**Source:** `scheduled_reports_service._build_pdf` lines 377–378
**Apply to:** Any new keys added to `report_data` that should not appear in the metrics table
```python
skip = {"report_type", "report_name", "generated_at", "tenant_id", "period_start", "period_end",
        "ai_executive_summary", "ai_framework_narratives", "top_failing_controls"}
```

---

## No Analog Found

None. All four files have clear analogs in the codebase.

---

## Metadata

**Analog search scope:** `backend/`, `backend/tests/`
**Files scanned:** `ai_service.py`, `agentic_service.py`, `scheduled_reports_service.py`, `compliance_narrative_service.py`, `tests/test_agentic_ai.py`, `tests/test_scheduled_reports.py`, `tests/test_compliance_narrative_service.py`
**Pattern extraction date:** 2026-06-23

**Implementation status note:** As of 2026-06-23 both `compliance_narrative_service.py` and `test_compliance_narrative_service.py` already exist and `scheduled_reports_service.py` is already modified. The planner should treat Phase 13 as a verification/completion phase rather than a green-field implementation phase.
