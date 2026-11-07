---
phase: 84-staged-patch-rollouts
verified: 2026-11-07T04:30:00Z
status: gaps_found
score: 3/5 must-haves verified
covered_files:
  - ".planning/phases/84-staged-patch-rollouts/84-01-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-01-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-02-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-02-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-03-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-03-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-04-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-04-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-05-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-05-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-06-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-06-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-07-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-07-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-08-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-08-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-09-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-09-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-10-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-10-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-11-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-11-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-12-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-12-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-13-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-13-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-14-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-14-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-15-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-15-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-16-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-16-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-17-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-17-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-18-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-18-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-19-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-19-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-20-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-20-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-21-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-21-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-22-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-22-SUMMARY.md"
  - "agent-install/omni-agent-rs/src/capabilities/patch_installer.rs"
  - "agent-install/omni-agent-rs/src/capabilities/service_watch.rs"
  - "backend/autonomous_ops/rollout/controller.py"
  - "backend/autonomous_ops/rollout/health.py"
  - "backend/autonomous_ops/rollout/installs.py"
  - "backend/autonomous_ops/rollout/lines.py"
  - "backend/autonomous_ops/rollout/signals.py"
  - "backend/autonomous_ops/rollout/start.py"
covered_digest: "v3:sha256:5d90a674e1cea4078204d93687d1e9b8813fe39c4f4bd361ab9c855f183d9fc5"
behavior_unverified: 6
overrides_applied: 0
gaps:
  - truth: "A failed stage halts the rollout and reverts the patch where the operating system supports it (SC3, PTCH-04) - and does so only on a real failure and without harming the host"
    status: partial
    reason: "The halt-and-revert machinery exists and is tested, but two agent defects make it unsafe on Linux. CR-03: classify_systemd maps ActiveState=inactive to Stopped without looking at LoadState, so a watched service that is simply not installed on a Linux computer reads stopped, fails the services signal (signals._from_block returns False for 'stopped') and triggers a halt plus ring revert of a healthy install. CR-04: Linux downgrade (every revert) runs apt-get install -y --allow-downgrades without --no-remove, so a revert can remove other packages."
    artifacts:
      - path: "agent-install/omni-agent-rs/src/capabilities/service_watch.rs"
        issue: "classify_systemd (line 61-73) ignores LoadState; 'inactive' with no bad Result -> Health::Stopped even for a unit that is not-found"
      - path: "agent-install/omni-agent-rs/src/capabilities/patch_installer.rs"
        issue: "downgrade() lines 429-430: apt-get install -y -q --allow-downgrades ... has no --no-remove"
    missing:
      - "Read LoadState in classify_systemd; a not-found unit is Unknown or 'not installed', never Stopped"
      - "Add --no-remove (and refuse the revert when apt would remove anything) to the apt downgrade; add a test that pins it"
  - truth: "Installs run on their own only in the canary ring; every other install and every reboot waits for one approval per stage (SC5, PTCH-06) - and a rollout never hangs without an approval line or a way out"
    status: partial
    reason: "CR-02: at the Suggest level (the level a tenant drops to after the circuit breaker trips or when settings are unreadable) the gate returns state 'suggested'; lines.raise_line counts it as skipped (lines.py:121-123) and canary_auto records nothing, so no approval card is ever raised and the rollout hangs. start.py:293 refuses Start only for 'off'. No test in backend/tests/test_patch_rollout_*.py exercises the Suggest level. CR-01: in installs.canary_auto the non-dispatching branch (gate wants a person) stores installActionId on a host that stays 'waiting'; needs_decision() then returns False for the canary (installs.py:73) and settle only handles state 'installing' (settle.py:209), so the computer is never decided again - the canary ring wedges permanently. WR-03: there is no timeout or failure handling for work in flight and a running rollout cannot be cancelled."
    artifacts:
      - path: "backend/autonomous_ops/rollout/installs.py"
        issue: "canary_auto else-branch (gate wants a person) sets installActionId but leaves state 'waiting'; needs_decision() excludes it forever"
      - path: "backend/autonomous_ops/rollout/lines.py"
        issue: "raise_line skips every decision whose state is not awaiting_approval, including 'suggested'"
      - path: "backend/autonomous_ops/rollout/start.py"
        issue: "preflight blocks only autonomy level 'off' (line 293), not 'suggest'"
    missing:
      - "At Suggest, either refuse Start with a plain reason or raise the approval card (the rollout row already is the operator's intent)"
      - "Make a canary host whose gate row is not dispatching either raise an approval line or return to a decidable state; add a stuck-ring timeout that halts with a reason and allow Cancel while running"
      - "Tests for Suggest level and for a canary row that the gate escalates"
deferred: []
advisory: []
behavior_unverified_items:
  - truth: "A canary computer installs a reversible patch on its own, reboots if needed, and a post-reboot heartbeat is read as the new boot (reboots.is_new_boot)"
    test: "On a real Windows and a real Linux canary computer, start a rollout of one reversible patch inside the window; let it install, reboot and report"
    expected: "Install result, restart card (one approval), new-boot heartbeat, fresh inventory and service block are all read; the ring turns green only after the soak"
    why_human: "Needs a real agent 2.1.17 (not yet published), a real reboot and real heartbeats; unit tests use fixtures"
  - truth: "A failed stage reverts the patch on a supported OS and the computer returns to the earlier version"
    test: "Force a canary failure on a Windows host (revertible update) and on a Linux apt host, observe the ring revert"
    expected: "Earlier version restored; nothing else removed; unsupported hosts read 'halted, not reverted' with a reason"
    why_human: "Real package-manager behaviour; CR-04 means a Linux revert can remove packages, test only on a disposable host"
  - truth: "Rollout installs and advances only inside the Change Management maintenance window on the wall clock (DST, past midnight, weekdays)"
    test: "Define a window a few minutes away, start a rollout, watch nothing install before it opens and instructions expire after it closes"
    expected: "Rows wait for the window; a late instruction is refused at delivery with instruction_expired"
    why_human: "Window maths is unit-tested with injected clocks; real wall-clock enforcement and delivery expiry cannot be observed here"
  - truth: "One approval per stage: the Approve click on a ring card dispatches exactly once and the Reboot card warns 5 minutes ahead"
    test: "Click Approve on an install card and a Reboot card in the live UI, double-click once"
    expected: "Exactly one instruction per computer; restart warns 'Restarting in 5 minutes for updates'"
    why_human: "Live UI plus real agent; UI publish and agent publish are the user's steps"
  - truth: "The Rollouts tab, Start dialog, ring detail, Resume/Cancel and Change Management windows render and behave correctly in a browser (UI-SPEC DEV-1..DEV-4 are implemented but not accepted by the user)"
    test: "Browser pass over Patching > Rollouts, Settings rings, Change Management windows; review DEV-1..DEV-4"
    expected: "Matches 84-UI-SPEC; user accepts or rejects each deviation; UI review scored 17/24 code-only"
    why_human: "Visual and UX judgement; the UI is not published"
  - truth: "Only the first 25 computers per ring are reachable in the UI"
    test: "Start a rollout with a ring of more than 25 computers and try to reach computer 26 onward"
    expected: "Either a paged hosts route exists or the limitation is accepted"
    why_human: "Known open edge in deferred-items.md; accept or schedule"
human_verification:
  - test: "Canary install, reboot and post-reboot heartbeat on real Windows and Linux hosts"
    expected: "Gate reads install result, inventory, new-boot heartbeat and services; ring goes green after soak"
    why_human: "Real agent 2.1.17, reboot and heartbeats"
  - test: "Revert on a supported OS after a forced canary failure (disposable Linux host only until CR-04 is fixed)"
    expected: "Earlier version restored, nothing else removed"
    why_human: "Real package manager"
  - test: "Window enforcement and delivery expiry on the wall clock"
    expected: "Nothing installs outside the window; late instructions refused"
    why_human: "Real clock and delivery"
  - test: "Per-stage Approve and Reboot clicks in the live UI"
    expected: "One dispatch each"
    why_human: "Live UI and agent"
  - test: "Browser pass and acceptance of UI-SPEC DEV-1..DEV-4"
    expected: "User accepts or rejects"
    why_human: "Visual and UX"
  - test: "Accept or schedule the 25-computers-per-ring UI limit"
    expected: "Decision recorded"
    why_human: "Product decision"
---

# Phase 84: Staged Patch Rollouts Verification Report

**Phase Goal:** Operators run patch rollouts in rings, each stage gated by a soak period and a real health check that halts the rollout - and reverts where the operating system supports it - on failure, inside the maintenance window, with one approval per stage for anything risky.
**Verified:** 2026-11-07T04:30:00Z
**Status:** gaps_found
**Re-verification:** No - initial verification

## Goal Achievement

The core machinery is real, wired and well tested: ring model, soak, a pure health-verdict function over four fresh-data signals, failure-rate gate, window-gated dispatcher, approval lines, one-active-rollout unique index, instruction expiry, platform-tenant refusal, controller loop started in app startup, and the exact "halts on failure; reverts where supported" copy. What is not achieved is the safety envelope around it. Four code-confirmed critical defects mean a rollout can hang forever with no approval card (Suggest level, or a canary row the gate escalates), a healthy Linux install can be reverted because a not-installed service reads "stopped", and a Linux revert can remove other packages. These bear directly on "a real health check that halts ... on failure", "reverts where the OS supports it" and "one approval per stage", so they are blockers, not polish.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 / PTCH-01: rings per tenant (canary then larger stages); moves on only after soak passed and gate green | VERIFIED | `health.ring_verdict` returns waiting("soak") until `soakEndsAt`, green only when soak over and every signal True; `rings.py`, `lifecycle.advance`, controller `_check`. `test_patch_rollout_rings.py` (24), `_health.py` (45), `_controller.py`, `_tracer.py` (29) pass: 168 passed on a private mongod 27998 (stopped afterwards). |
| 2 | SC2 / PTCH-02 + PTCH-03: gate combines install result, post-install inventory, fresh heartbeat after reboot and key services; missing data halts; failure-share halt with minimum sample | VERIFIED | `signals.read` builds install/inventory/heartbeat/services, each only from data newer than the change; `ring_verdict` halts `no_data:<signal>` after soak and `failure_share` via integer maths with `minSample`; canary halts on any failure. Caveat: CR-03 makes the services signal fail falsely for a not-installed watched service on Linux (see gap 1). |
| 3 | SC3 / PTCH-04: failed stage halts and reverts where supported; UI says "halts on failure; reverts where supported", never an unqualified rollback | PARTIAL (gap) | Halt, `revert.py` (per-job revert, `require_reversible`, unsupported hosts reported not reverted) and copy (`messages.ASSURANCE`, `RolloutCard.tsx:22`, `rolloutCopy.ts:24`) all present and tested (15 revert tests pass). But CR-04 (Linux revert can remove packages) and CR-03 (false failure triggers revert) make the revert path unsafe on Linux. |
| 4 | SC4 / PTCH-05: installs/advances only inside the Change Management window; nothing installs outside | VERIFIED (logic) | `dispatcher.dispatch` consults `windows_mod.load(...).open_at(now)`; defers otherwise; instruction `expires_at` set to the occurrence end and refused at delivery (`delivery._expired`, `instruction_expired`). Window maths covered by `test_patch_rollout_dispatcher.py` (14) and window tests. Wall-clock enforcement is a human item. |
| 5 | SC5 / PTCH-06 + PTCH-07: automatic installs only in canary and only for reversible classes; everything else and every reboot waits for one approval per stage; platform host never patched; host in at most one active rollout; instructions expire | PARTIAL (gap) | Canary split (`split_canary`), `raise_ring` for later rings, `raise_reboot_line`, unique partial index `one_active_rollout_per_host` (`store.py:86`, migration 031), `PLATFORM_TENANT_ID` refusal (`start.py:291`, `rings.py:161`), expiry at delivery - all present. Broken: CR-02 (no approval card at Suggest, rollout hangs, cannot be cancelled) and CR-01 (a canary row the gate escalates wedges the computer, `installs.py:167-170`, `needs_decision` line 73, `settle.py:209`). |

**Score:** 3/5 truths verified (SC1, SC2, SC4); SC3 and SC5 partial; 6 present-but-behavior-unverified items (listed under Human Verification).

### Deferred Items

None. Later phases (85, 86, 87) do not cover these concerns; Phase 86 live validation covers drills, not these defects.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/autonomous_ops/rollout/*.py` (20 modules, ~5.0k lines) | Controller, health, signals, dispatcher, lines, reboots, revert, windows, rings, start, store, views | VERIFIED (exists, substantive, wired) | `app_startup.py:522-526` starts `rollout_loop`; routes in `patch_rollout_endpoints.py` and `autonomous_ops_response_endpoints.py` (rollout-cards, lines approve/deny) |
| `backend/migrations/031_patch_rollouts.py` | Unique host claim index, lookups | VERIFIED | Index `one_active_rollout_per_host` unique partial; idempotent |
| `components/patchRollouts/*` (13 files) | Rollouts tab, Start dialog, ring detail, Resume/Cancel, windows | VERIFIED (exists, wired from `PatchManagementDashboard.tsx`); not browser-tested | `verify.artifacts`: plans 14, 15, 18 report "Missing pattern" for literal strings that live in server `messages.py` / `rolloutCopy.ts` instead of the named component - plan-text artefact, not a gap; plan 20 test file pattern `master_shadow` absent as a literal but shadow behaviour covered (13 tests pass) |
| Agent `patch_installer.rs`, `patch_reversible.rs`, `patch_state.rs`, `service_watch.rs` | Reversibility check, per-job revert state, service_state | EXISTS and wired; defects CR-03, CR-04 | Rust tests reported green by orchestrator (patch_ 31, service_state 2) |

All 22 plans: `verify.artifacts` 3 plans with literal-pattern misses (above), all others passed; `verify.key-links` passed for every plan.

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| app_startup | rollout loop | `asyncio.create_task(_safe_bg_task(_patch_rollout_loop()))` | WIRED | `app_startup.py:522-526` |
| controller tick | gate / dispatcher / health | `gate.decide`, `dispatcher.dispatch_approved`, `signals.ring_signals` -> `health.ring_verdict` | WIRED | all plan key_links verified by tool |
| canary row not dispatching | any later decision | `installActionId` set, host `waiting` | NOT WIRED | CR-01: nothing ever resumes it |
| Suggest-level decision | approval card | `raise_line` skip on state != awaiting_approval | NOT WIRED | CR-02 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| health verdict | per-host signals | agent `meta.system_patching`, `meta.service_state`, `lastSeen`, `reboots.is_new_boot`, newer-than-change checks | Yes (real agent documents; stale data = no data = halt) | FLOWING |
| Rollout cards | rollout/host docs | `store`, `views.py` | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Tracer, health, controller, revert, lines, rings, dispatcher, shadow/stop tests | `pytest tests/test_patch_rollout_{tracer,health,controller,revert,lines,rings,dispatcher,shadow_stop}.py` on private mongod 27998 | 168 passed in 54s; mongod stopped afterwards | PASS |
| Suggest-level rollout does not hang | grep "suggest" in `test_patch_rollout_*.py` / `rollout_support.py` | no test at all | FAIL (untested; CR-02 confirmed by reading `lines.py` / `start.py`) |
| Orchestrator-reported: vitest 1,599, backend map set 547, cargo patch_ 31 / response_ 92 / service_state 2, windows-gnu check, vite build | not re-run (orchestrator ran on final code) | reported green | accepted as reported, not independently verified |

### Probe Execution

SKIPPED - no `probe-*.sh` declared by the phase plans.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PTCH-01 | 84-01, 84-06, 84-22 et al. | Rings per tenant; soak + green gate | SATISFIED | Truth 1 |
| PTCH-02 | 84-01, 84-08..10 | Gate = install + inventory + heartbeat + services; missing data halts | SATISFIED (with CR-03 caveat) | Truth 2 |
| PTCH-03 | health plans | Failure-rate gate with minimum sample | SATISFIED | `ring_verdict` failure_share / host_failed |
| PTCH-04 | 84-07, revert plans | Halt + revert where supported; qualified copy | PARTIAL | CR-03/CR-04 undermine; copy present |
| PTCH-05 | 84-03, 84-05 | Window-only rollouts | SATISFIED (logic; wall clock is human) | Truth 4 |
| PTCH-06 | 84-01, 84-03 | Canary-only automatic, one approval per stage, reboot approval | PARTIAL | CR-01, CR-02 |
| PTCH-07 | 84-04, 84-06 | Platform host never patched, one active rollout per host, instructions expire | SATISFIED | unique index, platform refusal, delivery expiry |

REQUIREMENTS.md maps PTCH-01..07 to Phase 84 and marks all Complete; every ID is claimed by plan frontmatter and there are no orphans. The Complete marks for PTCH-04 and PTCH-06 are overstated until the gaps close.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/autonomous_ops/rollout/installs.py` | 167-170 | Non-dispatching gate result stores `installActionId`, host stays `waiting`, `needs_decision` false forever | BLOCKER | CR-01 canary ring wedges |
| `backend/autonomous_ops/rollout/lines.py` / `start.py` | 121-123 / 293 | Suggest level silently skipped; Start blocks only `off` | BLOCKER | CR-02 silent hang, no card, no cancel |
| `agent-install/.../service_watch.rs` | 61-73 | `inactive` -> Stopped without LoadState | BLOCKER | CR-03 false failure triggers revert |
| `agent-install/.../patch_installer.rs` | 429-430 | apt downgrade without `--no-remove` | BLOCKER | CR-04 revert may remove packages |
| rollout package | - | WR-03 no timeout for in-flight work; WR-04 denied hosts shown "installed"; WR-10 manual job rollback bypasses rollout gate | WARNING | Related robustness; 47 other review findings open in 84-REVIEW-DISPOSITION.md |
| debt markers (TBD/FIXME/XXX) | - | not scanned per file beyond review; none seen in the files read | INFO | - |

### Human Verification Required

1. **Canary install, reboot, post-reboot heartbeat on real Windows and Linux hosts.** Expected: gate reads all four signals, ring green after soak. Why human: real agent 2.1.17 (unpublished), reboot, heartbeats.
2. **Revert on a supported OS after a forced canary failure** (disposable Linux host only until CR-04 is fixed). Expected: earlier version restored, nothing else removed.
3. **Window enforcement and delivery expiry on the wall clock.** Expected: nothing installs outside the window; late instruction refused.
4. **Per-stage Approve and Reboot clicks in the live UI.** Expected: exactly one dispatch each; 5-minute restart warning.
5. **Browser pass and acceptance of UI-SPEC DEV-1..DEV-4** (implemented, not accepted by the user; UI review 17/24 code-only).
6. **Accept or schedule the 25-computers-per-ring UI limit** (deferred-items.md).

Nothing is deployed: backend restart, migration 031, UI publish, agent 2.1.17 publish and git push are the user's steps.

### Gaps Summary

Two concerns, four root causes, all in the review's CRITICAL list and all confirmed in code:

1. **A rollout can hang with no card and no way out** (CR-01, CR-02, WR-03). Fix at the root: when the gate does not dispatch a canary row, raise an approval line for it (or return the host to a decidable state); at Suggest, raise the card or refuse Start with a plain reason; add a stuck-ring timeout and allow Cancel while running. Add tests for the Suggest level and the escalated canary row - none exist.
2. **The revert path is not safe on Linux** (CR-03, CR-04). Make a not-installed unit read as unknown (LoadState), and add `--no-remove` to the apt downgrade with a pinning test.

Recommended next step: `/gsd-plan-phase 84 --gaps` for the four criticals, plus WR-03/WR-04/WR-10 as they touch the same goal statements; the other warnings can be triaged separately. The four criticals must not ship in agent 2.1.17 or in a live rollout; keep Autonomous Ops rollouts off for real tenants until closed.

---

_Verified: 2026-11-07T04:30:00Z_
_Verifier: Claude (gsd-verifier)_
