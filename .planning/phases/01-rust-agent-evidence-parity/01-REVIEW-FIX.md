---
phase: 01-rust-agent-evidence-parity
fixed_at: 2026-07-04T14:30:00Z
review_path: .planning/phases/01-rust-agent-evidence-parity/01-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-07-04T14:30:00Z
**Source review:** .planning/phases/01-rust-agent-evidence-parity/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (CR-01, CR-02, WR-01, WR-02, IN-01, IN-02)
- Fixed: 6
- Skipped: 0

This review was written 2026-06-17 during the v1.0 milestone and never got a fix report at the time — its frontmatter said `status: clean` while still listing `critical: 2` and a body describing 6 open findings, an internal contradiction that made it look like a live 2-critical-bug backlog. A 2026-07-04 audit (triggered by an ambiguous `/gsd-code-review --all --fix` invocation with no phase number) investigated this contradiction directly against the current codebase before fixing anything.

## Findings already fixed prior to this pass (undocumented at the time)

### CR-01: Duplicate `evidence_id` When Multiple Checks Share a Control ID

**File:** `backend/compliance_evidence_processor.py`
**Status found:** Already fixed. `evidence_id` now includes a `check_slug` (a short hash of `check_name`) in addition to hostname/control_id/timestamp: `f"auto-ev-{agent_hostname}-{control_id}-{check_slug}-{timestamp}"`, exactly matching the review's originally suggested fix.
**Verification:** Confirmed by reading the current line directly — no code change needed in this pass.

### CR-02: Wrong Field Used for `memory_used_mb` Calculation

**File:** `backend/agent_heartbeat_endpoints.py`
**Status found:** Already fixed. `memory_used_mb` now multiplies by `meta.get("current_memory", 0)`, not `current_cpu`.
**Verification:** Confirmed by reading the current line directly — no code change needed in this pass.

### WR-01: Tenant Context Not Restored on Exception in Main Processing Loop

**File:** `backend/compliance_evidence_processor.py`
**Status found:** Already fixed. The main processing loop is now wrapped in `try:` / `finally: set_tenant_id(old_tenant_id)`, so an exception raised by any `await db.*` call inside the loop no longer leaves the tenant `ContextVar` pointing at the wrong tenant.
**Verification:** Confirmed by reading the current control flow directly — no code change needed in this pass.

### WR-02: Unit Test Does Not Verify `agent_type` in the Embedded Evidence Record

**File:** `backend/tests/test_rust_heartbeat_parity.py`
**Status found:** Already fixed. `test_rust02_and_rust03_db_calls` now has an explicit "RUST-02b" assertion inspecting `args[1]["$push"]["evidence"].get("agent_type")`, in addition to the pre-existing document-level `$set` check.
**Verification:** Confirmed by reading the current test directly — no code change needed in this pass.

## Findings fixed in this pass

### IN-01: Sleep-Based Synchronization in Live-Mode Test Is Unreliable

**Files modified:** `backend/tests/test_rust_heartbeat_parity.py`
**Applied fix:** Replaced `time.sleep(1)` in `main()`'s live-backend integration test with a poll-with-timeout loop (10s deadline, 0.25s poll interval), matching the review's originally suggested fix.
**Verification:** This is the live-mode path (`python3 backend/tests/test_rust_heartbeat_parity.py` against a running backend + real MongoDB) — not exercised by `pytest`, so verified by code inspection and syntax check rather than execution in this environment.

### IN-02: Deferred Import of `tenant_context` Inside Async Function Body

**Files modified:** `backend/compliance_evidence_processor.py`, `backend/tests/test_rust_heartbeat_parity.py`
**Applied fix:** Moved `from tenant_context import set_tenant_id, get_tenant_id` from inside `process_automated_evidence`'s function body to module level, removing the now-redundant local import. Updated `test_rust_heartbeat_parity.py`'s `_run_processor` helper to patch `compliance_evidence_processor.set_tenant_id`/`get_tenant_id` directly instead of the fragile `patch.dict("sys.modules", {"tenant_context": ctx})` trick the review flagged as silently breaking the moment the import was hoisted to module level — exactly the scenario this fix creates, so the test patching had to change in the same pass.
**Verification:** Confirmed the module imports cleanly with no circular-import issue; ran `pytest tests/test_rust_heartbeat_parity.py` — all 3 tests pass with the new patching strategy. Ran the full backend suite (`pytest tests/`) — same pre-existing 19 flaky/unrelated failures as before this change (confirmed via a stash/re-run comparison on the specific overlapping failure), no new regressions; 737 passed, matching the pre-change baseline.

## Skipped Issues

None — all 6 findings resolved (4 were already fixed before this pass; 2 were fixed in it).

## Also corrected

`01-REVIEW.md`'s frontmatter (`status: clean` contradicting `critical: 2`) and findings counts were updated to reflect reality (`critical: 0, warning: 0, info: 0, total: 0`), with a note added pointing to this fix report.

---

_Fixed: 2026-07-04T14:30:00Z_
_Fixer: Claude Sonnet 5_
_Iteration: 1_
