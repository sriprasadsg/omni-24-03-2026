---
phase: 84-staged-patch-rollouts
plan: 26
subsystem: patching
status: complete
tags: [patch-rollout, agent, rust, gap-closure, cr-04, wr-13, wr-14, wr-15]

requires:
  - phase: 84-staged-patch-rollouts
    provides: patch_installer / patch_state / patch_reversible agent modules (84-07)
provides:
  - apt_downgrade_args(pkg, previous) with --no-remove, used by every Linux apt downgrade
  - revert_precheck(pkg, installed, recorded), the pure per-package revert decision (not_applicable when the package is gone, reverted when already at the recorded version, None otherwise)
  - strict require_reversible in parse_job (present and not a JSON bool, null included, is an error)
  - patch_state hardening: serde defaults on JobEntry, .bad copy of an unreadable file, sync_all before rename, per-package save in the Linux install loop
affects: [84-25, 84-27]

requirements-completed: [PTCH-04, PTCH-06]

actuals:
  tokens: 9500
  tasks: 3
  commits: 6
commits: 6
plan_head_before: d87d721ce41ccd8993cbaa64288150ccbde5e70f
plan_head_after: 946ce3133dd13d0679bdac05c34215ba7678fa52

tech-stack:
  added: []
  patterns: [pure decision helpers tested without a package manager, fail-closed parsing]

key-files:
  created: []
  modified:
    - agent-install/omni-agent-rs/src/capabilities/patch_installer.rs
    - agent-install/omni-agent-rs/src/capabilities/patch_state.rs
    - agent-install/omni-agent-rs/src/capabilities/patch_reversible.rs

key-decisions:
  - "A null require_reversible is an error like any other non-boolean (plan behaviour list), unlike revert_of where null reads as absent. The backend only ever sends true."
  - "The legacy (no revert_of) rollback gets only the not-installed guard, not the already-at-version answer, so its behaviour otherwise stays the 2.1.16 one."

duration: 25 min
completed: 2026-11-07
---

# Phase 84 Plan 26: Agent revert and install-record hardening Summary

Linux apt downgrades now pass `--no-remove`, a revert of a package that is gone installs nothing, a malformed `require_reversible` refuses the job, and install records are saved per package, kept as `patch_state.json.bad` when unreadable and fsynced before rename. All inside the single unpublished 2.1.17.

## Accomplishments

- CR-04 / T-84-71: `apt_downgrade_args` (top-level, not cfg-gated, so it is unit-tested) returns `apt-get install -y -q --allow-downgrades --no-remove -o ... -o ... -- pkg=previous`. `downgrade` calls it. A refused downgrade fails with apt's own stderr tail, which already reached the result text through the existing error path (confirmed in `downgrade`). The dnf branch is unchanged.
- WR-15: the pure helper is `revert_precheck(pkg, installed: Option<&str>, recorded: &str) -> Option<Value>`. None installed gives failed / `not_applicable` / "The package is not installed any more, so nothing was reverted"; installed at the recorded version gives success / `reverted` (the old "Already at the earlier version" answer); anything else returns None and the downgrade runs. `rollback_job` uses it; the legacy `rollback` checks `installed_version` once and answers with the same not-installed result before any downgrade.
- WR-13 / T-84-72: `parse_job` matches absent -> false, JSON bool -> value, anything else -> `Err("The patch instruction carried an invalid require_reversible")`. Applies to rollback jobs too.
- WR-14 / T-84-73: `#[serde(default)]` on `JobEntry.at/os/changes`; `load_from` copies a non-empty unparseable file to `<path>.bad` (overwriting an older copy, leaving the original) before returning the default; an empty, missing or valid file (including the 2.1.16 flat map) leaves no `.bad`; `save_to` writes, `sync_all`s the temporary file, then renames; the Linux install loop calls `patch_state::save` right after each package whose version changed (final save kept).

## Verification

- `patch_` lib tests: 31 earlier + 7 new = 38 passed (nodebug target, per the VM recipe).
- `cargo check --offline --lib --target x86_64-pc-windows-gnu`: Finished, no errors.
- Acceptance greps: `"--no-remove"` one match in apt_downgrade_args; "not installed any more" and "invalid require_reversible" present; `sync_all` and `.bad` present in patch_state.rs; `patch_state::save` calls in patch_installer.rs went from 3 to 4. `git diff --name-only` over the plan's commits lists only the three plan files, none of the user's WIP files.

## TDD Gate Compliance

RED/GREEN per task, in order, each RED run showing the named tests failing on their planned assertions (not compile errors):

1. Task 1: RED a97ee9d80 (`apt_downgrade_args` extracted without the flag, `revert_precheck` stub returning None; the argv test failed on the missing `--no-remove`, the gone-package test failed on "answered without a downgrade"), GREEN 4e4e6bacf.
2. Task 2: RED 5c8787715 (`unwrap_err` on an accepted "yes"/"true"/1/0/array/null), GREEN f0697f33f.
3. Task 3: RED 3e9c0903f (a short entry wiped `legacy` and the other jobs; no `.bad` written), GREEN 946ce3133. The save round-trip test and the no-`.bad`-for-good-file test pass before and after by design; fsync itself cannot be observed in a unit test.

Tracer gate (Task 1): its `<verify>` was re-run end to end after the fix (33 passed) before expansion.

## Deviations from Plan

None in behaviour. Notes: the "tracer" RED commit carried the extraction of `apt_downgrade_args` and a stub so the tests compile and fail on assertions; the plan's wording "null -> Err" was followed literally for `require_reversible` even though `field()` treats null as absent elsewhere. No edit to capabilities/mod.rs or any user WIP file; nothing was staged except the three plan files.

## Known Stubs

None. The `revert_precheck` stub from the RED commit is replaced in the GREEN commit.

## Threat Flags

None.

## Self-Check: PASSED

- Files modified exist; the six commits (a97ee9d80, 4e4e6bacf, 5c8787715, f0697f33f, 3e9c0903f, 946ce3133) are ancestors of HEAD.
- Plan-level verification re-run: `patch_` 38 passed; windows-gnu lib check Finished.
