---
phase: "83"
slug: "autonomous-security-response"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-31"
---

# Phase 83 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Backend: pytest + pytest-asyncio (`asyncio_mode = auto`). Agent: `cargo test --offline`. Frontend: vitest 5 + @testing-library/react (jsdom) |
| **Config file** | `pytest.ini`, `agent-install/omni-agent-rs/Cargo.toml`, `vitest` config in `package.json` scripts |
| **Quick run command** | Backend: `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_sweep.py -x -q -p no:cacheprovider`. Agent: `cd agent-install/omni-agent-rs && PATH=$HOME/.cargo/bin:$PATH CARGO_BUILD_JOBS=1 cargo test --offline <name>`. Frontend: `npx vitest run src/__tests__/autonomousOpsResponse.test.tsx` |
| **Full suite command** | `npx vitest run src/__tests__`, `npm run build`, and `TICKET_ATTACHMENT_DIR=$(mktemp -d) FILE_SHARE_DIR=$(mktemp -d) backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` |
| **Estimated runtime** | Quick run under 60 s. Full backend run 24 to 34 min, alone on the VM |

**Database rule:** the test fixtures default to the LIVE mongod on 27017. Every database test runs against a private mongod with `MONGO_TEST_URL`, `MONGODB_URL` and `MONGO_URI` all set:

`GLIBC_TUNABLES=glibc.pthread.rseq=1 /usr/bin/mongod --dbpath <tmp> --port 27998 --bind_ip 127.0.0.1 --wiredTigerCacheSizeGB 0.25 --fork --logpath <tmp>/mongod.log --pidfilepath <tmp>/mongod.pid`

**VM rule:** 2 vCPUs and 8 GB, shared with the live backend and MongoDB. Never run the full backend suite beside a subagent that runs tests. Use `CARGO_BUILD_JOBS=1` and one targeted `cargo test` at a time.

---

## Sampling Rate

- **After every task commit:** Run the touched test file plus `backend/tests/test_autonomous_ops_structural.py` and `backend/tests/test_autonomous_ops_copy.py`
- **After every plan wave:** Run all `backend/tests/test_autonomous_ops_*.py` plus `test_catalogue_slice_autonomous_ops.py`, `test_catalogue_route_parity.py` and `test_route_auth_baseline.py` on the private mongod, `npx vitest run src/__tests__`, and the Rust tests for touched modules
- **Before `/gsd-verify-work`:** Full suite run alone; compare failures by test name with the 2026-10-31 baseline in `82-VALIDATION.md` (5,135 passed, 5 known failures, 47 skipped)
- **Max feedback latency:** 60 seconds for a quick run

---

## Per-Task Verification Map

Requirement-level map seeded from 83-RESEARCH.md. Task ids are `83-<plan>-T<task>`; the task index below lists every task with its own command. Results are from the 83-20 run on 2026-11-02 (private mongod on 27998; Rust with `CARGO_TARGET_DIR=.../target/nodebug`): backend subset 1,072 passed and 1 failed (`test_catalogue_route_parity.py::test_ledger_ratchets`, the 9 known unguarded-route ledger names, predating the phase), 0 skipped; four more files 83-11 names, 60 passed; Rust `--lib` 400 passed, `--test quarantine_dispatch_test` 6, `--test remediation_dispatch_test` 5; vitest 76 files / 938 tests passed; `npm run build` ok. A green mark means the automated command passed; the live-only items stay in Manual-Only Verifications.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 83-01-T1..T3, 83-05-T1..T3, 83-06-T1..T2, 83-11-T1..T3, 83-15-T1..T2 | 83-01, 83-05, 83-06, 83-11, 83-15 | 1-6 | RESP-01 | R7 | The sweep turns candidates into gate decisions, reads global feed rows only through the raw handle, and resolves hostname to one `agents.id`; vulnerabilities and file changes become suggestions; a file finding routes to quarantine, never kill | unit + real-Mongo | `pytest backend/tests/test_autonomous_ops_sweep.py -x` | ✅ exists | ✅ green 2026-11-02 |
| 83-01-T1..T3, 83-02-T1..T2, 83-03-T1..T2, 83-04-T1..T2, 83-08-T1..T3, 83-10-T1..T2 | 83-01, 83-02, 83-03, 83-04, 83-08, 83-10 | 1-5 | RESP-02 | R1, R4, R6 | TTL travels in the instruction; an idempotent claim, expiry while offline and across restart, refcounted undo that removes only its own claim; a CIDR needs approval; the agent refuses non-global addresses, the platform, gateway and DNS | Rust unit with a command recorder; backend params test | `cargo test --offline response_state`; `pytest backend/tests/test_autonomous_ops_block_contract.py -x` | ✅ exists | ✅ green 2026-11-02 |
| 83-03-T1..T2, 83-09-T1..T2, 83-10-T1..T2, 83-11-T1..T3, 83-16-T1..T2 | 83-03, 83-09, 83-10, 83-11, 83-16 | 2-6 | RESP-03 | R3, R5, R10 | Moved, never deleted; hash-bound; manifest; restore only to the manifest path; refuses a symlink, a directory, its own directories and an existing destination; a kill reaches the process after its file moved, leaves a reused PID alone, and never reports a live process as gone | Rust integration with tempdirs and one real child process; Rust unit on scripted process lists | `cargo test --offline --test quarantine_dispatch_test`; `cargo test --offline --lib process_kill` | ✅ exists | ✅ green 2026-11-02 |
| 83-07-T1..T2, 83-13-T1..T2, 83-14-T1..T2, 83-17-T1..T2 | 83-07, 83-13, 83-14, 83-17 | 4-7 | RESP-04 | R3 | Listed services only; an admin stop is not a failure; budget of 3 per service per host per rolling hour, then one card; argv-only spawn; server regex matches the agent's rule | backend + Rust unit | `pytest backend/tests/test_autonomous_ops_restart_budget.py -x`; `cargo test --offline service_watch` | ✅ exists | ✅ green 2026-11-02 |
| 83-09-T1..T2, 83-11-T1..T3, 83-12-T1..T2, 83-16-T1..T2, 83-18-T1..T2, 83-19-T1..T2 | 83-09, 83-11, 83-12, 83-16, 83-18, 83-19 | 4-9 | RESP-05 | R4 | Management allow rules applied and verified before any block; self-test failure reverts; agent-held 4-hour revert with no network; confirm cancels the revert; a confirmed finding adds at most one isolate line per incident | Rust unit with a command recorder; route test | `cargo test --offline isolation`; `pytest backend/tests/test_autonomous_ops_confirm_isolation.py -x` | ✅ exists | ✅ green 2026-11-02 |
| 83-01-T1..T3, 83-02-T1..T2, 83-09-T1..T2, 83-16-T1..T2 | 83-01, 83-02, 83-09, 83-16 | 1-6 | RESP-06 | — | `verify.ok` true gives `verified`; false gives `failed` with no unblock dispatched; the original finding is never re-read (a still-Malicious fixture plus an AST check on the verify path, from 83-01); a failed undo never reads as undone (from 83-16); a kill row is `verified` only when the agent reports the process gone (from 83-16) | real-Mongo + structural | `pytest backend/tests/test_autonomous_ops_block_contract.py backend/tests/test_autonomous_ops_verify.py backend/tests/test_autonomous_ops_followups.py -x` | ✅ exists | ✅ green 2026-11-02 |
| 83-05-T1..T3 | 83-05 | 3 | RESP-07 | — | Ten consecutive ticks create at most one row, including for recorded refusals; no redo for 24 h after undo; a re-block after expiry needs evidence newer than the old block | real-Mongo + frozen clock | `pytest backend/tests/test_autonomous_ops_sweep_dedupe.py -x` | ✅ exists | ✅ green 2026-11-02 |
| 83-03-T1..T2, 83-05-T1..T3, 83-07-T1..T2, 83-13-T1..T2 | 83-03, 83-05, 83-07, 83-13 | 2-6 | RESP-08 | R1, R2, R8 | Two distinct origins by default; two entries of one origin never count; deception and manual IOCs never count; 24-hour promotion; the switch is honoured and every change is recorded; 3 automatic actions per host per hour | unit + real-Mongo | `pytest backend/tests/test_autonomous_ops_origins.py -x` | ✅ exists | ✅ green 2026-11-02 |
| 83-11-T1..T3, 83-18-T1..T2, 83-19-T1..T2 | 83-11, 83-18, 83-19 | 5-9 | RESP-09 | — | One-hour quiet gap, restart-safe, one card for a burst | real-Mongo | `pytest backend/tests/test_autonomous_ops_incidents.py -x` | ✅ exists | ✅ green 2026-11-02 |
| 83-02-T1..T2, 83-08-T1..T3, 83-09-T1..T2, 83-12-T1..T2, 83-14-T1..T2 | 83-02, 83-08, 83-09, 83-12, 83-14 | 2-6 | RESP-10 | R6 | Dormant without the tick, without the token, while offline and on an old agent, with no breaker effect; hash mismatch and no-ops do not count toward the breaker | real-Mongo | `pytest backend/tests/test_autonomous_ops_dormancy.py -x` | ✅ exists | ✅ green 2026-11-02 |
| 83-06-T1..T2 | 83-06 | 3 | RESP-11 | — | No writer to `db.instructions` remains; the routes answer not-sent; `agents.isolated` is unchanged; automatic XDR containment only suggests | structural + route | `pytest backend/tests/test_autonomous_ops_structural.py backend/tests/test_swarm_soar_fence.py -x` | ✅ exists | ✅ green 2026-11-02 |
| 83-01-T1..T3, 83-03-T1..T2, 83-07-T1..T2, 83-10-T1..T2, 83-13-T1..T2, 83-18-T1..T2, 83-19-T1..T2 | 83-01, 83-03, 83-07, 83-10, 83-13, 83-18, 83-19 | 1-9 | ACTV-02 | R8, R11 | Approve, deny, undo and confirm need the control permission and an interactive session; the settings panel needs the manage permission; bulk is Super Admin only; strings render as text | vitest + route | `npx vitest run src/__tests__/autonomousOpsResponse.test.tsx`; `pytest backend/tests/test_autonomous_ops_response_endpoints.py -x` | ✅ exists | ✅ green 2026-11-02 |
| 83-03-T1..T2, 83-06-T1..T2, 83-07-T1..T2, 83-10-T1..T2, 83-13-T1..T2, 83-18-T1..T2, 83-19-T1..T2 | 83-03, 83-06, 83-07, 83-10, 83-13, 83-18, 83-19 | 2-9 | Copy (ACTV-08) | — | No banned term in any new file | existing | `pytest backend/tests/test_autonomous_ops_copy.py -x`; `npx vitest run src/__tests__/autonomousOpsCopy.test.ts` | ✅ exists | ✅ green 2026-11-02 |
| 83-07-T1..T2, 83-18-T1..T2 | 83-07, 83-18 | 4-8 | Catalogue | — | New routes are mounted, guarded and in parity | existing | `pytest backend/tests/test_catalogue_slice_autonomous_ops.py backend/tests/test_catalogue_route_parity.py -x` | ✅ exists | ⚠️ green except `test_ledger_ratchets` (the 9 known names, not Phase 83) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Task index

| Task ID | Wave | Requirement | What the task proves | Automated command (short form) | Status |
|---------|------|-------------|----------------------|--------------------------------|--------|
| 83-01-T1 | 1 | RESP-01, RESP-02, RESP-06 | Tracer: one IP flagged by two origins on one host becomes one gated block; the agent's verify result marks it verified | `pytest test_autonomous_ops_block_contract _sweep _reconciler _structural` | ✅ green 2026-11-02 |
| 83-01-T2 | 1 | RESP-01, RESP-02 | The sweep runs every minute with one runner at a time | `pytest test_autonomous_ops_sweep _reconciler _structural` | ✅ green 2026-11-02 |
| 83-01-T3 | 1 | RESP-02, RESP-06 | Undo removes only this block's claim; a second tick repeats nothing | `pytest test_autonomous_ops_block_contract _approvals _gate _gate_order _dispatch_binding _structural` | ✅ green 2026-11-02 |
| 83-02-T1 | 2 | RESP-02, RESP-06 | A block with a time limit on the agent: seam, state file, rule plans, claims, verify | `cargo test --lib firewall; --lib response_state` | ✅ green 2026-11-02 |
| 83-02-T2 | 2 | RESP-06, RESP-10 | Real dispatch answers with the contract's result bodies; heartbeat reports support | `cargo test --lib response_; --test remediation_dispatch_test` | ✅ green 2026-11-02 |
| 83-03-T1 | 2 | ACTV-02 (copy) | Every server sentence in one module on the copy gate | `pytest test_autonomous_ops_copy; vitest autonomousOpsCopy.test.ts` | ✅ green 2026-11-02 |
| 83-03-T2 | 2 | RESP-02, RESP-03, RESP-08 | Rows say what happened and which can be undone | `pytest test_autonomous_ops_response_rows _endpoints _endpoints_writes _copy` | ✅ green 2026-11-02 |
| 83-04-T1 | 3 | RESP-02 | Blocks end on their own, offline and across restarts | `cargo test --lib response_state` | ✅ green 2026-11-02 |
| 83-04-T2 | 3 | RESP-02 | The agent refuses addresses that would cut the host off, blocks an approved range, names a security-product refusal | `cargo test --lib net_safety; --lib response_` | ✅ green 2026-11-02 |
| 83-05-T1 | 3 | RESP-01, RESP-08 | Every origin read honestly; feeds keep their names | `pytest test_autonomous_ops_origins test_threat_feed_sync_origins` | ✅ green 2026-11-02 |
| 83-05-T2 | 3 | RESP-01, RESP-08 | One origin suggests, a second within 24 h acts, the tenant switch is honoured | `pytest test_autonomous_ops_origins _sweep _block_contract` | ✅ green 2026-11-02 |
| 83-05-T3 | 3 | RESP-07, RESP-08 | Nothing repeats: decision memory, undo window, per-host cap | `pytest test_autonomous_ops_sweep_dedupe _gate_order _gate` | ✅ green 2026-11-02 |
| 83-06-T1 | 3 | RESP-11 | Swarm, SOAR and worker tasks send nothing and say so | `pytest test_swarm_soar_fence test_autonomous_ops_structural _copy; vitest SwarmDashboardNotSent, autonomousOpsCopy` | ✅ green 2026-11-02 |
| 83-06-T2 | 3 | RESP-11, RESP-01 | Automatic XDR only suggests; the new actions reach an agent only through the gate | `pytest test_autonomous_ops_xdr_fence test_swarm_soar_fence test_autonomous_ops_stop _structural` | ✅ green 2026-11-02 |
| 83-07-T1 | 4 | RESP-04, RESP-08, ACTV-02 | A tenant admin reads and saves the three settings; every change is recorded | `pytest test_autonomous_ops_response_endpoints test_catalogue_slice_autonomous_ops test_catalogue_route_parity test_route_auth_baseline test_autonomous_ops_copy` | ✅ green 2026-11-02 |
| 83-07-T2 | 4 | RESP-08, ACTV-02 | A Super Admin sees the spread and applies a change to every organization | `pytest test_autonomous_ops_response_endpoints test_catalogue_slice_autonomous_ops test_route_auth_baseline test_autonomous_ops_copy` | ✅ green 2026-11-02 |
| 83-08-T1 | 4 | RESP-10 | A host that cannot carry an action stays dormant, in the sweep, the gate and at approval | `pytest test_autonomous_ops_dormancy _gate _gate_order _approvals` | ✅ green 2026-11-02 |
| 83-08-T2 | 4 | RESP-10 | The breaker counts real failures, each with its own name | `pytest test_autonomous_ops_breaker _reconciler _dormancy` | ✅ green 2026-11-02 |
| 83-08-T3 | 4 | RESP-02 | Blocking a range always waits for a person | `pytest test_autonomous_ops_range_block _registry _protected _gate _dispatch_binding` | ✅ green 2026-11-02 |
| 83-09-T1 | 4 | RESP-03 | Quarantine moves a file and never deletes it; restore only to where it came from | `cargo test --test quarantine_dispatch_test; --lib quarantine` | ✅ green 2026-11-02 |
| 83-09-T2 | 4 | RESP-03, RESP-05, RESP-06, RESP-10 | A kill reaches only the approved process and says it ended only when it did | `cargo test --lib process_kill; --lib response_; --test quarantine_dispatch_test` | ✅ green 2026-11-02 |
| 83-10-T1 | 5 | ACTV-02, RESP-02, RESP-03 | Undo on Done rows; Review link on Pending rows | `vitest autonomousOpsResponse, AutonomousOpsActivity, autonomousOpsCopy` | ✅ green 2026-11-02 |
| 83-10-T2 | 5 | ACTV-02, RESP-03 | Suggestions stay readable in volume and link to where the work is done | `vitest autonomousOpsResponse, AutonomousOpsActivity; npm run build` | ✅ green 2026-11-02 |
| 83-11-T1 | 5 | RESP-09 | A burst of alerts on one host is one incident | `pytest test_autonomous_ops_incidents` | ✅ green 2026-11-02 |
| 83-11-T2 | 5 | RESP-01, RESP-03 | A confirmed malicious file is quarantined; a protected system file waits for a person | `pytest test_autonomous_ops_quarantine_decisions test_remediation_playbook test_autonomous_remediation_loop test_autonomous_ops_structural _remediation_truth test_rotate_key_wiring test_ueba_remediation_trigger` | ✅ green 2026-11-02 |
| 83-11-T3 | 5 | RESP-05, RESP-09 | A confirmed finding proposes isolation once per incident | `pytest test_autonomous_ops_incidents _sweep _sweep_dedupe` | ✅ green 2026-11-02 |
| 83-12-T1 | 5 | RESP-05, RESP-10 | Isolation opens the management path first, tests it, backs out on any failure | `cargo test --lib isolation` | ✅ green 2026-11-02 |
| 83-12-T2 | 5 | RESP-05, RESP-10 | The host comes back on its own unless a person confirms | `cargo test --lib isolation; --lib response_` | ✅ green 2026-11-02 |
| 83-13-T1 | 6 | RESP-04, RESP-08 | Settings panel: a tenant admin reads, changes and saves | `vitest autonomousOpsSettings, AutonomousOpsActivity, autonomousOpsCopy` | ✅ green 2026-11-02 |
| 83-13-T2 | 6 | RESP-08 | A Super Admin applies a setting to every organization | `vitest autonomousOpsSettings; npm run build` | ✅ green 2026-11-02 |
| 83-14-T1 | 6 | RESP-04, RESP-10 | A failed listed service is noticed, reported and restarted; a stopped one is left alone | `cargo test --lib service_watch` | ✅ green 2026-11-02 |
| 83-14-T2 | 6 | RESP-04, RESP-10 | A reboot can be scheduled; the agent's contract results are complete | `cargo test --lib response_; --lib host_power` | ✅ green 2026-11-02 |
| 83-15-T1 | 6 | RESP-01 | Hundreds of vulnerabilities on a host are one row | `pytest test_autonomous_ops_suggestions _sweep` | ✅ green 2026-11-02 |
| 83-15-T2 | 6 | RESP-01 | File changes on a host are one suggestion; a malicious file leaves it | `pytest test_autonomous_ops_suggestions _response_rows` | ✅ green 2026-11-02 |
| 83-16-T1 | 6 | RESP-03, RESP-05, RESP-06 | A running file gets one kill card; the retry stops after one try | `pytest test_autonomous_ops_followups _reconciler _block_contract` | ✅ green 2026-11-02 |
| 83-16-T2 | 6 | RESP-06 | An undo that failed never reads as undone | `pytest test_autonomous_ops_verify _reconciler _breaker` | ✅ green 2026-11-02 |
| 83-17-T1 | 7 | RESP-04 | A failed listed service restarts within its budget, then asks a person | `pytest test_autonomous_ops_restart_budget _sweep _sweep_dedupe` | ✅ green 2026-11-02 |
| 83-17-T2 | 7 | RESP-04 | The watched list reaches the agent; failure data respects the capability tick | `pytest test_autonomous_ops_restart_budget` | ✅ green 2026-11-02 |
| 83-18-T1 | 8 | ACTV-02, RESP-09 | One list of cards, grouped by incident | `pytest test_autonomous_ops_incident_route test_catalogue_slice_autonomous_ops test_route_auth_baseline test_autonomous_ops_copy` | ✅ green 2026-11-02 |
| 83-18-T2 | 8 | RESP-05 | Confirming an isolation reaches the agent; an automatic revert is noticed | `pytest test_autonomous_ops_confirm_isolation _incident_route _restart_budget test_route_auth_baseline` | ✅ green 2026-11-02 |
| 83-19-T1 | 9 | ACTV-02, RESP-09 | Needs your decision: cards with Approve and Deny on each action | `vitest autonomousOpsDecisions, AutonomousOpsActivity, autonomousOpsCopy` | ✅ green 2026-11-02 |
| 83-19-T2 | 9 | ACTV-02, RESP-05 | Confirm isolation, the kill cards and the deadlines | `vitest src/__tests__ (all); npm run build` | ✅ green 2026-11-02 |
| 83-20-T1 | 10 | RESP-10 | One agent version 2.1.16; cfg(windows) code compiles | `cargo check --lib --target x86_64-pc-windows-gnu (exit 0, 11 warnings, none in phase files); cargo test --lib response_ (80 passed)` | ✅ green 2026-11-02 |
| 83-20-T2 | 10 | all | Every automated gate once together | `this table's results line above` | ✅ green 2026-11-02 |

Backend commands drop the `backend/tests/` prefix after the first file name and the `.py` suffix; a name beginning `_` continues the `test_autonomous_ops` prefix. Every one ran in the 83-20 backend command or, for 83-11-T2, in the separate four-file run (60 passed). Not one of these status marks covers a live behaviour.


---

## Wave 0 Requirements

- [x] Every test file marked ❌ W0 above: all exist and pass. Plans 83-02, 83-07 and 83-09 wrote tests after the code, and their SUMMARYs say so; 83-03's RED evidence is weak
- [x] A thread-local recorder returning scripted results: it exists as `RECORDER` in `agent-install/omni-agent-rs/src/capabilities/privileged.rs` (not in `remediation_actions.rs` as first written); checked by 83-20
- [x] A hermetic Rust fixture for `response_state.json` with an injectable clock: `Store::at`, `use_temp_store` and the `now` parameter of `expire_due`, `reapply_live` and `start_up` in `response_state.rs`
- [x] `backend/tests/autonomy_support.py` — seeding helpers for global `edr_ioc` rows, `fim_events` and agents with `meta.response_actions` and a hostname that differs from the id (file exists; checked by 83-20)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Publish and roll out agent 2.1.16 | RESP-10 | User's step; publishing and `_LATEST_AGENT_VERSION` are not automated | Publish, bump the version, confirm `meta.response_actions` tokens appear for a test host |
| Firewall round trip, both directions, IPv4 and IPv6 | RESP-02 | Needs root and a real firewall | Block and unblock on real Linux and on Windows EILT0197 with Defender on |
| A block expiring while offline, across an agent restart and a reboot | RESP-02 | Needs a real host and network | Set a 1-hour block, take the host offline, confirm the rule is gone at expiry |
| Quarantine of a running file, approved kill, and restore, on Windows | RESP-03, RESP-06, D-27 | Assumed OS behaviour; Defender in the loop; the path a renamed process reports is read from its own memory on Windows | Run a harmless test binary, quarantine it, confirm `still_running` and the kill-only card, approve it, confirm the process really ended before the row reads Done, record the path it reported after the move, restore |
| Isolation with the management connection open, automatic revert, reboot while isolated, Group Policy firewall | RESP-05 | Risk of losing a host; needs a real network | Use a shortened revert on a test host first, then the full 4 hours; confirm the platform stays reachable |
| Real service restart, and admin stop versus crash | RESP-04 | OS exit-code semantics are assumed | Crash and stop a test service on Linux and Windows; only the crash may restart |
| Defender behaviour for `netsh`, `sc` and `shutdown` | RESP-02, RESP-04, RESP-10 | No documentation either way | Run each action on EILT0197 and check Defender history |
| Public feed signals | D-26 | Needs the user's abuse.ch key and a live database read | Set `ABUSE_CH_AUTH_KEY`, restart, count `edr_ioc` by `source_feeds` |
| Browser pass of the cards, Undo and settings panel | ACTV-02 | Needs a published UI | Light and dark at 640, 1024 and 1280 px, including the 1280px no-sideways-scroll check |
| Windows output written from documentation, never captured from a host: `sc`, `netsh`, the effective-policy read, `route print`, error codes 5, 225 and 4551 | RESP-02, RESP-03, RESP-04, RESP-05 | Every `cfg(windows)` branch is compiled (83-20) but not run | Capture each on EILT0197 and compare with the parsers' test fixtures |
| Over-budget restart card after the service recovers | RESP-04 | A card stays open up to 24 hours; a late approval restarts a healthy service | Let a service recover, look at the card, decide whether the restart stage should withdraw it |
| A block with no `ttl_seconds` lasts 24 hours; private addresses are refused | RESP-02 | Behaviour change to publish knowingly (83-02, 83-04) | Read both in the settings text before publishing 2.1.16 |
| Level Suggest rows appear as approvable lines (A-83-LEVEL-SUGGEST) | ACTV-02 | A product decision, awaits the user | Decide whether `incident_views.APPROVABLE_SUGGESTION_CODES` stays as is |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s for a quick run
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** automated coverage audited 2026-11-02: every requirement behaviour has a named test that passed in the orchestrator's own gate run on a67453a8e (build ok; vitest 76 files, 938 tests; backend 1,132 passed and `test_ledger_ratchets` failed, which the 82 baseline already lists; Rust `--lib` 400 passed, 1 ignored; drift and UI gates did not block). This says nothing about live behaviour: the Manual-Only table above still stands, and the full backend suite is still to be compared by name.

## Validation Audit 2026-11-02

| Metric | Count |
|---|---|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
