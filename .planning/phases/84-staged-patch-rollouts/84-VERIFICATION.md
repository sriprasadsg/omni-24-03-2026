---
phase: 84-staged-patch-rollouts
verified: 2026-11-07T10:10:00Z
status: human_needed
score: 5/5 must-haves verified
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
  - ".planning/phases/84-staged-patch-rollouts/84-23-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-23-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-24-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-24-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-25-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-25-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-26-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-26-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-27-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-27-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-28-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-28-SUMMARY.md"
  - ".planning/phases/84-staged-patch-rollouts/84-29-PLAN.md"
  - ".planning/phases/84-staged-patch-rollouts/84-29-SUMMARY.md"
  - "agent-install/omni-agent-rs/src/capabilities/patch_installer.rs"
  - "agent-install/omni-agent-rs/src/capabilities/service_watch.rs"
  - "backend/autonomous_ops/rollout/cancelling.py"
  - "backend/autonomous_ops/rollout/inflight.py"
  - "backend/autonomous_ops/rollout/installs.py"
  - "backend/autonomous_ops/rollout/lifecycle.py"
  - "backend/autonomous_ops/rollout/lines.py"
  - "backend/autonomous_ops/rollout/settle.py"
  - "backend/autonomous_ops/rollout/signals.py"
  - "backend/patch_core_endpoints.py"
covered_digest: "v3:sha256:09fc78a68da5cd65dd20daf0b8216f1055eccbf6c5f81ed7590184d5d688acae"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "PTCH-04: CR-03 a not-installed watched service read stopped (false halt + revert) - now token `absent`, judged against a pre-change baseline"
    - "PTCH-04: CR-04 apt downgrade without --no-remove - now apt_downgrade_args carries --no-remove, pinned by a test"
    - "PTCH-06: CR-01 a canary row the gate held wedged the host - now tracked as the ring's Install line (lines.track_line)"
    - "PTCH-06: CR-02 Suggest level raised no approval line - now OPEN_ROW_STATES covers `suggested`, the row becomes a card"
    - "WR-03 in-flight work had no bound and a running rollout could not be cancelled - inflight.RESULT_DEADLINE, settle.recover_unsent, cancelling.tick, Cancel on a running rollout"
    - "WR-04 denied hosts read installed - waitReason not_approved"
    - "WR-10 manual job rollback bypassed the rollout gate - 409 ROLLOUT_OWNED_JOB_DETAIL"
  gaps_remaining: []
  regressions: []
residual_warnings:
  - id: WR-25
    area: "PTCH-04 (revert on Linux/apt)"
    summary: "installed_version uses dpkg-query -W, which also succeeds for an `rc` package (removed, config kept); a revert could then re-install a package an administrator removed after the patch. No package is removed (--no-remove holds)."
    disposition: "acceptable residual, fix before the 2.1.17 publish (cheap, status-aware dpkg query)"
  - id: WR-26
    area: "PTCH-06/07 (in-flight settle)"
    summary: "A `sent` instruction past its expiresAt reads not_delivered. Needs the one-shot `accepted` post to be lost AND the install to still be running at window close; a lost accepted post is normally superseded by the retried final result."
    disposition: "acceptable residual (double fault); fix is one condition in inflight.instruction_outcome"
  - id: WR-27
    area: "PTCH-04 (revert of an offline computer)"
    summary: "An undo never fetched has no expiresAt; after 6 h it reads `no_answer` / Not reverted while the instruction stays pending and runs when the computer returns. The revert still happens (safe direction); the card is wrong for that window; the poll route writes sent_at but inflight reads delivered_at."
    disposition: "acceptable residual; fix before relying on revert of laptops that go offline"
  - id: WR-31
    area: "PTCH-06 / D-16 (Cancel of a running rollout)"
    summary: "A controller pass that loaded the rollout before the Cancel stamp can still send canary installs in that one pass (canary_auto/_send do not re-read cancelRequested). Bounded to one tick; Cancel keeps patches and reverts nothing by design, so the extra installs are ordinary canary installs that the cancel tick then waits for."
    disposition: "acceptable residual"
  - id: "WR-28, WR-29, WR-30, WR-32, IN-24, IN-25, IN-26"
    area: "wording / visibility / hardening"
    summary: "Failed revert worded as `did not answer`; Cancel's unfetched-instruction rows use the halt reason text; no `cancelling` flag on the card; 409 text for a finished rollout points to a screen that cannot revert; masked-but-active unit reads absent; unknown baseline for a late-added watched name stays no-data; patch_state tmp file not cleaned / dir not synced."
    disposition: "warnings/info, none changes a success criterion"
human_verification:
  - test: "Canary install, reboot and post-reboot heartbeat on a real Windows and a real Linux computer (agent 2.1.17, not yet published)"
    expected: "Install result, one restart approval, new-boot heartbeat, fresh inventory and service block are read; the ring goes green only after the soak"
    why_human: "Real agent, real reboot and heartbeats; tests use fixtures"
  - test: "Force a canary failure on a disposable Linux apt host and a Windows host with a revertible update"
    expected: "Earlier version restored, nothing else removed (--no-remove), unsupported hosts read `halted, not reverted` with a reason; also try an apt host where the package was removed (`rc`) to see WR-25"
    why_human: "Real package-manager behaviour"
  - test: "Define a Change Management window a few minutes away, start a rollout, watch the wall clock"
    expected: "Nothing installs before the window opens; a late instruction is refused at delivery with instruction_expired"
    why_human: "Window maths is unit-tested with injected clocks; wall-clock enforcement and delivery expiry cannot be observed here"
  - test: "Approve on an install card and on a Reboot card in the live UI (double-click once); Cancel a running rollout in the live UI"
    expected: "Exactly one instruction per computer; restart warns 'Restarting in 5 minutes for updates'; Cancel keeps patches and the rollout ends cancelled"
    why_human: "Live UI plus real agent; UI publish and agent publish are the user's steps"
  - test: "Browser pass over Patching > Rollouts, Start dialog, ring detail, Resume/Cancel, Settings rings, Change Management windows; accept or reject UI-SPEC DEV-1..DEV-4"
    expected: "Matches 84-UI-SPEC; user decision recorded"
    why_human: "Visual and UX judgement; UI review scored 17/24 code-only; dist-new is unpublished"
  - test: "Start a rollout with a ring of more than 25 computers"
    expected: "A paged hosts route exists or the limitation is accepted"
    why_human: "Known open edge in deferred-items.md; product decision"
  - test: "Decide whether to fix WR-25, WR-26, WR-27 and WR-31 before publishing agent 2.1.17 / enabling rollouts for real tenants"
    expected: "Decision recorded"
    why_human: "Residual-risk acceptance"
---

# Phase 84: Staged Patch Rollouts Verification Report

**Phase Goal:** Operators run patch rollouts in rings, each stage gated by a soak period and a real health check that halts the rollout - and reverts where the operating system supports it - on failure, inside the maintenance window, with one approval per stage for anything risky.
**Verified:** 2026-11-07T10:10:00Z
**Status:** human_needed
**Re-verification:** Yes - after gap closure (plans 84-23..84-29)

## Goal Achievement

All four code-confirmed criticals from the first verification are closed in the code, not just in the SUMMARYs, and each has tests that fail without the fix. What remains is (a) behaviour only a real host, real clock or real browser can show, and (b) four residual warnings from the fresh review that I read in the code and judge acceptable, with a recommendation to fix before the agent is published.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 / PTCH-01: rings per tenant; a rollout moves on only after the soak and a green gate | VERIFIED | Unchanged since the first verification (`health.ring_verdict`, `rings.py`, `lifecycle.advance`). Regression run: all 24 `backend/tests/test_patch_rollout_*.py` files, 437 passed on a private mongod (port 27998, stopped afterwards). |
| 2 | SC2 / PTCH-02 + PTCH-03: gate = install result + post-install inventory + fresh heartbeat + key services; missing data halts; failure-share halt with minimum sample | VERIFIED | `signals.read` / `_from_block` (signals.py:73-97). The CR-03 caveat is closed: `classify_systemd` reads `LoadState` first and returns `Health::Absent` for not-found/masked (service_watch.rs:69-72, `systemctl show -p LoadState,...` at :119); Windows exit 1060 maps to Absent (:125); token `absent` (:237). The backend judges `absent` against `servicesPresentBefore/AbsentBefore` recorded just before the send (installs.py `_send` -> `signals.record_service_baseline`): present before and absent after fails, absent before and after leaves the wanted list, no record is no data (fail closed). Tests: `test_patch_rollout_baseline.py`, `test_patch_rollout_health.py`; cargo `service_` 48 passed. |
| 3 | SC3 / PTCH-04: failed stage halts and reverts where supported, without harming the host; UI says "halts on failure; reverts where supported" | VERIFIED (residuals WR-25, WR-27) | CR-04 closed: `apt_downgrade_args` (patch_installer.rs:91-98) has `--allow-downgrades --no-remove ... -- pkg=previous` and `downgrade()` uses it; pure helper pinned by a unit test. Also present: `revert_precheck` (a package gone installs nothing, already-at-version is success), strict `require_reversible`, per-package save, `.bad` copy of an unreadable state file. CR-03 closed (truth 2), so a healthy Linux install is no longer reverted for a missing service. WR-10 closed: `rollback_patch_job` answers 409 for any job with `rolloutId` after the tenant check (patch_core_endpoints.py:278-281; 4 fence tests). Cancel of a running rollout (KD-84-G3) stamps `cancelRequested`, reverts and halts nothing (`cancelling.tick`, `lifecycle.finish_cancel`; 4 cancel tests + 4 view tests), consistent with D-16. cargo `patch_` 38 passed. Residuals: WR-25 (`rc` package re-installed by a revert - no removal, narrow admin-action precondition) and WR-27 (offline computer's queued revert reads "Not reverted" after 6 h but still runs later) - warnings, not a broken criterion. |
| 4 | SC4 / PTCH-05: installs/advances only inside the Change Management window | VERIFIED (logic); wall clock is human | `dispatcher.dispatch` consults `windows_mod.load(...).open_at(now)`; instruction `expiresAt` = window close, refused at delivery. Dispatcher/window tests in the 437 pass. |
| 5 | SC5 / PTCH-06 + PTCH-07: automatic installs only in canary and only for reversible classes; everything else and every reboot waits for one approval per stage; platform host never patched; one active rollout per host; instructions expire | VERIFIED (residuals WR-26, WR-31) | CR-01/CR-02 closed: in `canary_auto`, a gate result in `lines.OPEN_ROW_STATES = ("awaiting_approval", "suggested")` goes through `lines.track_line` (installs.py:~176-181), which stores the row under `lineActionIds.install` and `linePatchIds`, so `needs_decision` is False for the right reason and the ring has a card; `raise_line` uses the same constant (lines.py:124). A refused row stores only the attempt and is retried, then fails the host after MAX_ATTEMPTS (`_refused`). `dispatcher` stores `installJobId/installInstructionId` on approval. Tests `test_patch_rollout_gap_lines.py` (Suggest-level row becomes the Install line, nothing is sent; approving sends once and the result settles the host) pass. WR-03 closed: `inflight.RESULT_DEADLINE` (6 h), `DISPATCH_CLAIM_BOUND`, `settle.recover_unsent`, `close_job`, and a running rollout can be cancelled. WR-04 closed: denied/expired approval row leaves the host `waiting` / `not_approved`, never `installed` (settle.py:273, views.py:162, messages.py:85). Unique index `one_active_rollout_per_host` (migration 031), platform-tenant refusal and delivery expiry unchanged. Residuals: WR-26 (double fault) and WR-31 (one-tick Cancel race; extra installs are ordinary reversible canary installs and Cancel keeps patches by design). |

**Score:** 5/5 truths verified; 0 present-but-behavior-unverified (transitions are exercised by passing tests; live-host behaviour is listed under Human Verification).

### Disposition of the fresh review findings (84-REVIEW.md, all `open`)

I read the cited code for each.

| Finding | Confirmed in code | Real gap in a success criterion? | Decision |
|---------|-------------------|----------------------------------|----------|
| WR-25 `rc` package re-installed by revert (patch_installer.rs:379-392, 479-482) | Yes: `installed_version` returns Some for any non-empty `dpkg-query -W` version; no status check | SC3 "without harming the host": only in the case an admin removed the package after the patch; it installs an older version of software the host had before the rollout, removes nothing. Violates the softer D-15 sentence "a revert never adds software" | Acceptable residual; fix before the 2.1.17 publish (status-aware query + test) |
| WR-26 expired `sent` read not_delivered (inflight.py:63-65) | Yes; agent's `accepted` post has `attempts = 1` (instruction_report.rs:59), poll route sets `sent` (agent_tasks_endpoints.py:61) | No: needs a lost `accepted` post and a still-running install at window close; the final result post retries and moves the status to success/failure | Acceptable residual; simple fix (only `pending` is provably undelivered) |
| WR-27 unfetched undo judged no_answer after 6 h; reads `delivered_at`, route writes `sent_at` (inflight.py:66-69; revert.py:236-253) | Yes | No: the revert still executes later (safe direction). The card and Resume gating can be wrong for an offline computer | Acceptable residual; flag for the first offline-host drill |
| WR-31 stale-copy Cancel race (controller.py:300-330, installs.py) | Yes: `rollout` is read once per tenant pass; `canary_auto`/`_send` never re-read `cancelRequested` | No: bounded to one controller pass; D-16 Cancel never reverts and keeps patches, and the cancel tick waits for the installs it did not prevent | Acceptable residual |
| WR-28, WR-29, WR-30, WR-32 | Wording / visibility | No | Warnings |
| IN-24, IN-25, IN-26 | Hardening | No (IN-25 fails closed - no data - never a false green) | Info |

### Deferred Items

None. Phases 85-87 do not cover these concerns.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/autonomous_ops/rollout/*.py` (now incl. `inflight.py`, `cancelling.py`) | Controller, health, signals, dispatcher, lines, revert, settle, cancel | VERIFIED (exists, substantive, wired) | controller calls `settle.settle`, `cancelling.tick`, `revert.tick`, `dispatcher.dispatch_approved`, `_ring`; loop started in `app_startup.py` (verified in the first pass, unchanged) |
| `backend/migrations/031_patch_rollouts.py` | Unique host claim index | VERIFIED | unchanged; not yet applied to the live database (restart is the user's step) |
| `agent-install/omni-agent-rs/src/capabilities/{patch_installer,patch_state,patch_reversible,service_watch}.rs` | Revert hardening, absent token | VERIFIED | cargo tests green (below) |
| `components/patchRollouts/*`, `services/patchRollouts/*` | Rollouts UI incl. Cancel on a running card | VERIFIED (exists, wired); not browser-tested | vitest `src/__tests__/PatchRollout*`: 8 files, 272 passed |
| `shared/agent-response-contract.json` | `absent` token in the service_state contract | VERIFIED | contract tests (`response_` 92 per orchestrator) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| canary row the gate holds (awaiting_approval or suggested) | an approval card | `lines.track_line` -> `lineActionIds.install` | WIRED (was NOT_WIRED) | installs.py `canary_auto`; test passes |
| Suggest-level decision | approval card | `lines.OPEN_ROW_STATES` in `raise_line` | WIRED (was NOT_WIRED) | lines.py:32, :124 |
| watched service `absent` | services signal | `signals._from_block` vs host baseline | WIRED | baseline written in `_send` after a queued result |
| revert argv | apt | `apt_downgrade_args` in `downgrade()` | WIRED | `--no-remove` |
| manual job rollback | rollout gate | 409 on `rolloutId` | WIRED | patch_core_endpoints.py:278 |
| in-flight instruction | end state | `inflight.instruction_outcome` in settle (:127, :185) and revert | WIRED | see WR-26/27 for edge cases |
| Cancel (running) | controller | `cancelRequested` -> `cancelling.tick` | WIRED | controller.py:~306 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| health verdict | per-host signals | agent `meta.system_patching`, `meta.service_state`, `lastSeen`, boot identity; baseline from the agent's last block read before the send | Yes (stale or missing data = no data = halt) | FLOWING |
| Rollout cards | rollout/host/ledger docs | `store`, `views.py` | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All Phase 84 backend rollout suites (24 files) | `pytest tests/test_patch_rollout_*.py` against a private mongod on 27998 | 437 passed in 174 s; mongod stopped afterwards (live 27017 untouched) | PASS |
| Agent service watch incl. absent token | `cargo test --offline --lib service_` (nodebug recipe) | 48 passed | PASS |
| Agent patch installer / state / reversible | `cargo test --offline --lib patch_` | 38 passed | PASS |
| Rollout UI | `npx vitest run src/__tests__/PatchRollout` | 8 files, 272 passed | PASS |
| Orchestrator's full-gate chain (backend map set 1,601, windows-gnu check, full vitest 1,604, tsc, vite build) | not re-run | accepted as reported | not independently verified |

### Probe Execution

SKIPPED - no `probe-*.sh` declared by the phase plans.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PTCH-01 | 84-01, 84-06, 84-22, 84-23 | Rings per tenant; soak + green gate | SATISFIED | Truth 1 |
| PTCH-02 | 84-01, 84-08..10, 84-25, 84-27 | Gate = install + inventory + heartbeat + services; missing data halts | SATISFIED | Truth 2; CR-03 closed |
| PTCH-03 | health plans | Failure-rate gate with minimum sample | SATISFIED | `ring_verdict` failure_share / host_failed (45 health tests) |
| PTCH-04 | 84-07, 84-13, 84-24..28 | Halt + revert where supported; qualified copy | SATISFIED (residuals WR-25, WR-27) | Truth 3 |
| PTCH-05 | 84-03, 84-05 | Window-only rollouts | SATISFIED (logic; wall clock is human) | Truth 4 |
| PTCH-06 | 84-01, 84-03, 84-23, 84-26..28 | Canary-only automatic, one approval per stage, reboot approval | SATISFIED (residuals WR-26, WR-31) | Truth 5; CR-01/CR-02 closed |
| PTCH-07 | 84-04, 84-06, 84-27, 84-28 | Platform host never patched, one active rollout per host, instructions expire | SATISFIED | unique index, platform refusal, delivery expiry |

All seven IDs appear in plan frontmatter (84-29 lists all seven as completed); REQUIREMENTS.md maps PTCH-01..07 to Phase 84, currently marked "Gaps Found" in its traceability table and unchecked in its list (84-29 deliberately left it untouched). No orphans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `patch_installer.rs` | 379-392 | installed check not status-aware on apt | WARNING | WR-25 |
| `inflight.py` | 63-69 | `sent` after expiry = not_delivered; undo with no expiry judged by `created_at` | WARNING | WR-26, WR-27 |
| `installs.py` / `controller.py` | 127-170 / 300-330 | no re-check of `cancelRequested` in the send path | WARNING | WR-31 |
| debt markers (TBD/FIXME/XXX) | - | none in the rollout package, agent patch/service files, or rollout UI | - | - |

The four first-round BLOCKER patterns (installs.py CR-01 branch, lines.py/start.py Suggest, service_watch.rs, apt downgrade) are gone.

### Human Verification Required

1. **Canary install, reboot, post-reboot heartbeat on real Windows and Linux hosts** (agent 2.1.17 unpublished). Expected: all four signals read, ring green after soak.
2. **Revert on a disposable Linux apt host and a Windows host after a forced canary failure**, including a host where the package was removed (`rc`) to see WR-25. Expected: earlier version restored, nothing else removed.
3. **Window enforcement and delivery expiry on the wall clock.** Expected: nothing installs outside the window; late instruction refused.
4. **Per-stage Approve, Reboot and Cancel-while-running clicks in the live UI.** Expected: one dispatch each; 5-minute restart warning; Cancel keeps patches.
5. **Browser pass and acceptance of UI-SPEC DEV-1..DEV-4** (UI review 17/24 code-only; dist-new unpublished).
6. **25-computers-per-ring UI limit**: accept or schedule.
7. **Accept or fix WR-25, WR-26, WR-27, WR-31** before publishing agent 2.1.17 and before enabling rollouts for real tenants.

Nothing is deployed: backend restart with migration 031, UI publish of dist-new, agent 2.1.17 publish and git push are the user's steps.

### Gaps Summary

No gaps remain. Both gaps from the first verification are closed with code and tests: gap 1 (PTCH-04) by `Health::Absent` plus the pre-change service baseline and by `--no-remove` on the apt downgrade; gap 2 (PTCH-06) by routing every held canary row (Suggest, escalated, rate-limited) to a tracked approval line, plus in-flight bounds and Cancel of a running rollout. The status is human_needed, not passed, because the goal's central claims (a real install, reboot and revert on a real host, the maintenance window on the wall clock, an approval click) cannot be observed in this environment, and four residual warnings need a keep-or-fix decision from the user.

---

_Verified: 2026-11-07T10:10:00Z_
_Verifier: Claude (gsd-verifier)_
