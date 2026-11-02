---
phase: 83-autonomous-security-response
plan: 20
subsystem: testing
tags: [cargo, windows-gnu, pytest, vitest, validation, release-gate]
requires:
  - phase: 83-autonomous-security-response
    provides: plans 83-01 to 83-19 (backend gate and sweep, Rust agent actions, Activity screen cards)
provides:
  - Agent manifest version 2.1.16 (Cargo.toml and the omni-agent entry of Cargo.lock) committed
  - Windows compile result for the whole phase (cargo check --lib for x86_64-pc-windows-gnu, exit 0)
  - One combined run of every automated gate (backend, Rust, frontend, build) with its result
  - 83-VALIDATION.md with real task ids, a 45-row task index and the results
  - The ordered Live list for the user (last section)
affects: [phase 83 verification, /gsd-verify-work 83, agent 2.1.16 publish]
actuals:
  tokens: 6500
  tasks: 2
  commits: 2
plan_head_before: 86775b0722c7c9f90df10ce8a557e5fc48ba1a45
plan_head_after: 08c4683d2fe3936c734e9dcfd42327a046e3229c
tech-stack:
  added: []
  patterns: []
key-files:
  created: []
  modified:
    - agent-install/omni-agent-rs/Cargo.toml
    - agent-install/omni-agent-rs/Cargo.lock
    - .planning/phases/83-autonomous-security-response/83-VALIDATION.md
key-decisions:
  - "The version commit holds only the two version lines; the user's flate2 hunks stay uncommitted"
  - "RESP-10 is not ticked: publishing the agent and the Windows hosts are the user's, so the requirement is not finished by this plan"
requirements-completed: []
status: complete
---

# Phase 83 Plan 20: Release gate Summary

Agent version 2.1.16 is committed, the Windows build of the phase's `cfg(windows)` code compiles (`cargo check` exit 0), every automated gate passes together except the one known catalogue ledger test, and the live-only checks are one ordered list for the user.

## What ran, and what it returned

**Windows compile (the plan's Task 1 check).** Command, from the project root, foreground, one try:

`PATH=$HOME/.cargo/bin:$PATH CARGO_BUILD_JOBS=1 CARGO_TARGET_DIR=$PWD/agent-install/omni-agent-rs/target/nodebug CARGO_PROFILE_DEV_DEBUG=0 timeout 580 cargo check --offline --manifest-path agent-install/omni-agent-rs/Cargo.toml --lib --target x86_64-pc-windows-gnu`

Result: exit 0, `Finished dev profile in 1m 07s` (the finished crates from the dead run were kept, so no 124 retry was needed). No `error` lines. 11 warnings, all in files this phase did not write (`system_patching.rs`, `fim.rs`, `fim_baseline.rs`, `heartbeat.rs`); none in the Phase 83 files. Windows compiled, from that command. Limits: `--lib` only (the binary and the tests are not compiled for Windows), and the check ran on the working tree, which includes the user's uncommitted flate2 hunk; the committed Cargo.toml/Cargo.lock pair alone was not checked separately. Nothing in the check ran Windows code. The live backend's startup build (`cargo build --release --target x86_64-pc-windows-gnu`, 04:07-04:14, 32108 KB) agrees.

**Rust, Linux (same recipe, no-debug target dir).** `--lib response_`: 80 passed. Whole `--lib`: 400 passed, 1 ignored. `--test quarantine_dispatch_test`: 6 passed. `--test remediation_dispatch_test`: 5 passed. The two integration targets are not in the plan's verify list; I ran them because 83-02 and 83-09 name them.

**Backend subset, private mongod 27998, one background run, 6 min 58 s.** The plan's list (40 files, all exist; none had to be removed) plus `test_autonomous_ops_two_signal.py`, the one `test_autonomous_ops_*.py` file the list omitted. Result: 1072 passed, 1 failed, 0 skipped. The failure is `test_catalogue_route_parity.py::test_ledger_ratchets`, the expected exception to "non-zero exit". Its list holds exactly the 9 known names (audit_program, compliance_evidence, compliance_report, compliance_reports, export_report, reporting, route_aliases, scheduled_reports, soa); no new name. It predates the phase and was not fixed. Also run separately because 83-11-T2 names them and the 83-20 list does not: `test_remediation_playbook.py`, `test_autonomous_remediation_loop.py`, `test_rotate_key_wiring.py`, `test_ueba_remediation_trigger.py`: 60 passed.

**Frontend.** `npx vitest run src/__tests__`: 76 files, 938 tests passed, exit 0. `npm run build`: exit 0, "built in 5.34s", no `error` in the output; output in git-ignored `dist-new` (entry `index-VUPN-kZs.js`, replacing the earlier Phase 81 dist-new). Nothing went to /var/www.

**Not run:** the full backend suite (A-83-FULLSUITE, the user's step, alone, compared by name with the 2026-10-31 baseline).

## Task Commits

| Task | Commit | What |
|------|--------|------|
| 1 | `920b9c214` | `chore(83-20): agent version 2.1.16 for the whole of phase 83` (2 lines: one in Cargo.toml, one in Cargo.lock) |
| 2 | `08c4683d2` | `docs(83-20): fill the validation map with real task ids, commands and the 2026-11-02 results` |

The version commit contains only the two version lines. `git diff` after the commit still shows the user's flate2 lines in Cargo.toml and the flate2 dependency line in Cargo.lock as uncommitted. `_LATEST_AGENT_VERSION` was not touched. The commit message of Task 2 says "all 40 tasks"; the index has 45 rows (43 plan tasks plus the 2 of this plan). That is the only error in it and it was not amended.

## Deviations from Plan

- **Version staging (process, not content).** The plan says "a filtered patch and `git apply --cached`". I built the two staged blobs from `git show HEAD:<file>` with only the version line changed and put them in the index with `git update-index --cacheinfo`; the result is the same two-line commit. The working-tree files were never rewritten.
- **Verify commands.** The plan's cargo commands omit the no-debug variables; I used the run-notes recipe, as instructed. The backend list gained `test_autonomous_ops_two_signal.py`.
- **Two extra runs** (the two Rust integration targets, and the four 83-11 backend files) so that no status in the task index rests on a result I did not have.
- **VALIDATION.md.** Besides the task map: the requirement-level rows keep their text and gain task ids; a 45-row task index was added; two Wave 0 boxes were ticked (the recorder, which lives in `capabilities/privileged.rs` and not in `remediation_actions.rs`, and `autonomy_support.py`); the hermetic response_state fixture with an injectable clock was not checked and stays unticked; four rows were added to Manual-Only. `nyquist_compliant` is false, `status` is draft, sign-off boxes untouched.

No Rule 1 to 3 fixes were needed: the Windows check reported nothing to fix.

## Requirements

RESP-10 is NOT ticked. Plan 83-20 is the last plan that lists it, but the requirement is the agent shipping the actions, and publishing the agent, the Windows behaviour and the dormancy on real hosts are the live list below. The automated half is green (`test_autonomous_ops_dormancy.py`, the Rust response tests, the Windows compile). The orchestrator decides at the phase gate. REQUIREMENTS.md was not touched. Other IDs unticked at the start of this plan (RESP-02, -03, -04, -06, -07, -08) are the orchestrator's.

## Read, and not read

Read: the run notes, the plan, 83-VALIDATION.md, STATE.md frontmatter and lines 745 to the end, `config.json`, CLAUDE.md. Of each 83-NN-SUMMARY.md I read the heading list, and the sections named below; the task map comes from each plan's task names, requirements and `<automated>` lines (grep), not from a full reading. Not read: 83-CONTEXT.md, 83-UI-SPEC.md, 83-RESEARCH.md, 83-PATTERNS.md, the execute-plan workflow and the reference files (their rules were applied from the dispatch prompt). This plan writes no user-visible sentence.

## Known Stubs

None created by this plan.

## Self-Check: PASSED

`920b9c214` and `08c4683d2` are ancestors of HEAD; `83-20-SUMMARY.md` and the filled `83-VALIDATION.md` exist; `grep -c 83-TBD` on the validation file prints 0; `grep -m1 ^version Cargo.toml` prints 2.1.16 and the omni-agent entry of Cargo.lock reads 2.1.16 in the working tree and in HEAD.

## Live list

For the user, in the order to do them. Everything the plan could prove on this VM is above; this is what only a person or a real host can prove. Each item is a human check.

**Read and decide before anything is published**

1. **Read the sentences the UI-SPEC does not word.** Each plan's SUMMARY lists the ones it wrote: 83-03 ("Keys in response_messages.py"), 83-04 ("User-visible sentences not in the UI-SPEC"), 83-05 and 83-06 ("Wording"), 83-07, 83-08, 83-09, 83-10, 83-11, 83-12, 83-13, 83-14, 83-16, 83-18 and 83-19 (each has a "User-visible sentences" or "Sentences" section). Examples from 83-19: step state `Not run`, `Confirming...`, and the 409 texts; from 83-18: the chain-failure fragments such as "the file is still in use". 83-18 also notes a Suggest-level block or quarantine line has no What-happens text, and 83-16's kill-only notice reads as an instruction (check it on a card).
2. **Confirm A-83-LEVEL-SUGGEST.** `incident_views.APPROVABLE_SUGGESTION_CODES` decides which rows at level Suggest appear as approvable lines; one-source suggestions never appear. This filter is already live in the backend; the cards are not visible until the UI is published. Change it, or say it stands.
3. **Before publishing 2.1.16, accept the two behaviour changes:** a `block_ip` with no `ttl_seconds` lasts 24 hours (83-02), and the agent refuses every non-global address, RFC 1918 included, the platform host, the gateway, DNS servers and networks wider than /8 (83-04). A refusal is final and is not a failure the breaker counts.

**Publish**

4. **Publish the UI.** The backend does not need a restart for this phase: it runs from this checkout and restarted at 04:07:14 on 2026-11-02, so all Phase 82 and Phase 83 backend code is already live (migration 028 applied at 04:07:43; 025 to 027 on 2026-10-30). No backend file has been committed since 04:07: the last commit touching `backend/` is `eb8c4b8ae` at 03:43:56 (and `ff514e34b`, `incident_views.py`, the same minute); the only commit after 04:07 is the version commit, which touches no backend file. So: publish `dist-new` (entry `index-VUPN-kZs.js`, built today by `npm run build` from the working tree, which includes the two App.tsx hunks the user keeps uncommitted), and restart the backend only if something backend is committed after this. The 83-06 Swarm dashboard check (amber "not sent" message, narrow-window wrapping) waits on this publish.
5. **Publish agent 2.1.16 and bump `_LATEST_AGENT_VERSION`** (still 2.1.14), then confirm the `meta.response_actions` tokens on a test host. Three facts to hold in mind: (a) startup already rebuilt `target/x86_64-pc-windows-gnu/release/omni-agent.exe` from the working tree at 04:14:08, version 2.1.16, including the user's uncommitted hunks, so new tenant installers ship that binary now; the log shows no download yet; (b) that binary carries Phase 83 `cfg(windows)` code that compiles but has never run (item 12); (c) existing hosts stay on 2.1.14, because the update channel serves the versioned static file and `_LATEST_AGENT_VERSION` has not moved.
6. **Tenants are in shadow, and automatic block and quarantine will be uncommon until real signals exist.** At the check made at about 04:12 to 04:20: 4 of 4 tenants have `shadow: true`, no autonomy rows exist and no instructions have been created since boot. Expect Simulation rows only until a Super Admin lifts a tenant. When one does, automatic block and quarantine still stay rare, because they need two different origins, nothing schedules agent scans (A-83-SCAN), and no writer feeds the on-host origin today (A-83-ONHOST, D-23). That is expected, not a fault.
7. **Set `ABUSE_CH_AUTH_KEY`, restart the backend, and count `edr_ioc` by `source_feeds`** (D-26, A-83-A2). Without the key the public-feed origin has no rows.

**Real hosts**

8. **Firewall round trip**, both directions, IPv4 and IPv6, on real Linux (chain at position 1 of INPUT and OUTPUT beside ufw or firewalld, A-83-A12) and on EILT0197 with Defender on (`dir=out`, A-83-A4). Use a routable address such as 45.33.32.156.
9. **A 1-hour block expiring while the host is offline**, across an agent restart and a reboot; the rule must be gone at expiry. The backend infers "ended" from `blockedUntil` and changes nothing.
10. **Quarantine and restore of a running harmless test binary on Windows.** Confirm which of "still running" or "locked" appears and the kill-only card; approve the kill card and confirm in Task Manager that the process really ended before the row reads Done; note which path it reported after the move; check the quarantine directory's ACL (A-83-A10).
11. **Isolation on a throwaway host** with a shortened revert first: management connection open, automatic revert, Confirm isolation, a reboot while isolated, and a Group Policy firewall (A-83-A5, A-83-ISOLATION-TEST). Not covered by any test: a platform given by name is resolved once at apply (83-12), and Linux hosts without `ip6tables` cannot be isolated.
12. **Windows behaviour written from documentation and never captured from a host:** `sc` output (including that an administrator's `sc stop` leaves `WIN32_EXIT_CODE : 0`, A-83-A6), `netsh` output, the effective-policy read behind `not_effective`, `route print`, and the codes 5, 225 and 4551. Capture each on EILT0197 and compare with the parsers' fixtures; non-English Windows output is expected to fall back to defaults. Also this binary is the one new installers already download (item 5).
13. **Crash and stop a test service on both operating systems:** only the crash may restart; an administrator stop must not.
14. **Check Defender history** for `netsh`, `sc` and `shutdown` spawned by the agent (A1).
15. **Browser pass** of the cards, Undo and settings, in light and dark at 640, 1024 and 1280 px, including no sideways scroll at 1280 px.

**Known defects and limits left open**

16. **Over-budget restart card.** It stays open up to 24 hours after the service recovers, and a late approval restarts a healthy service (83-17, 83-18, 83-19). Nothing withdraws it. The card also shows no Result sentence after approval because it has no `attempt`.
17. **A-83-PATCHED.** `remediation_service.py` still marks a vulnerability Patched right after a worker task that now answers `not_sent` (83-06). A separate defect, not fixed here.
18. **Full backend suite**, alone, before `/gsd-verify-work 83` (A-83-FULLSUITE): compare failures by test name with the 2026-10-31 baseline (5,135 passed, 5 known failures, 47 skipped). Expect `test_catalogue_route_parity.py::test_ledger_ratchets` to fail with the 9 names listed above; whether it was among the 5 known failures was not checked.
