---
phase: 13
reviewers: [claude-internal]
reviewed_at: 2026-06-23T12:00:00Z
plans_reviewed: [13-01-PLAN.md, 13-02-PLAN.md]
implementation_reviewed: true
note: >
  No external AI CLI reviewers were detected at review time (gemini, codex, opencode,
  qwen, cursor, antigravity, ollama, lm_studio, llama_cpp — all missing). This review
  was produced by Claude Code (the executing environment) as the only available reviewer.
  Self-review limits independence; treat HIGH-severity findings with extra scrutiny and
  consider running /gsd-review again once an external CLI (gemini or codex recommended)
  is installed.
---

# Cross-AI Plan Review — Phase 13

## Claude Internal Review — Round 2 (post-execution)

_Self-review produced because no external CLI reviewers were available at runtime.
This pass covers 13-02-PLAN.md and audits the live implementation against the
13-01 review findings from Round 1. See frontmatter note on independence limits._

---

## Round 1 Findings Resolution (13-01 Plan)

The following Round 1 concerns were resolved in the implementation:

| Finding | Status | Evidence |
|---------|--------|----------|
| [HIGH] Wasted LLM calls on Path B | ✅ Fixed | `scheduled_reports_service.py:331` — `if not schedule.get("framework_id"): await enrich_report_data(...)` gate present |
| [MEDIUM] Empty `$in` edge case — no warning | ✅ Fixed | `compliance_narrative_service.py:156-160` — logger.warning when `control_id_to_name` is empty |
| [MEDIUM] `_fallback_executive_summary` not called consistently | ✅ Fixed | `compliance_narrative_service.py:88` — `fallback = _fallback_executive_summary(safe_fw, score)` |
| [MEDIUM] Cascading import risk | ✅ Fixed | `scheduled_reports_service.py:20-24` — try/except ImportError guard with noops |
| [LOW] Test 8 RED phase comment inaccuracy | ✅ Fixed | Test 8 docstring in `test_compliance_narrative_service.py:173-177` correctly states `AttributeError` RED mode |
| [MEDIUM] Test pattern inconsistency | ⚠️ See below | Implementation used `asyncio.get_event_loop()` — **this is the D-fix-1 bug addressed in 13-02** |
| [LOW] `within_budget` threshold at 250 (slack above 200) | ℹ️ Accepted | Intentional safety-net slack; primary enforcer is `_trim_to_words` |
| [LOW] Sequential LLM calls for N frameworks | ℹ️ Accepted | Noted in A4; `asyncio.gather()` is deferred |

---

## 13-02 Plan Review

### Summary

Plan 13-02 is a lean, targeted fixup plan with exactly two tasks and zero scope creep. It
addresses two verified post-execution defects — an asyncio ordering bug and a 500-line
violation — without touching AI logic, test assertions, or integration wiring. The plan
is well-evidenced: exact line numbers are named for every change, the arithmetic for line
reduction is shown, and the acceptance criteria verify both positive (things that should
change) and negative (things that must remain unchanged). This is a correct and
implementation-ready plan.

---

### Strengths

- **Exact line targeting for Task 1**: Lines 38, 63, 85, 110, and 165 are named
  explicitly. The action block specifies "Make exactly 5 Edit replacements" with old and
  new strings. No ambiguity about scope. The "do NOT change" constraints (sync tests,
  assertion logic, mocks) prevent over-reach.

- **Arithmetic-verified line reduction for Task 2**: The plan shows the for-loop body
  (lines 512-536 = 25 lines) minus the extracted function overhead. The `_process_due_schedule`
  body is printed verbatim in the plan, making it trivial to verify no behaviour change.

- **Both failure modes are accurately diagnosed**: D-fix-1 (asyncio ordering) is confirmed
  by the Python 3.12 behaviour where `asyncio.run()` removes the current event loop on
  completion, breaking subsequent `get_event_loop()` callers. D-fix-2 (line count) is
  confirmed by `wc -l scheduled_reports_service.py` = 539.

- **Preservation constraints are explicit**: The plan names the specific guards that must
  not be touched — ImportError guard (lines 20-24), framework_id gate (line 331),
  enrich_report_data call, _render_narratives calls, skip-set expansion. These match the
  live file exactly.

- **Acceptance criteria are binary and automated**: Every criterion maps to a shell command
  that returns a number or exit code. No subjective judgments required.

---

### Concerns

- **[MEDIUM] asyncio.run() inside a nested patch may behave differently from
  asyncio.get_event_loop()**:
  The fix replaces `asyncio.get_event_loop().run_until_complete(run())` with
  `asyncio.run(run())`. `asyncio.run()` creates a new event loop AND closes it after the
  coroutine completes. The 5 test methods each create a `with patch(...)` context that
  patches `compliance_narrative_service.ai_service`. The patch target lives in the module
  namespace — it is not event-loop-scoped — so closing the loop after each call should not
  affect the patch. However: the `patch()` context manager is entered and exited INSIDE
  the `run()` coroutine (nested inside `asyncio.run()`). If a future test uses a
  `@pytest.fixture` that sets up an event loop (e.g., `asyncio_mode = "auto"` from
  `pytest-asyncio`), `asyncio.run()` inside a running loop will raise `RuntimeError`.
  The project does not currently use `pytest-asyncio` in auto mode (confirmed by the
  warning in test output: "Unknown config option: asyncio_mode"), so this is safe now but
  worth noting as a future fragility.

- **[LOW] Module docstring update in Task 1 overwrites partial RED-phase documentation**:
  Line 5 currently reads: `RED phase: Tests 1-7 fail with ImportError (compliance_narrative_service.py
  does not exist yet). Test 8 fails with AssertionError (_build_pdf does not yet render narrative text).`
  The plan replaces this with: `Pattern: asyncio.run() isolates each test from prior event-loop state — order-independent.`
  The RED phase documentation is now gone. This is acceptable since Phase 13-01 is
  executed, but the comment's value going forward (as historical context for test design
  decisions) is lost. Low impact.

- **[LOW] `_process_due_schedule` adds ~27 lines, reducing from 539 by ~25 net**:
  The extracted function saves ~24 lines from the for-loop body but adds ~27 lines for the
  new function definition + docstring + signature. Net reduction: ~24 - 3 (signature +
  docstring + blank line) = ~21 lines, bringing total from 539 to ~518. This **does NOT
  reach ≤500 lines** if the arithmetic is right. Let me verify:
  - Lines 498-539 = 42 lines for `start_report_scheduler`
  - The for-loop body (lines 512-536) is ~25 lines
  - After extraction: `start_report_scheduler` = 42 - 25 + 1 (single call line) = 18 lines
  - `_process_due_schedule` = ~27 lines (signature, docstring, try, 10 body lines, except, 3 error lines)
  - Net change: -25 + 27 = +2 lines added → 539 + 2 = 541 lines
  - BUT the 25 for-loop lines are replaced by 1 call line: saves 24 lines
  - And `_process_due_schedule` is new: adds 27 lines
  - Net: 539 - 24 + 27 = 542 lines? That's HIGHER than before.
  
  Wait, let me re-count. The extraction replaces lines 512-536 (25 lines) in the for-loop
  with 1 line (`await _process_due_schedule(schedule, db)`). That's -24 lines from
  `start_report_scheduler`. The new `_process_due_schedule` function adds ~27 lines
  (including the try/except that wraps those 25 lines plus signature/docstring/blank).
  Net change: 539 - 24 + 27 = 542 lines. The file would be LARGER, not smaller.

  This arithmetic is a concern. The plan assumes the extraction reduces the file, but the
  extraction moves the same code to a different function definition — it only shrinks the
  file if the function has fewer total lines than the inlined code (e.g., by eliminating
  redundant try/except nesting). The plan shows `_process_due_schedule` adding its own
  try/except wrapper, which is the same try/except already present in `start_report_scheduler`.
  If the EXISTING for-loop body in `start_report_scheduler` is ALREADY wrapped in its own
  try/except (the per-schedule try/except), extraction just moves that try/except block to
  a new function — net line change ≈ 0 plus function signature overhead = net +2 to +4 lines.

  **The plan's claim that extraction brings the file under 500 lines may be incorrect.**
  The only way this works is if the current 539 lines includes significant blank lines or
  long comments inside `start_report_scheduler` that are NOT in the `_process_due_schedule`
  template shown in the plan. The executor MUST verify `wc -l` before and after the edit
  and may need to additionally remove blank lines or find another extraction target to hit
  ≤500.

- **[LOW] Task 2 docstring on `_process_due_schedule` adds a line**:
  The plan includes `"""Generate, deliver, and log one due schedule. Never raises — all exceptions logged."""`
  as a docstring. This is 1 additional line beyond what's strictly needed. If line count is
  tight, dropping the docstring saves 1 line.

---

### Verification Against Live Files

Current live state (checked at review time):

| Check | Value | Target | Status |
|-------|-------|--------|--------|
| `wc -l scheduled_reports_service.py` | 539 | ≤500 | ❌ FAIL (Plan 13-02 Task 2 needed) |
| `grep -c "get_event_loop" test_compliance_narrative_service.py` | 5 | 0 | ❌ FAIL (Plan 13-02 Task 1 needed) |
| `wc -l compliance_narrative_service.py` | 229 | <500 | ✅ PASS |
| `grep -c "enrich_report_data" scheduled_reports_service.py` | 2 | ≥2 | ✅ PASS |
| `grep -c "_render_narratives" scheduled_reports_service.py` | 3 | ≥3 | ✅ PASS |
| `grep -c "ai_executive_summary" scheduled_reports_service.py` (non-comment) | 1 | ≥1 | ✅ PASS |
| `grep -c "framework_id" scheduled_reports_service.py` | 7 | ≥1 | ✅ PASS (gate at line 331 confirmed) |
| All 15 tests pass (narrative + scheduled_reports) | 15/15 | 15/15 | ✅ PASS (in this run order) |
| All 15 tests pass (scheduled_reports first) | unknown | 15/15 | ❓ EXPECTED FAIL (event loop ordering) |

---

### Implementation Quality Notes

1. **`enrich_report_data` has two separate outer try/except blocks** (lines 145-181 and
   183-198 and 200-213). The three-part structure (failing controls block, executive summary
   block, framework narratives block) is cleanly separated. Each block can fail independently
   without affecting the others. This is correct defensive design.

2. **`_sanitise` silently truncates at `max_len` after stripping** (line 24):
   `_UNSAFE.sub("", str(value)).strip()[:max_len]`. If a 200-char name has 50 unsafe chars
   stripped, the result is only 150 chars — the truncation cap applies to the STRIPPED
   result, not the original. This means the effective max of the source string could be
   up to 200 + (number of stripped chars) chars. This is correct behavior (we want ≤200
   chars of safe content) but differs from what a naive reader would expect.

3. **`generate_framework_narrative` passes `data["top_failing_controls"]` from `enrich_report_data`
   to all frameworks** (lines 207): All frameworks get the SAME top failing controls list
   (the cross-framework list), not per-framework failing controls. This is a semantic
   approximation: the narrative says "top failing controls across all frameworks" rather
   than "failing controls specific to this framework." For Phase 13 scope this is acceptable,
   but it may produce narratives where the per-framework section references controls that
   don't belong to that framework's spec.

4. **Test 8 patches `scheduled_reports_service._render_narratives`** (not
   `compliance_narrative_service._render_narratives`). This is correct — the import at
   line 21 of `scheduled_reports_service.py` binds `_render_narratives` into the
   `scheduled_reports_service` namespace, so the patch target must be the consumer module,
   not the source module. The test is correctly written.

---

### Recommendations for Executor (13-02)

1. **Verify line-count arithmetic before committing Task 2**: Run `wc -l scheduled_reports_service.py`
   immediately after the edit. If still > 500, the extraction needs to target additional
   cleanup (e.g., collapsing 3-line `logger.info` calls into 1 line, or removing blank
   lines inside the scheduler loop). Do NOT commit until `wc -l` confirms ≤500.

2. **Run tests in the problematic order first**: After Task 1, run
   `python3 -m pytest tests/test_scheduled_reports.py tests/test_compliance_narrative_service.py`
   (scheduled_reports FIRST). This is the order that triggers the Python 3.12 event-loop bug.
   Only this order confirms the fix works.

3. **Do not change the 3 sync tests** (TestSanitise, TestNarrativeOutput,
   TestBuildPdfIntegration) — they have no event loop calls and must remain unchanged.

---

### Risk Assessment — 13-02 Plan

**Overall: LOW-MEDIUM**

Both tasks are correct in their diagnosis and approach. The asyncio.run() fix (Task 1) is
definitive. Task 2's line-count reduction arithmetic needs verification — the executor
should check `wc -l` before and after and be prepared to do additional cleanup if the
extraction alone is insufficient to reach ≤500 lines.

---

## Consensus Summary

_Single reviewer — consensus reflects this reviewer's synthesis only._

### Agreed Strengths

- Full four-layer fail-safe delivery (sanitise → prefix check → Pydantic → static fallback)
- All Round 1 HIGH and MEDIUM findings were resolved in the implementation
- Framework_id gate prevents wasted LLM calls on Path B reports
- ImportError guard prevents cascading service failure
- `_process_due_schedule` extraction is architecturally correct (pure refactor, no logic change)
- asyncio.run() fix is the correct Python 3.12-compatible pattern

### Agreed Concerns

- **Task 2 line-count arithmetic may not reach ≤500**: Verify `wc -l` after extraction;
  be prepared to do additional cleanup if needed.
- **Cross-framework control list in per-framework narratives**: All frameworks get the same
  top failing controls — a semantic approximation. Acceptable for Phase 13 scope.
- **asyncio.run() fragility with future pytest-asyncio adoption**: Safe today; document
  the pattern choice so future test authors don't mix asyncio.run() with auto-mode fixtures.

### Open Items

- Plan 13-02 Task 1: Replace 5 `asyncio.get_event_loop()` calls — **NOT YET EXECUTED**
- Plan 13-02 Task 2: Extract `_process_due_schedule` — **NOT YET EXECUTED**

_To execute: `/gsd-execute-phase 13`_
_To incorporate this feedback into replanning: `/gsd-plan-phase 13 --reviews`_
_For independent review: install gemini (`npm i -g @google/gemini-cli`) or codex (`npm i -g @openai/codex`), then re-run `/gsd-review --phase 13`_
