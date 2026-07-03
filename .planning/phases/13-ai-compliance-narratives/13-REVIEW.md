---
phase: 13-ai-compliance-narratives
reviewed: 2026-07-03T19:05:38Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - backend/compliance_narrative_service.py
  - backend/scheduled_reports_service.py
  - backend/tests/test_compliance_narrative_service.py
findings:
  critical: 2
  warning: 7
  info: 3
  total: 12
status: issues_found
---

# Phase 13: Code Review Report

**Reviewed:** 2026-07-03T19:05:38Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed `compliance_narrative_service.py` (new), `scheduled_reports_service.py` (modified/trimmed to 500 lines in 13-02), and the new unit test file. The word-budget enforcement (`_trim_to_words` + `NarrativeOutput` pydantic model) is fundamentally sound and the `BLOCKED:`/`Error:` fallback path is well covered by a defense-in-depth pair (prefix check + pydantic `text_not_empty` validator), including the edge case where `ai_service.generate_text()` returns `""` when no provider is configured.

However, two BLOCKER-level defects were found. First, AI-generated narrative text and other report strings (schedule name, framework name) are passed unescaped into `reportlab.platypus.Paragraph`, which parses its input as a constrained XML/markup dialect (confirmed by executing the code: an unescaped unclosed tag raises `ValueError` at `Paragraph()` construction). `_build_pdf`'s broad `except Exception` swallows this, returns `None`, and the caller (`_deliver_report`/`_process_due_schedule`) still logs the delivery as `"success"` and emails recipients with no attachment — a silent, unannounced report-delivery failure triggerable by ordinary AI phrasing or by any user naming a schedule with a stray `<`. This is exactly the class of "AI-output sanitization before rendering" issue the phase was supposed to close, and it regresses relative to `_build_html`'s correct use of `html.escape()` and `compliance_reporting_pdf.py`'s established `html.escape(str(v), quote=False)` convention for the same `Paragraph()` API. Second, `enrich_report_data` computes a single tenant-wide/aggregated `top_failing_controls` list and feeds the *identical* list to `generate_framework_narrative()` for every framework in a multi-framework report, so a framework's "per-framework findings narrative" can describe another framework's failing controls as if they belong to it — undermining the accuracy of an audit-facing document.

## Critical Issues

### CR-01: AI narrative / user-controlled strings are rendered unescaped into reportlab `Paragraph`, causing silent PDF-generation failure and markup-injection risk

**File:** `backend/compliance_narrative_service.py:222,228-229`
**File:** `backend/scheduled_reports_service.py:336,338-342`

**Issue:**
`_render_narratives()` builds `Paragraph(ai_summary, styles["Normal"])`, `Paragraph(narrative, styles["Normal"])`, and `Paragraph(f"{fw_name} — Findings", styles["Heading2"])` directly from LLM output and DB-sourced framework names, with no escaping. `_build_pdf()` similarly renders `Paragraph(title, styles["Title"])` from the fully user-controlled `schedule["name"]` field (set by `create_schedule`/`update_schedule` with zero validation).

`reportlab.platypus.Paragraph` parses its text argument as a constrained XML/HTML-like markup dialect (it supports `<b>`, `<i>`, `<font>`, `<a href=...>`, etc.), so raw, unescaped input is not safe to hand to it. This is empirically confirmed:

```
>>> from reportlab.platypus import Paragraph
>>> from reportlab.lib.styles import getSampleStyleSheet
>>> Paragraph('Risk & Compliance narrative with an ampersand and unclosed <b>tag', getSampleStyleSheet()['Normal'])
ValueError: paragraph text '<para>Risk & Compliance narrative with an ampersand and unclosed <b>tag</para>' caused exception Parse error: saw </para> instead of expected </b>
```

The compliance-narrative system prompts *ask* the LLM to avoid markdown/headings, but nothing enforces this — an LLM stray `<b>`, an unbalanced angle bracket, or a schedule name containing `<` will raise inside `Paragraph()`. `_build_pdf()` catches this with a blanket `except Exception: return None` (line 371-373), so the failure is invisible to the caller. Tracing the call chain: `_deliver_report()` only guards attachment creation with `if pdf_bytes:` but still calls `email_service.send_report(...)` for every recipient with `attachments=None`, and `_process_due_schedule()`/`run_report_now()` still call `_write_delivery_log(db, schedule, "success", None, filename)` (filename is `None`). The net effect: a report whose narrative or schedule name contains ordinary punctuation-adjacent text can result in **emails being sent with no PDF attached, while the delivery log and schedule metadata (`last_run`, `run_count`) record it as a successful delivery** — a silent compliance-evidence delivery failure with no operator visibility.

This is also inconsistent with the rest of the codebase: `_build_html()` in the same file correctly does `_html.escape(...)` for all interpolated values (added in commit `be293f0`, "CR-03 HTML-escape user-controlled values in `_build_html` to prevent XSS"), and `compliance_reporting_pdf.py` already does `Paragraph(html.escape(str(h), quote=False), ...)` for the exact same `Paragraph` API. The new narrative-rendering path does not follow this established, already-fixed-once convention.

**Fix:**
```python
# compliance_narrative_service.py
import html as _html

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
```
```python
# scheduled_reports_service.py — _build_pdf
title = _html.escape(report_data.get("report_name", "Security Report"), quote=False)
story.append(Paragraph(title, styles["Title"]))
story.append(Paragraph(f"Generated: {_html.escape(str(report_data.get('generated_at', '')), quote=False)}", styles["Normal"]))
```
Additionally, consider surfacing a failed `_build_pdf()` (returns `None`) as a `"failure"` delivery-log entry rather than silently proceeding to send an attachment-less email as `"success"`.

---

### CR-02: Per-framework narrative uses a single tenant-wide aggregated `top_failing_controls` list for every framework, misattributing findings

**File:** `backend/compliance_narrative_service.py:161-178, 200-209`

**Issue:**
`enrich_report_data()` builds one flat, deduplicated `data["top_failing_controls"]` list aggregated across **all** frameworks (query at line 161-167 has no per-framework scoping beyond the global `control_id_to_name` map). That same list is then passed unchanged as `failing_controls` to `generate_framework_narrative()` for **every** framework in the loop:

```python
for fw in data.get("frameworks", []):
    fw_name = fw.get("name", "")
    narratives[fw_name] = await generate_framework_narrative(
        framework_name=fw_name,
        score=float(fw.get("score", 0.0)),
        failing_controls=data.get("top_failing_controls", []),   # same list for every framework
        remediation_summary=None,
    )
```

The `generate_framework_narrative` system prompt explicitly instructs the model: *"Write factual, concise prose. Do not reference controls not listed below."* — but the controls listed are not actually specific to `fw_name`; they may belong entirely to a different framework in a multi-framework report. The generated "per-framework findings narrative" (the core feature of this phase) can therefore describe controls that have nothing to do with the framework it is titled under, in an audit-facing PDF. This is a factual-accuracy defect in the delivered feature, not merely a style issue.

**Fix:** Scope the failing-controls query per framework (e.g., track `frameworkId` alongside `controlId` when building `control_id_to_name`, and filter `sorted_controls` by the current framework before calling `generate_framework_narrative`):
```python
control_id_to_framework: dict = {}
for fw in frameworks:
    for ctrl in fw.get("controls", []):
        cid = str(ctrl.get("id") or ctrl.get("_id") or "")
        if cid:
            control_id_to_framework[cid] = fw.get("id") or fw.get("name")
...
for fw in data.get("frameworks", []):
    fw_controls = [n for cid, n in ... if control_id_to_framework.get(cid) == fw.get("id")]
    narratives[fw_name] = await generate_framework_narrative(..., failing_controls=fw_controls, ...)
```

## Warnings

### WR-01: A single bad framework record discards narratives for all frameworks, not just the failing one

**File:** `backend/compliance_narrative_service.py:200-213`
**Issue:** The entire per-framework loop is wrapped in one `try`/`except`. If any single framework's `float(fw.get("score", 0.0))` raises (e.g. `compliance_score` stored as `None` or a non-numeric string for one framework), the `except` branch discards the whole `narratives` dict built so far and sets `data["ai_framework_narratives"] = {}` — every other, otherwise-successful framework narrative is lost too.
**Fix:** Move the try/except inside the loop body so one framework's failure doesn't blank the others:
```python
narratives: dict = {}
for fw in data.get("frameworks", []):
    fw_name = fw.get("name", "")
    try:
        score = float(fw.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    try:
        narratives[fw_name] = await generate_framework_narrative(
            framework_name=fw_name, score=score,
            failing_controls=data.get("top_failing_controls", []), remediation_summary=None,
        )
    except Exception as exc:
        logger.warning("[NarrativeService] Framework narrative failed for %s: %s", fw_name, exc)
data["ai_framework_narratives"] = narratives
```

### WR-02: `NarrativeOutput.within_budget` uses a shared hardcoded 200-word ceiling for both the 150-word and 200-word budgets

**File:** `backend/compliance_narrative_service.py:46-53`
**Issue:** The comment acknowledges the validator is a bypass-catcher, but because it hardcodes `v > 200` for both the executive summary (150-word budget) and the framework narrative (200-word budget), it cannot catch a regression that produces, e.g., a 180-word executive summary if `_trim_to_words` were ever called with the wrong limit or skipped. The safety net is only as tight as the loosest of the two budgets.
**Fix:** Parametrize the budget check per call site instead of relying solely on the model's fixed threshold, e.g. re-validate the actual limit after `_trim_to_words` in each generator function, or pass the applicable limit into `NarrativeOutput.from_raw(raw, limit)` and validate against it.

### WR-03: `_sanitise` strips structural characters but not newlines/quotes, leaving a residual prompt-injection surface

**File:** `backend/compliance_narrative_service.py:13, 23-24`
**Issue:** `_UNSAFE = re.compile(r"[<>{}\[\]\\]")` removes characters that could forge a fake `</compliance_data>` closing tag, but does not strip newlines or quotes. A crafted control/framework name (if such names are ever user- or tenant-editable, e.g. via a custom framework feature) containing embedded newlines can still inject new "instructions" on subsequent lines inside the `<compliance_data>` block, bypassing the tag-based delimiter defense. Downstream word-budget/fallback enforcement bounds the blast radius, but the report content itself could still be manipulated.
**Fix:** Additionally strip or collapse newlines/control characters in `_sanitise` (e.g. `re.sub(r"[\r\n]+", " ", value)`) before truncation.

### WR-04: `enrich_report_data` accepts `tenant_id` but never uses it — relies entirely on ambient context

**File:** `backend/compliance_narrative_service.py:144, 161-167`
**Issue:** The function signature is `async def enrich_report_data(data: dict, db, tenant_id: str) -> None`, but `tenant_id` is never referenced in the body. The tenant scoping of `db.asset_compliance.find(...)` (line 161) depends entirely on `tenant_context.get_tenant_id()` having already been set by the caller (`_generate_report` calls `set_tenant_id(tenant_id)` before invoking this function). It currently works because the one caller happens to set it first, but the function gives no indication of this dependency and provides no defense if a future call site forgets to call `set_tenant_id` first — the fail-closed tenant wrapper would then return no rows (or, if `tenant_id` were ever `"platform-admin"` unintentionally, all tenants' rows).
**Fix:** Call `set_tenant_id(tenant_id)` explicitly at the top of `enrich_report_data` (as every other function in `scheduled_reports_service.py` does), or drop the unused parameter and document the ambient-context dependency clearly.

### WR-05: `_calculate_next_run` ignores the stored `day_of_week` / `day_of_month` schedule fields

**File:** `backend/scheduled_reports_service.py:118-119, 143-166`
**Issue:** `create_schedule`/`update_schedule` store `day_of_week` and `day_of_month` from user input, but `_calculate_next_run(frequency, hour)` never accepts or reads either field. The `weekly` branch (`days_ahead = 7 - now.weekday()`) always lands on the next Monday regardless of the configured `day_of_week`, and `monthly`/`quarterly` always land on day 1 regardless of `day_of_month`. Users who configure a schedule for, e.g., Friday delivery will silently get Monday delivery instead. (This predates the Phase 13 changes but is present in the reviewed file and worth tracking.)
**Fix:** Thread `day_of_week`/`day_of_month` into `_calculate_next_run` and use them in the weekly/monthly/quarterly branches, or remove the fields from the schema/API if they are intentionally not implemented yet.

### WR-06: Webhook/Slack/Teams delivery POSTs to a user-supplied URL with no validation (SSRF surface)

**File:** `backend/scheduled_reports_service.py:447-455`
**Issue:** `webhook_url`, `slack_webhook`, and `teams_webhook` are stored verbatim from `create_schedule`/`update_schedule` input with no URL validation, and `_deliver_report` performs `await session.post(webhook_url, json=report_data, ...)` directly. There is no scheme allow-list or check against internal/link-local/private address ranges, so a tenant user with schedule-management access could point report delivery at internal services (e.g. cloud metadata endpoints, internal admin APIs). (Pre-existing pattern, not introduced by Phase 13, but present in the reviewed file.)
**Fix:** Validate the URL scheme (`https://` only) and resolve/reject private, loopback, and link-local address ranges before allowing it to be saved or used for delivery.

### WR-07: `failing_docs` query has no explicit sort, so severity ranking of `top_failing_controls` can be non-deterministic

**File:** `backend/compliance_narrative_service.py:161-178`
**Issue:** `db.asset_compliance.find(...)` has no `.sort()`, and the subsequent dedup (`if name and name not in seen`) keeps whichever occurrence of a repeated control name is encountered *first* in the (unordered) result set. If the same control name appears with different severities across records, the severity attributed to it — and therefore its position in the final top-7 list — depends on arbitrary DB return order rather than the actual highest severity seen.
**Fix:** Either sort the query results deterministically (e.g., by a stored severity/priority field) or, when deduplicating by name, keep the occurrence with the lowest `_SEVERITY_ORDER` value rather than the first-seen one.

## Info

### IN-01: `db._db.compliance_frameworks` bypasses the tenant-isolation wrapper's own public API unnecessarily

**File:** `backend/compliance_narrative_service.py:146`
**Issue:** `compliance_frameworks` is already in `TenantIsolatedDatabase`'s exemption list (`database.py`), so `db.compliance_frameworks.find({})` would return the identical unwrapped collection via `__getattr__`. Reaching into the private `db._db` attribute instead is unnecessary and couples this module to `TenantIsolatedDatabase`'s internal implementation detail.
**Fix:** Use `db.compliance_frameworks.find({})` for consistency with the rest of the codebase.

### IN-02: `remediation_summary` parameter is always `None` from the only caller

**File:** `backend/compliance_narrative_service.py:114, 119, 208`
**Issue:** `generate_framework_narrative` accepts a `remediation_summary` argument and builds a "Remediation notes" section of the prompt from it, but `enrich_report_data` always passes `remediation_summary=None`, so this section of every generated narrative is permanently "None provided". The capability is wired but never populated with real data.
**Fix:** Either populate `remediation_summary` from actual remediation data (e.g., an existing remediation-plan/ticket summary if available), or drop the unused parameter until there's a data source for it.

### IN-03: `_process_due_schedule`'s `last_run` timestamp is computed after delivery, not reused from the batch-level `now` — a subtle change from the pre-refactor behavior

**File:** `backend/scheduled_reports_service.py:469`
**Issue:** Commit `33b8df3` explicitly states the extraction "preserves exact exception handling behavior verbatim." Exception handling is indeed preserved, but the previous inline code reused a single `now` timestamp captured once at the top of the scheduler tick (before the `for schedule in due_schedules` loop) for every schedule's `last_run`. The extracted `_process_due_schedule` now computes `now = datetime.now(timezone.utc).isoformat()` freshly inside the function, after `_generate_report`/`_deliver_report` complete, for each schedule individually. This is arguably more accurate, but it is a real behavior change beyond "exact... verbatim" and is worth calling out explicitly rather than leaving implicit in the diff.
**Fix:** No action required if the new (per-schedule, post-delivery) timestamp is the intended behavior — just note it in the phase's decision log so it isn't mistaken for a no-op refactor.

---

_Reviewed: 2026-07-03T19:05:38Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
