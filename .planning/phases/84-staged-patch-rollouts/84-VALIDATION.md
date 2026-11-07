---
phase: "84"
slug: "staged-patch-rollouts"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-05"
validated: "2026-11-07"
---

# Phase 84 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend, fixtures `backend/tests/_mongo_test_db.py`, helpers `backend/tests/autonomy_support.py`), Vitest (UI), cargo test (Rust agent) |
| **Config file** | `backend/tests/conftest.py`, `package.json` (`"test": "vitest run"`), `agent-install/omni-agent-rs/Cargo.toml` |
| **Quick run command** | `MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=mongodb://127.0.0.1:27998 MONGO_URI=mongodb://127.0.0.1:27998 backend/venv/bin/python -m pytest backend/tests/test_patch_rollout_<file>.py -q -p no:cacheprovider` |
| **Full suite command** | same prefix with `backend/tests/test_autonomous_ops_*.py backend/tests/test_patch_*.py backend/tests/test_catalogue_*.py -q -p no:cacheprovider`; UI `npx vitest run src/__tests__/<file>`; agent `PATH=$HOME/.cargo/bin:$PATH CARGO_BUILD_JOBS=1 CARGO_PROFILE_DEV_DEBUG=0 cargo test --offline --manifest-path agent-install/omni-agent-rs/Cargo.toml --lib <filter>` |
| **Estimated runtime** | ~60 seconds per quick run; Rust lib tests ~6 minutes from clean with debug info off |

---

## Sampling Rate

- **After every task commit:** Run the task's new test file plus `test_autonomous_ops_structural.py` and `test_autonomous_ops_copy.py`
- **After every plan wave:** Run all `test_autonomous_ops_*.py`, `test_patch_*.py`, catalogue slice tests and the touched Vitest files
- **Before `/gsd-verify-work`:** Full backend suite (known baseline: 5,135 pass plus the known 5 failures, including the two nav-count-190 pins from Phase 87), Vitest and Rust lib tests green
- **Max feedback latency:** 120 seconds for backend and UI; Rust runs only on agent tasks

---

## Per-Task Verification Map

Requirement-level map. Task ids read `plan/task` (for example `84-01/T1` is plan 84-01 task 1). Filled by 84-21 from the plan summaries; every automated command below ran green together on the final code (84-21 SUMMARY).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 84-01/T1, 84-01/T2, 84-06/T1, 84-06/T3, 84-22/T1, 84-22/T2, 84-16/T1, 84-14/T1..T3, 84-17/T1..T3, 84-18/T3 | 84-01, 84-06, 84-22, 84-16, 84-14, 84-17, 84-18 | 1-6 | PTCH-01 | T-84-60, T-84-61 | Rings from agent groups snapshot at Start; next ring only after soak and green gate; controller resumes after restart; the controller loop runs one copy at a time | unit + mongo + vitest | `pytest backend/tests/test_patch_rollout_rings.py backend/tests/test_patch_rollout_controller.py backend/tests/test_patch_rollout_tracer.py backend/tests/test_patch_rollout_lifecycle.py -q`; `npx vitest run src/__tests__/PatchRolloutsTab.test.tsx src/__tests__/PatchRolloutStartDialog.test.tsx src/__tests__/PatchRolloutRings.test.tsx src/__tests__/PatchRolloutCard.test.tsx` | ✅ | ✅ green |
| 84-08/T1, 84-08/T2, 84-08/T3, 84-11/T1, 84-11/T2, 84-18/T1 | 84-08, 84-11, 84-18 | 3, 6 | PTCH-02 | T-84-37 | Each missing signal halts; `skipped` is not success; boot baseline rejects the old boot; services the agent cannot report read Not checked, never Passed | unit + cargo + vitest | `pytest backend/tests/test_patch_rollout_health.py backend/tests/test_patch_rollout_boot.py -q`; `cargo test --lib service_state`; `npx vitest run src/__tests__/PatchRolloutRingDetail.test.tsx` | ✅ | ✅ green |
| 84-08/T2, 84-08/T3, 84-13/T1, 84-18/T1 | 84-08, 84-13, 84-18 | 3, 4, 6 | PTCH-03 | — | Canary halts on any failure; later rings halt above 10% once 10 hosts reported | unit | `pytest backend/tests/test_patch_rollout_health.py backend/tests/test_patch_rollout_revert.py -q` | ✅ | ✅ green |
| 84-02/T2, 84-07/T1, 84-07/T2, 84-13/T1..T3, 84-16/T1, 84-16/T3, 84-14/T3, 84-18/T2, 84-18/T3 | 84-02, 84-07, 84-13, 84-14, 84-16, 84-18 | 1-6 | PTCH-04 | T-84-43 | Halt reverts through undo, also during a stop; unsupported OS says not reverted; no bare "rollback" copy | mongo + copy gate + cargo + vitest | `pytest backend/tests/test_patch_rollout_revert.py backend/tests/test_patch_rollout_activity.py backend/tests/test_autonomous_ops_copy.py -q`; `cargo test --lib patch_`; `npx vitest run src/__tests__/PatchRolloutDialogs.test.tsx` | ✅ | ✅ green |
| 84-01/T3, 84-03/T1, 84-04/T1, 84-05/T1, 84-05/T2, 84-06/T2, 84-09/T1, 84-12/T1..T3, 84-17/T2, 84-20/T1 | 84-01, 84-03, 84-04, 84-05, 84-06, 84-09, 84-12, 84-17, 84-20 | 1-6 | PTCH-05 | — | Window math (overnight, DST, weekday mapping); no window blocks Start; outside window nothing dispatches; tenant-isolated window routes | unit + api + vitest | `pytest backend/tests/test_maintenance_windows.py backend/tests/test_patch_rollout_delivery.py backend/tests/test_patch_rollout_views.py backend/tests/test_patch_rollout_dispatcher.py -q`; `npx vitest run src/__tests__/MaintenanceWindows.test.tsx src/__tests__/ChangeManagementWindows.test.tsx` | ✅ | ✅ green |
| 84-01/T1, 84-02/T1, 84-03/T1..T3, 84-07/T3, 84-08/T1, 84-10/T1, 84-10/T2, 84-15/T1, 84-15/T2, 84-19/T1, 84-19/T2, 84-20/T1, 84-20/T2 | 84-01, 84-02, 84-03, 84-07, 84-08, 84-10, 84-15, 84-19, 84-20 | 1-6 | PTCH-06 | T-84-60 | Canary auto only with agent token and reversible class; all else and every reboot needs approval; reconciler skips rollout rows; shadow mode simulates for the whole life of a rollout | mongo + vitest | `pytest backend/tests/test_patch_rollout_lines.py backend/tests/test_patch_rollout_cards.py backend/tests/test_patch_rollout_shadow_stop.py backend/tests/test_autonomous_ops_reconciler.py backend/tests/test_autonomous_ops_registry.py -q`; `npx vitest run src/__tests__/RolloutApprovalCard.test.tsx src/__tests__/PatchRolloutDraftEntry.test.tsx` | ✅ | ✅ green |
| 84-04/T1..T3, 84-06/T2, 84-09/T3, 84-16/T1, 84-16/T2, 84-20/T2, 84-22/T1, 84-22/T2 | 84-04, 84-06, 84-09, 84-16, 84-20, 84-22 | 2-6 | PTCH-07 | T-84-61 | Platform tenant and protected hosts never claimed; one active rollout per host; expired instruction never delivered; legacy service writes nothing | mongo | `pytest backend/tests/test_patch_rollout_claims.py backend/tests/test_patch_rollout_legacy_fence.py backend/tests/test_autonomous_ops_stop.py backend/tests/test_autonomous_ops_structural.py -q` | ✅ | ✅ green |
| 84-07/T1, 84-07/T2, 84-07/T3, 84-11/T1, 84-11/T2, 84-21/T1 | 84-07, 84-11, 84-21 | 2, 3, 7 | Agent | T-84-37, T-84-60 | Reversibility pre-check, per-job revert state, `service_state`, tokens equal the contract; Windows target compiles; version 2.1.17 | cargo | `cargo test --lib patch_` (31 passed), `--lib response_` (92 passed), `--lib service_state` (2 passed), `cargo check --target x86_64-pc-windows-gnu --lib` | ✅ | ✅ green |
| 84-02/T1, 84-02/T3, 84-09/T2, 84-12/T1..T3, 84-14/T2, 84-14/T3, 84-15/T2, 84-17/T1..T3, 84-18/T1..T3, 84-19/T1, 84-19/T2 | 84-02, 84-09, 84-12, 84-14, 84-15, 84-17, 84-18, 84-19 | 1-6 | UI | — | Rollouts tab, Start dialog, ring settings, approval card, window dialogs; copy gate on both sides | vitest | `npx vitest run src/__tests__/PatchRollout*.test.tsx src/__tests__/RolloutApprovalCard.test.tsx src/__tests__/rolloutCopy.test.ts src/__tests__/autonomousOpsCopy.test.ts` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Gap closure 2026-11

One row per task of gap plans 84-23..84-28, filled by 84-29 after the whole gate chain ran green together on the final code. `PYT` below is `MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=mongodb://127.0.0.1:27998 MONGO_URI=mongodb://127.0.0.1:27998 backend/venv/bin/python -m pytest ... -q -p no:cacheprovider` on a private mongod (never the live 27017); `RUST` is `cargo test --offline --manifest-path agent-install/omni-agent-rs/Cargo.toml --lib <filter>` with the nodebug target and debug info off.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 84-23/T1 | 84-23 | 1 | PTCH-06 | T-84-65, T-84-66 | A canary row the gate holds at Suggest level is the ring's Install line; approving it sends it once and its result settles the host | mongo | `PYT backend/tests/test_patch_rollout_gap_lines.py` | ✅ | ✅ green |
| 84-23/T2 | 84-23 | 1 | PTCH-06, PTCH-01 | T-84-65 | Later rings at Suggest raise Install lines; deny or 24 h expiry of a held canary line halts; a refused canary row is retried then failed with a reason | mongo | `PYT backend/tests/test_patch_rollout_gap_lines.py` | ✅ | ✅ green |
| 84-23/T3 | 84-23 | 1 | PTCH-01 | T-84-67 | Expired `rollout_not_delivered` rows cannot lower a tenant's level (breaker ignores them) | mongo | `PYT backend/tests/test_patch_rollout_gap_lines.py backend/tests/test_patch_rollout_lines.py backend/tests/test_patch_rollout_cards.py backend/tests/test_patch_rollout_tracer.py backend/tests/test_patch_rollout_controller.py backend/tests/test_patch_rollout_dispatcher.py backend/tests/test_patch_rollout_shadow_stop.py` | ✅ | ✅ green |
| 84-24/T1 | 84-24 | 1 | PTCH-04, PTCH-06 | T-84-68 | Manual rollback route refuses any job carrying `rolloutId` with 409 before an instruction is queued | mongo | `PYT backend/tests/test_patch_rollout_legacy_fence.py` | ✅ | ✅ green |
| 84-24/T2 | 84-24 | 1 | PTCH-04 | T-84-68 | Ordinary jobs still roll back; another tenant's rollout job answers 404; the sentence passes the copy gate | mongo + copy gate | `PYT backend/tests/test_patch_rollout_legacy_fence.py backend/tests/test_patch_rollout_messages.py backend/tests/test_patch_rollout_endpoints.py` | ✅ | ✅ green |
| 84-25/T1 | 84-25 | 2 | PTCH-02 | T-84-69, T-84-70 | A not-found or masked systemd unit reads `absent`, never stopped; the services signal judges it against the pre-change baseline | cargo + mongo | `RUST service_`; `PYT backend/tests/test_patch_rollout_health.py` | ✅ | ✅ green |
| 84-25/T2 | 84-25 | 2 | PTCH-02 | T-84-70 | The baseline is recorded only when an install is queued, merged across attempts, and can never fail the send | mongo | `PYT backend/tests/test_patch_rollout_baseline.py backend/tests/test_patch_rollout_health.py backend/tests/test_patch_rollout_dispatcher.py backend/tests/test_patch_rollout_tracer.py backend/tests/test_patch_rollout_gap_lines.py backend/tests/test_patch_rollout_gap_inflight.py` | ✅ | ✅ green |
| 84-25/T3 | 84-25 | 2 | PTCH-04 | T-84-69 | Windows error 1060 reads `absent`, any other sc failure stays unknown; the shared contract lists the token | cargo + mongo | `RUST service_`; `RUST response_`; `cargo check --offline --lib --target x86_64-pc-windows-gnu`; `PYT backend/tests/test_patch_rollout_contract.py` | ✅ | ✅ green |
| 84-26/T1 | 84-26 | 2 | PTCH-04 | T-84-71 | Every apt downgrade carries `--no-remove`; a revert of a package that is gone installs nothing | cargo | `RUST patch_` | ✅ | ✅ green |
| 84-26/T2 | 84-26 | 2 | PTCH-06 | T-84-72 | A non-boolean `require_reversible` (null included) refuses the job, never reads as false | cargo | `RUST patch_reversible` | ✅ | ✅ green |
| 84-26/T3 | 84-26 | 2 | PTCH-04 | T-84-73 | Job records are saved per package, an unreadable file is kept as `.bad`, the temporary file is fsynced before rename; Windows target compiles | cargo | `RUST patch_`; `cargo check --offline --lib --target x86_64-pc-windows-gnu` | ✅ | ✅ green |
| 84-27/T1 | 84-27 | 3 | PTCH-06 | T-84-74 | An install answered FAILURE or silent past 6 h fails the computer and the ring halts; an expired unread instruction is retried | mongo | `PYT backend/tests/test_patch_rollout_gap_inflight.py` | ✅ | ✅ green |
| 84-27/T2 | 84-27 | 3 | PTCH-04, PTCH-02 | T-84-74, T-84-75 | A revert answered FAILURE, expired or silent reads Not reverted (did not answer) and Resume is unblocked; a denied computer is never shown installed | mongo | `PYT backend/tests/test_patch_rollout_gap_inflight.py backend/tests/test_patch_rollout_revert.py backend/tests/test_patch_rollout_lifecycle.py backend/tests/test_patch_rollout_messages.py` | ✅ | ✅ green |
| 84-27/T3 | 84-27 | 3 | PTCH-06, PTCH-07 | T-84-76 | A row dispatching with no instruction is recovered after 10 min; a send that raises ends the row; every abandoned install closes its job | mongo | `PYT backend/tests/test_patch_rollout_gap_inflight.py backend/tests/test_patch_rollout_gap_lines.py backend/tests/test_patch_rollout_dispatcher.py backend/tests/test_patch_rollout_tracer.py backend/tests/test_patch_rollout_controller.py backend/tests/test_patch_rollout_claims.py` | ✅ | ✅ green |
| 84-28/T1 | 84-28 | 4 | PTCH-04, PTCH-07 | T-84-77, T-84-78 | Cancel of a running rollout stops new work, reverts nothing, ends cancelled with claims released once installs settle or at 6 h; halt, Resume and a second Cancel are refused while cancelling | mongo | `PYT backend/tests/test_patch_rollout_cancel_running.py backend/tests/test_patch_rollout_lifecycle.py backend/tests/test_patch_rollout_endpoints.py backend/tests/test_patch_rollout_messages.py backend/tests/test_patch_rollout_revert.py backend/tests/test_patch_rollout_controller.py backend/tests/test_patch_rollout_gap_inflight.py` | ✅ | ✅ green |
| 84-28/T2 | 84-28 | 4 | PTCH-04, PTCH-06 | T-84-77, T-84-78 | The server offers Cancel on a running card with the nothing-is-reverted sentence; neither Cancel nor Resume while cancelling | mongo + vitest | `PYT backend/tests/test_patch_rollout_views.py backend/tests/test_patch_rollout_views_cancel.py backend/tests/test_patch_rollout_lifecycle.py backend/tests/test_patch_rollout_messages.py`; `npx vitest run src/__tests__/PatchRollout`; `npx tsc --noEmit` | ✅ | ✅ green |

---

## Wave 0 Requirements

- [x] `backend/tests/test_patch_rollout_*.py` (rings, controller, health, boot, revert, windows, gate, claims) covering PTCH-01..07
- [x] `backend/tests/test_maintenance_windows.py` (new model, update route, weekday mapping)
- [x] Rust unit tests for the new pure parsers and reversibility decision in `patch_installer.rs`
- [x] Contract additions in `shared/agent-response-contract.json` and the pinned token list in `response_contract_tests.rs`
- [x] Private mongod on port 27998 started before backend tests
- [x] UI tests under `src/__tests__/` for each new component

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real canary install plus reboot on a disposable host | PTCH-01, PTCH-06 | Needs a non-platform tenant with a Rust agent 2.1.17 enrolled | Start a rollout on a canary group with one disposable host inside an open window; approve the reboot; watch the ring pass |
| Revert on a supported OS | PTCH-04 | Needs a real package manager and an old version still offered | Force a health failure on the canary; confirm the package returns to the pre-rollout version |
| Post-reboot heartbeat feeds the gate | PTCH-02 | Needs a real reboot | After the approved reboot, confirm the gate shows the new boot time and passes |
| Maintenance-window enforcement | PTCH-05 | Needs wall-clock time on live | Start a rollout outside the window; confirm nothing is sent until the window opens |
| Per-stage reboot approval click | PTCH-06 | Needs the live UI and a real agent | Approve the Reboot line on the Autonomous Ops card; confirm one approval covers the stage |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (window math lives in `test_maintenance_windows.py`, the gate in the tracer/registry/health tests; no separate `test_patch_rollout_windows.py` or `_gate.py` was needed)
- [x] No watch-mode flags (`vitest run`, `pytest -q`, `cargo test --lib`)
- [x] Feedback latency < 120s per quick-run file (the whole backend map set takes about 3 min)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-11-07 by /gsd-validate-phase 84. Re-run on the final code: backend map set 547 passed, 0 skipped (private mongod :27998); vitest `src/__tests__` 1,599 passed; cargo `--lib` patch_ 31, response_ 92, service_state 2 passed. Live behaviours stay in Manual-Only above.

**Gap round re-run 2026-11-07 (plan 84-29), final code after 84-23..84-28:** backend map set 1,601 passed, 0 failed (private mongod :27998, `test_patch_rollout_*.py` + maintenance windows + deployment flow + `test_autonomous_ops_*.py` + catalogue slice/parity + route auth baseline); vitest `src/__tests__` 108 files, 1,604 passed; cargo `--lib` patch_ 38, response_ 92, service_ 48 passed; windows-gnu `cargo check --lib` finished; `tsc --noEmit` clean; `npm run build` ok (dist-new only). Every gap task row above has an automated command, so `nyquist_compliant` stays true.

## Validation Audit 2026-11-07

| Metric | Count |
|---|---|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
