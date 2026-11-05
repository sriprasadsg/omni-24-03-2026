---
phase: "84"
slug: "staged-patch-rollouts"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-05"
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

Requirement-level map from research; the planner's task IDs replace the `TBD` column.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | PTCH-01 | — | Rings from agent groups snapshot at Start; next ring only after soak and green gate; controller resumes after restart | unit + mongo | `pytest backend/tests/test_patch_rollout_rings.py backend/tests/test_patch_rollout_controller.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PTCH-02 | — | Each missing signal halts; `skipped` is not success; boot baseline rejects the old boot | unit | `pytest backend/tests/test_patch_rollout_health.py backend/tests/test_patch_rollout_boot.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PTCH-03 | — | Canary halts on any failure; later rings halt above 10% once 10 hosts reported | unit | `pytest backend/tests/test_patch_rollout_health.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PTCH-04 | — | Halt reverts through undo, also during a stop; unsupported OS says not reverted; no bare "rollback" copy | mongo + copy gate | `pytest backend/tests/test_patch_rollout_revert.py backend/tests/test_autonomous_ops_copy.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PTCH-05 | — | Window math (overnight, DST, weekday mapping); no window blocks Start; outside window nothing dispatches; tenant-isolated window routes | unit + api | `pytest backend/tests/test_patch_rollout_windows.py backend/tests/test_maintenance_windows.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PTCH-06 | — | Canary auto only with agent token and reversible class; all else and every reboot needs approval; reconciler skips rollout rows | mongo | `pytest backend/tests/test_patch_rollout_gate.py backend/tests/test_autonomous_ops_reconciler.py backend/tests/test_autonomous_ops_registry.py -q` | ❌ W0 / extend | ⬜ pending |
| TBD | TBD | TBD | PTCH-07 | — | Platform tenant and protected hosts never claimed; one active rollout per host; expired instruction never delivered; legacy service writes nothing | mongo | `pytest backend/tests/test_patch_rollout_claims.py backend/tests/test_autonomous_ops_stop.py backend/tests/test_autonomous_ops_structural.py -q` | ❌ W0 / extend | ⬜ pending |
| TBD | TBD | TBD | Agent | — | Reversibility pre-check, per-job revert state, `service_state`, tokens equal the contract | cargo | `cargo test --lib patch_installer` and `--lib response_contract` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | UI | — | Rollouts tab, Start dialog, ring settings, approval card, window dialogs | vitest | `npx vitest run src/__tests__/PatchRollouts*.test.tsx` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_patch_rollout_*.py` (rings, controller, health, boot, revert, windows, gate, claims) covering PTCH-01..07
- [ ] `backend/tests/test_maintenance_windows.py` (new model, update route, weekday mapping)
- [ ] Rust unit tests for the new pure parsers and reversibility decision in `patch_installer.rs`
- [ ] Contract additions in `shared/agent-response-contract.json` and the pinned token list in `response_contract_tests.rs`
- [ ] Private mongod on port 27998 started before backend tests
- [ ] UI tests under `src/__tests__/` for each new component

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
