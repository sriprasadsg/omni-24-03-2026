---
phase: 84-staged-patch-rollouts
plan: 21
subsystem: release
status: complete
tags: [patch-rollout, agent-version, windows-check, validation-map, live-list, phase-close]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-01..84-20 and 84-22 (all rollout backend, agent and UI work)
provides:
  - agent version 2.1.17 in Cargo.toml and the omni-agent entry of Cargo.lock (no dependency changed)
  - Windows compile check of the agent library (x86_64-pc-windows-gnu) passing with the phase code
  - every automated gate of the phase passing together on the final code
  - 84-VALIDATION.md map with real plan/task ids and a green status per requirement row
  - the ordered live list and DEV-1..DEV-4 for the user
affects: [84-verification, 84-UAT]

requirements-completed: [PTCH-01, PTCH-02, PTCH-03, PTCH-04, PTCH-05, PTCH-06, PTCH-07]

actuals:
  tokens: 9000
  tasks: 2
  commits: 2
commits: 2
plan_head_before: dbebff3bdbf76faa1c22b856d4fb426f360a7971
plan_head_after: 06a7931a024f1c78059ec58dad000c63a8c327ff

tech-stack:
  added: []
  patterns:
    - "version-only commit of a file that carries user hunks: HEAD blob edited, written with hash-object and staged with update-index --cacheinfo, so the user's uncommitted lines stay unstaged"

key-files:
  created: []
  modified:
    - agent-install/omni-agent-rs/Cargo.toml
    - agent-install/omni-agent-rs/Cargo.lock
    - .planning/phases/84-staged-patch-rollouts/84-VALIDATION.md

key-decisions:
  - "Only the two version lines of Cargo.toml and Cargo.lock are committed; the user's uncommitted flate2 dependency lines remain unstaged in the working tree"
  - "84-VALIDATION.md automated commands were corrected to the real test file names (the research names test_patch_rollout_windows.py and test_patch_rollout_gate.py were never created; the windows and gate behaviour lives in test_maintenance_windows.py, test_patch_rollout_delivery.py, test_patch_rollout_views.py, test_patch_rollout_dispatcher.py and test_patch_rollout_lines.py)"
  - "nyquist_compliant, wave_0_complete, status and the sign-off boxes are left for /gsd-validate-phase"

coverage:
  - id: D1
    description: "Agent version 2.1.17 is set in Cargo.toml and the omni-agent entry of Cargo.lock, and nothing else in those files is part of the commit"
    requirement: PTCH-06
    verification:
      - kind: command
        ref: "git show HEAD~1 --stat: Cargo.lock 2 +-, Cargo.toml 2 +-; grep -m1 '^version' Cargo.toml prints 2.1.17"
        status: pass
    human_judgment: false
  - id: D2
    description: "The Windows build of the agent library compiles with the phase code (cfg(windows) paths in patch_installer, patch_reversible, patch_state, service_state)"
    requirement: PTCH-04
    verification:
      - kind: command
        ref: "cargo check --offline --lib --target x86_64-pc-windows-gnu (exit 0, no errors)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every automated gate passes together on the final code: Rust patch_/response_/service_state tests, 1,546 backend tests, 1,599 Vitest tests, production build"
    requirement: PTCH-01
    verification:
      - kind: command
        ref: "pytest (rollout, maintenance, Autonomous Ops, catalogue, route baseline): 1546 passed, 0 skipped"
        status: pass
      - kind: command
        ref: "npx vitest run src/__tests__: 107 files, 1599 tests passed"
        status: pass
      - kind: command
        ref: "npm run build: built, no errors"
        status: pass
    human_judgment: false
  - id: D4
    description: "84-VALIDATION.md maps every requirement row to real plan and task ids (grep -c '| TBD |' prints 0)"
    requirement: PTCH-07
    verification:
      - kind: command
        ref: "grep -c '| TBD |' 84-VALIDATION.md = 0"
        status: pass
    human_judgment: false
  - id: D5
    description: "What only real hosts and the live server can prove (the live list below)"
    requirement: PTCH-06
    verification: []
    human_judgment: true
    rationale: "Real canary install plus reboot, revert, window enforcement and the UI in a browser need a disposable enrolled host, the live server and a person; they are the user's steps"

duration: 40min
completed: 2026-11-07
---

# Phase 84 Plan 21: Version 2.1.17, All Gates Together and the Live List Summary

**One agent version (2.1.17) carries every rollout agent change, the Windows build of the agent compiles with the phase code, every automated gate of the phase passes together on the final code, the validation map names real plans and tasks, and the user's ordered live list is below.**

## Performance

- **Duration:** about 40 min (the backend subset took 9m07s of that)
- **Tasks:** 2
- **Files:** 3 modified (Cargo.toml, Cargo.lock, 84-VALIDATION.md)

## Accomplishments

- **Version 2.1.17 (Task 1).** `Cargo.toml` line 3 and the `omni-agent` entry of `Cargo.lock` read 2.1.17. The agent changes it carries are 84-07 (`patch_reversible_check`, `patch_revert_by_job`, per-job revert records in `patch_state.rs`, the reversibility pre-check on Linux and Windows) and 84-11 (`service_state`). `SUPPORTED_TOKENS` lists `patch_reversible_check`, `patch_revert_by_job` and `service_state`. The commit holds only the two version lines; the user's uncommitted `flate2 = "1"` dependency and comment line in Cargo.toml and the ` "flate2",` line in Cargo.lock were verified present and unstaged after the commit.
- **Windows compile check (Task 1).** `cargo check --offline --lib --target x86_64-pc-windows-gnu` exited 0 with 11 warnings (all in files this phase did not write or pre-existing dead-code notices) and no error. The check covers the library only; nsis is not installed, so no installer was built, and no release binary was built.
- **Every gate together (Task 2).** Run one after another, nothing else running, on a private mongod (port 27998, stopped afterwards):
  - Rust (`CARGO_PROFILE_DEV_DEBUG=0`, target/nodebug): `--lib patch_` 31 passed; `--lib response_` 92 passed; `--lib service_state` 2 passed.
  - Backend: `pytest backend/tests/test_patch_rollout_*.py test_maintenance_windows.py test_patch_deployment_flow.py test_autonomous_ops_*.py test_catalogue_slice_devices.py test_catalogue_slice_autonomous_ops.py test_catalogue_route_parity.py test_route_auth_baseline.py`: **1546 passed, 0 skipped** in 547.54 s. This includes the copy gate (`test_autonomous_ops_copy.py`).
  - Vitest: `npx vitest run src/__tests__`: **107 files, 1599 tests passed** (copy gate on the UI side included through `autonomousOpsCopy.test.ts` and `rolloutCopy.test.ts`).
  - Build: `npm run build` finished without error (output in `dist-new/`, gitignored, not live).
- **Validation map (Task 2).** Every `TBD` row of the Per-Task Verification Map now names the plans, tasks, waves, threat refs, the real test commands and a green status; the Wave 0 boxes are ticked. `nyquist_compliant`, `wave_0_complete`, `status` and the sign-off section are untouched for `/gsd-validate-phase`.

## Task Commits

1. Task 1: `8ae60e036` chore(84-21) agent version 2.1.17 carries every rollout change
2. Task 2: `06a7931a0` docs(84-21) validation map names real plans and tasks for every requirement

## Deviations from Plan

None - plan executed exactly as written. Two small notes, neither a deviation from the plan's intent: the Windows check and the Rust tests used the environment's required `CARGO_TARGET_DIR=.../target/nodebug` and `CARGO_PROFILE_TEST_DEBUG=0` settings (the plan's command omitted the target-dir on the check); and 84-VALIDATION.md command cells were corrected to the file names that exist (see key-decisions).

**Total deviations:** 0.

## Flaky tests (reported, not weakened)

Seen once during the phase and not seen in this run (all passed on the single full run here): backend `test_patch_rollout_claims.py::test_two_starts_at_once...` (race), frontend `src/__tests__/PatchRolloutsTab.test.tsx` first-load-failure test.

## Open edges recorded by earlier plans (not fixed here)

- 84-13: a refused or overdue revert restart is not asked again; a computer that never settles is never reverted.
- 84-16: a ring halted by a denied or expired approval can only be cancelled; a reverted ring reads red on resume; a returning computer that needs a restart after a late install is not asked.
- 84-18 (deferred-items.md): only the first 25 computers per ring are reachable; needs a paged hosts route such as `GET /api/patch-rollouts/{id}/rings/{index}/hosts?offset=&limit=` and a call from `RingDetail`.
- 84-20: a stop pressed and cleared between two controller ticks never records `stoppedSince`; three stop cancellations consume `MAX_ATTEMPTS`; a live rollout under shadow still sends rows approved earlier.

## Live list (the user's steps, in this order; the executor performed none of them)

0. Before building or publishing 2.1.17: the working tree holds the user's uncommitted Rust work (gzip heartbeat posts, `collect_due` intervals, `flate2`, plus edits in `capabilities/mod.rs`, `heartbeat.rs`, `buffer.rs`, `config.rs`, `lib.rs`, `main.rs`). Cargo builds the working tree, so a release built now would include all of it. Decide whether to commit that work or set it aside first.
1. Windows target: the library compiles (this plan). The installer (nsis) and a real Windows run are not covered; the reversibility check and revert on a real Windows host stay unproven until step 8.
2. Run the full backend suite alone and compare by test name with the baseline in memory (5,135 pass plus the known 5 failures, including the two nav-count-190 pins).
3. Run migration 031, restart the backend, publish the UI (`dist-new`).
4. Publish agent 2.1.17, bump `_LATEST_AGENT_VERSION`, and confirm `meta.response_actions.tokens` on a test host lists `patch_reversible_check`, `patch_revert_by_job` and `service_state`, and that `meta.service_state` appears. Until this is done no host reports the new tokens: canary installs wait for approval, Linux reverts say the agent does not support it yet, and services read Not checked (fail closed).
5. On a non-platform tenant with an enrolled Rust 2.1.17 agent on a disposable host: set a time zone and a maintenance window, set rings (Canary with that host's group), and confirm the window shows in Change Management and the ring chip on Agent Groups.
6. Tenants stay in shadow: a rollout started now is a simulation; expect Would install rows only. A Super Admin lifts the test tenant for steps 7-11.
7. A real canary install plus reboot: start a rollout inside the window; a reversible Linux package installs on its own or appears as an approval line with the reason; approve the Reboot line and watch the 5-minute warning.
8. The post-reboot heartbeat feeds the gate: the Heartbeat after restart row turns Passed only after the new boot.
9. Revert on a supported OS: force a failure (stop a watched service) so the ring halts; confirm the package returns to its pre-rollout version and the row says Reverted, or Not reverted with the reason.
10. Window enforcement: start a rollout while the window is closed; nothing is sent until it opens, and an instruction left over after it closes is never delivered.
11. The per-ring reboot approval click on the Autonomous Ops card, once for the whole line.
12. Browser pass of the Rollouts tab, Start dialog, rings card, ring detail, Resume and Cancel, the approval card, Settings windows and Change Management windows in light and dark at 640, 1024 and 1280 px, including the ring strip on one row at 1280 px and no sideways scroll in the hosts table.
13. git push.

## UI-SPEC deviations pending user review (copied from 84-UI-SPEC.md; none accepted)

| ID | Contract text it departs from | What the plans do instead | Why | Implemented by |
|----|-------------------------------|---------------------------|-----|----------------|
| DEV-1 | Section 6, last paragraph: Approve and Deny use the same approvals API as incident cards (`services/autonomousOpsApi.ts`). | Approve and Deny on an Install, Reboot or revert-restart line call `POST /api/autonomous-ops/rollout-lines/{rolloutId}/{ring}/{line}/approve` and `/deny`, which run `approvals.approve` or `approvals.deny` once per computer row of that line. Same permission (`control:autonomous_ops`), signed-in session (API keys refused), stop rule (Approve refused, Deny allowed), 24 h expiry and single use. Card anatomy, labels, aria-labels, toasts and result texts stay as section 6 states. | Every line is one ledger row per computer (84-RESEARCH Open Questions (RESOLVED) 2), so one click has to settle several rows. | 84-03 (lines), 84-10 (routes and card payload), 84-15 (card) |
| DEV-2 | Section 4, Health check: the `Services` row chips are `Passed` / `Failed` / `Waiting`. | Adds a fourth state `Not checked` (existing OUTLINE chip, `InfoIcon`) with the text `{services} can't be checked on {k} of {n} computers until their agent is updated.` for computers whose agent does not report `service_state` yet (agents before 2.1.17). It is never shown as `Passed` and does not halt the ring; a reported service failure still fails the computer. No new tone. | Without a positive service report, `Passed` would only mean "nothing complained" (84-RESEARCH Open Questions (RESOLVED) 6). | 84-02 (copy and chip), 84-08 (signal), 84-11 (agent report), 84-18 (ring detail) |
| DEV-3 | Section 3, `Check before starting`: rows are Window, Rings, Canary per operating system, Left out, Offline now. | Computers that cannot take a rollout (agent too old, patch capability not ticked, unsupported operating system, busy with another patch job, on the never-touch list) are listed in the Left out area with one reason sentence each, never dropped silently. Two blockers the section does not list are added: Autonomous Ops off for the organization (`Autonomous Ops is off for this organization, so a rollout can't run.`) and the 500-computer cap (`A rollout can reach at most 500 computers. Pick fewer patches or split your rings.`). | 84-RESEARCH Open Questions (RESOLVED) 3; the gate refuses every install while Autonomous Ops is off; the cap bounds one rollout (84-RESEARCH Security Domain). | 84-02 (copy), 84-06 (preflight), 84-17 (Start dialog) |
| DEV-4 | Design System, the New files table and the Copy gate paragraph: names `components/PatchRollout*.tsx`, `components/AutonomousOpsRolloutCard.tsx`, `components/MaintenanceWindowDialog.tsx`, `components/ChangeManagementWindows.tsx`, `services/patchRolloutApi.ts`, each new file added one by one to the copy gate `files` list. | New rollout UI files live in `components/patchRollouts/` and `services/patchRollouts/` (file mapping in 84-UI-SPEC.md). The copy gate gains a `directories` list (`backend/autonomous_ops/rollout`, `components/patchRollouts`, `services/patchRollouts`) walked recursively on the pytest and the Vitest side; a listed directory that is missing or empty fails. The `files` list keeps working for new files outside those folders (`backend/patch_rollout_endpoints.py` is added to it by 84-09), and `OsPatchesTab.tsx` and `ChangeManagementDashboard.tsx` stay off the gate as the contract says. | The contract calls the names a recommendation. Directory coverage is the same or wider (files added later are scanned too) and lets the UI plans run in parallel without all editing the same three list files. | 84-02 (gate, `rolloutCopy.ts`, `types.ts`); files placed by 84-12, 84-14, 84-15, 84-17, 84-18 |

## Known Stubs

None.

## Threat Flags

None. This plan changes a version string and a planning document; T-84-60 (unpublished code assumed live) is mitigated by live-list steps 3-4 and by every agent-dependent path failing closed by token until 2.1.17 is published; T-84-61 (live rollout on real tenants) is mitigated by tenants staying in shadow until a Super Admin lifts them (step 6).

## Self-Check: PASSED

- `agent-install/omni-agent-rs/Cargo.toml` line 3 = 2.1.17: FOUND; `Cargo.lock` omni-agent entry = 2.1.17: FOUND.
- `grep -c "| TBD |" 84-VALIDATION.md` = 0: PASS.
- Commits `8ae60e036` and `06a7931a0` are ancestors of HEAD: FOUND.
- User's `flate2` lines still present and unstaged in Cargo.toml and Cargo.lock: FOUND.
- Private mongod on port 27998 stopped: confirmed.
