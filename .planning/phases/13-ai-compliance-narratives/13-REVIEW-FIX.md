---
phase: 13-ai-compliance-narratives
fixed_at: 2026-07-03T19:20:48Z
review_path: .planning/phases/13-ai-compliance-narratives/13-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 13: Code Review Fix Report

**Fixed at:** 2026-07-03T19:20:48Z
**Source review:** .planning/phases/13-ai-compliance-narratives/13-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (CR-01, CR-02, WR-01 through WR-07; IN-01 through IN-03 out of scope for this pass)
- Fixed: 9
- Skipped: 0

All fixes were verified against the existing suite: `cd backend && python3 -m pytest tests/test_compliance_narrative_service.py tests/test_scheduled_reports.py -v` — 15/15 passed after every commit.

## Fixed Issues

### CR-01: AI narrative / user-controlled strings rendered unescaped into reportlab `Paragraph`

**Files modified:** `backend/compliance_narrative_service.py`, `backend/scheduled_reports_service.py`
**Commit:** c8d9dbe
**Applied fix:** Added `import html as _html` to `compliance_narrative_service.py` and escaped `ai_summary`, `narrative`, and `fw_name` with `_html.escape(..., quote=False)` before passing to `Paragraph()` in `_render_narratives`, matching the existing convention in `_build_html` (same file) and `compliance_reporting_pdf.py`. Also escaped `report_name`, `generated_at`, and `period_start`/`period_end` in `scheduled_reports_service.py::_build_pdf`. Additionally, changed `_deliver_report` so a failed local PDF build (`pdf_bytes` falsy) now raises `RuntimeError` instead of silently sending an attachment-less email — this propagates through the existing `try`/`except` in both `run_report_now` and `_process_due_schedule`, which already write a `"failure"` delivery-log entry on any exception, so no new call-site logic was needed beyond the raise. Verified the reportlab PoC from the review (`Paragraph('...unclosed <b>tag', ...)`) no longer raises once escaped.

### CR-02: Per-framework narrative used a single tenant-wide aggregated `top_failing_controls` list for every framework

**Files modified:** `backend/compliance_narrative_service.py`
**Commit:** ed5fe7f
**Applied fix:** `enrich_report_data` now tracks `control_id_to_framework` (keyed by framework `name`, the only identifier shared between the all-frameworks lookup and the tenant-scoped `data["frameworks"]` entries, which carry only `name`/`score` — no `id`) and builds a per-framework failing-controls list (`failing_by_framework`, kept as a local variable rather than stored on `data`, so it doesn't leak into the generic metrics table / HTML / JSON exports). The framework-narrative loop now passes `failing_by_framework.get(fw_name, [])` instead of the aggregated `data["top_failing_controls"]`. The aggregated list is retained unchanged for the executive summary, which is intentionally cross-framework. Manually verified with a mocked two-framework, same-control-name scenario that dedup and per-framework scoping behave as expected.

### WR-01: A single bad framework record discarded narratives for all frameworks

**Files modified:** `backend/compliance_narrative_service.py`
**Commit:** e510128
**Applied fix:** Moved the `try`/`except` inside the per-framework loop in `enrich_report_data`. `float(fw.get("score", 0.0))` failures are now caught per-framework (falling back to `0.0`) and `generate_framework_narrative` failures are logged per-framework without discarding narratives already generated for other frameworks.

### WR-02: `NarrativeOutput.within_budget` used a shared hardcoded 200-word ceiling for both 150- and 200-word budgets

**Files modified:** `backend/compliance_narrative_service.py`
**Commit:** 1e5e0f9
**Applied fix:** Added a `limit: int = 200` field to `NarrativeOutput` and replaced the `field_validator` on `word_count` with a `model_validator(mode="after")` that checks `word_count > limit`. `from_raw` and `_validated_narrative` now accept an explicit `limit` parameter; `generate_executive_summary` passes `limit=150` and `generate_framework_narrative` passes `limit=200`, so the bypass-catcher validates against the actual call-site budget instead of the loosest of the two.

### WR-03: `_sanitise` stripped structural characters but not newlines, leaving a residual prompt-injection surface

**Files modified:** `backend/compliance_narrative_service.py`
**Commit:** 8bd71ea
**Applied fix:** Added `_NEWLINES = re.compile(r"[\r\n]+")` and collapse embedded newlines to a single space in `_sanitise` before the existing `_UNSAFE` character strip and truncation, so a crafted control/framework name can't inject new lines inside the `<compliance_data>` prompt block.

### WR-04: `enrich_report_data` accepted `tenant_id` but never used it, relying entirely on ambient context

**Files modified:** `backend/compliance_narrative_service.py`
**Commit:** b75feb5
**Applied fix:** Imported `set_tenant_id` from `tenant_context` and call it explicitly at the top of `enrich_report_data`, so the function is correct in isolation and fails closed if a future call site forgets to set tenant context first, rather than depending entirely on the current caller (`_generate_report`) having already done so.

### WR-05: `_calculate_next_run` ignored the stored `day_of_week`/`day_of_month` schedule fields

**Files modified:** `backend/scheduled_reports_service.py`
**Commit:** 3c6eaf2
**Applied fix:** `_calculate_next_run` now accepts `day_of_week`/`day_of_month` parameters. The weekly branch converts the schedule's stored `1=Monday..7=Sunday` convention to Python's `weekday()` convention and computes the correct number of days ahead (rolling forward a full week if the target day/hour has already passed today). The monthly/quarterly branches use `calendar.monthrange` to clamp `day_of_month` to the target month's actual length (avoiding invalid dates like Feb 30). Updated all four call sites (`create_schedule`, `update_schedule`, `run_report_now`, `_process_due_schedule`) to pass these values from the schedule document. Also added `day_of_week`/`day_of_month` to `update_schedule`'s persisted-fields loop, since the fix would otherwise be undermined by a stale value if a user only ever updates these fields via `update_schedule` (they were previously not in the persisted-fields list at all, meaning changes were silently dropped). Manually verified next-run computation for a Friday weekly target and 15th/31st monthly/quarterly targets (with day clamping).

**Note:** This is a scheduling-algorithm change. Only syntax verification and ad hoc manual date-math checks were performed — no automated test exercises `_calculate_next_run` directly. **Recommend human verification** of the weekly/monthly/quarterly date logic before relying on it in production.

### WR-06: Webhook/Slack/Teams delivery POSTed to a user-supplied URL with no validation (SSRF surface)

**Files modified:** `backend/scheduled_reports_service.py`
**Commit:** 6bcbfff
**Applied fix:** Added `_validate_webhook_url()`, which requires `https://` scheme and rejects (or fails closed on unresolvable) hostnames/IPs that are loopback, private, link-local, reserved, multicast, or unspecified, using `ipaddress` for literal IPs and `socket.getaddrinfo` (via `run_in_executor` to avoid blocking the event loop) for DNS names. Wired into `create_schedule` and `update_schedule` (validate before persisting `webhook_url`/`slack_webhook`/`teams_webhook`) and into `_deliver_report` (re-validate immediately before `session.post(...)`, as defense-in-depth against DNS rebinding after the schedule was saved). Manually verified rejection of `http://`, `169.254.169.254` (cloud metadata), `127.0.0.1`, and `localhost`, and acceptance of a real public HTTPS webhook host.

### WR-07: `failing_docs` query had no explicit sort, so severity ranking of `top_failing_controls` could be non-deterministic

**Files modified:** `backend/compliance_narrative_service.py`
**Commit:** 1aec912
**Applied fix:** Replaced the `seen: set` first-occurrence dedup with `best_severity`/`best_severity_by_fw` dicts that track the lowest (most severe) `_SEVERITY_ORDER` value seen for each control name, updating whenever a more severe occurrence is found later in the (unordered) result set. This makes both the aggregate `top_failing_controls` list and the new per-framework lists (from the CR-02 fix) deterministic and correct regardless of MongoDB's return order, without needing to add a sort on an unverified severity field in `asset_compliance`.

## Skipped Issues

None — all 9 in-scope findings were fixed.

---

_Fixed: 2026-07-03T19:20:48Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
