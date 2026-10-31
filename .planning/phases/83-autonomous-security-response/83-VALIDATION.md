---
phase: "83"
slug: "autonomous-security-response"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
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

Requirement-level map seeded from 83-RESEARCH.md. The executor replaces `83-TBD` with task ids as plans are executed.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 83-TBD | TBD | TBD | RESP-01 | R7 | The sweep turns candidates into gate decisions, reads global feed rows only through the raw handle, and resolves hostname to one `agents.id`; vulnerabilities and file changes become suggestions; a file finding routes to quarantine, never kill | unit + real-Mongo | `pytest backend/tests/test_autonomous_ops_sweep.py -x` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | RESP-02 | R1, R4, R6 | TTL travels in the instruction; an idempotent claim, expiry while offline and across restart, refcounted undo that removes only its own claim; a CIDR needs approval; the agent refuses non-global addresses, the platform, gateway and DNS | Rust unit with a command recorder; backend params test | `cargo test --offline response_state`; `pytest backend/tests/test_autonomous_ops_block_contract.py -x` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | RESP-03 | R3, R5, R10 | Moved, never deleted; hash-bound; manifest; restore only to the manifest path; refuses a symlink, a directory, its own directories and an existing destination | Rust integration with tempdirs | `cargo test --offline --test quarantine_dispatch_test` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | RESP-04 | R3 | Listed services only; an admin stop is not a failure; budget of 3 per service per host per rolling hour, then one card; argv-only spawn; server regex matches the agent's rule | backend + Rust unit | `pytest backend/tests/test_autonomous_ops_restart_budget.py -x`; `cargo test --offline service_watch` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | RESP-05 | R4 | Management allow rules applied and verified before any block; self-test failure reverts; agent-held 4-hour revert with no network; confirm cancels the revert; a confirmed finding adds at most one isolate line per incident | Rust unit with a command recorder; route test | `cargo test --offline isolation`; `pytest backend/tests/test_autonomous_ops_confirm_isolation.py -x` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | RESP-06 | — | `verify.ok` true gives `verified`; false gives `failed` with no unblock dispatched; the original finding is never re-read | real-Mongo | `pytest backend/tests/test_autonomous_ops_verify.py -x` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | RESP-07 | — | Ten consecutive ticks create at most one row, including for recorded refusals; no redo for 24 h after undo; a re-block after expiry needs evidence newer than the old block | real-Mongo + frozen clock | `pytest backend/tests/test_autonomous_ops_sweep_dedupe.py -x` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | RESP-08 | R1, R2, R8 | Two distinct origins by default; two entries of one origin never count; deception and manual IOCs never count; 24-hour promotion; the switch is honoured and every change is recorded; 3 automatic actions per host per hour | unit + real-Mongo | `pytest backend/tests/test_autonomous_ops_origins.py -x` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | RESP-09 | — | One-hour quiet gap, restart-safe, one card for a burst | real-Mongo | `pytest backend/tests/test_autonomous_ops_incidents.py -x` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | RESP-10 | R6 | Dormant without the tick, without the token, while offline and on an old agent, with no breaker effect; hash mismatch and no-ops do not count toward the breaker | real-Mongo | `pytest backend/tests/test_autonomous_ops_dormancy.py -x` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | RESP-11 | — | No writer to `db.instructions` remains; the routes answer not-sent; `agents.isolated` is unchanged; automatic XDR containment only suggests | structural + route | `pytest backend/tests/test_autonomous_ops_structural.py backend/tests/test_swarm_soar_fence.py -x` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | ACTV-02 | R8, R11 | Approve, deny, undo and confirm need the control permission and an interactive session; the settings panel needs the manage permission; bulk is Super Admin only; strings render as text | vitest + route | `npx vitest run src/__tests__/autonomousOpsResponse.test.tsx`; `pytest backend/tests/test_autonomous_ops_response_endpoints.py -x` | ❌ W0 | ⬜ pending |
| 83-TBD | TBD | TBD | Copy (ACTV-08) | — | No banned term in any new file | existing | `pytest backend/tests/test_autonomous_ops_copy.py -x`; `npx vitest run src/__tests__/autonomousOpsCopy.test.ts` | ✅ extend | ⬜ pending |
| 83-TBD | TBD | TBD | Catalogue | — | New routes are mounted, guarded and in parity | existing | `pytest backend/tests/test_catalogue_slice_autonomous_ops.py backend/tests/test_catalogue_route_parity.py -x` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Every test file marked ❌ W0 above, written before the code that satisfies it
- [ ] `agent-install/omni-agent-rs/src/capabilities/remediation_actions.rs` — a thread-local recorder replacing the `#[cfg(test)]` no-op `run_privileged_command`, returning scripted results
- [ ] A hermetic Rust fixture for `response_state.json` with an injectable clock
- [ ] `backend/tests/autonomy_support.py` — seeding helpers for global `edr_ioc` rows, `fim_events` and agents with `meta.response_actions` and a hostname that differs from the id

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Publish and roll out agent 2.1.16 | RESP-10 | User's step; publishing and `_LATEST_AGENT_VERSION` are not automated | Publish, bump the version, confirm `meta.response_actions` tokens appear for a test host |
| Firewall round trip, both directions, IPv4 and IPv6 | RESP-02 | Needs root and a real firewall | Block and unblock on real Linux and on Windows EILT0197 with Defender on |
| A block expiring while offline, across an agent restart and a reboot | RESP-02 | Needs a real host and network | Set a 1-hour block, take the host offline, confirm the rule is gone at expiry |
| Quarantine of a running file, and restore, on Windows | RESP-03, D-27 | Assumed OS behaviour; Defender in the loop | Run a harmless test binary, quarantine it, confirm `still_running` and the kill-only card, restore |
| Isolation with the management connection open, automatic revert, reboot while isolated, Group Policy firewall | RESP-05 | Risk of losing a host; needs a real network | Use a shortened revert on a test host first, then the full 4 hours; confirm the platform stays reachable |
| Real service restart, and admin stop versus crash | RESP-04 | OS exit-code semantics are assumed | Crash and stop a test service on Linux and Windows; only the crash may restart |
| Defender behaviour for `netsh`, `sc` and `shutdown` | RESP-02, RESP-04, RESP-10 | No documentation either way | Run each action on EILT0197 and check Defender history |
| Public feed signals | D-26 | Needs the user's abuse.ch key and a live database read | Set `ABUSE_CH_AUTH_KEY`, restart, count `edr_ioc` by `source_feeds` |
| Browser pass of the cards, Undo and settings panel | ACTV-02 | Needs a published UI | Light and dark at 640, 1024 and 1280 px, including the 1280px no-sideways-scroll check |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
