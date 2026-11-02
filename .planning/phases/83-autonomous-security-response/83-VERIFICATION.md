---
phase: 83-autonomous-security-response
verified: 2026-11-02T12:40:00Z
status: human_needed
score: 5/5 must-haves verified
covered_files:
  - ".planning/phases/83-autonomous-security-response/83-01-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-01-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-02-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-02-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-03-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-03-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-04-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-04-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-05-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-05-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-06-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-06-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-07-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-07-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-08-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-08-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-09-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-09-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-10-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-10-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-11-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-11-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-12-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-12-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-13-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-13-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-14-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-14-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-15-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-15-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-16-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-16-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-17-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-17-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-18-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-18-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-19-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-19-SUMMARY.md"
  - ".planning/phases/83-autonomous-security-response/83-20-PLAN.md"
  - ".planning/phases/83-autonomous-security-response/83-20-SUMMARY.md"
  - "agent-install/omni-agent-rs/src/capabilities/isolation.rs"
  - "agent-install/omni-agent-rs/src/capabilities/net_safety.rs"
  - "agent-install/omni-agent-rs/src/capabilities/privileged.rs"
  - "agent-install/omni-agent-rs/src/capabilities/quarantine.rs"
  - "agent-install/omni-agent-rs/src/capabilities/response_actions.rs"
  - "agent-install/omni-agent-rs/src/capabilities/response_sweeper.rs"
  - "backend/autonomous_ops/agent_support.py"
  - "backend/autonomous_ops/delivery.py"
  - "backend/autonomous_ops/incidents.py"
  - "backend/autonomous_ops/registry.py"
  - "backend/autonomous_ops/signals.py"
  - "backend/autonomous_ops/sweep.py"
  - "backend/autonomous_ops/sweep_restart.py"
  - "backend/autonomous_ops/sweep_security.py"
  - "backend/autonomous_ops/verify.py"
  - "backend/soar_engine.py"
  - "backend/swarm_endpoints.py"
  - "backend/swarm_service.py"
  - "components/AutonomousOpsDecisions.tsx"
  - "components/AutonomousOpsIncidentCard.tsx"
  - "components/AutonomousOpsRowActions.tsx"
  - "shared/agent-response-contract.json"
covered_digest: "v3:sha256:169c06b6903a907084bae8b35cd2f1aada64ab58b942016f87a113f5cc57f9e8"
behavior_unverified: 0
overrides_applied: 0
unverified_prohibitions: 18   # all 18 PROH-83-xx are judgment-tier; verdicts below are NON-AUTHORITATIVE, human review recommended
human_verification:
  - test: "DECISION BEFORE PUBLISHING 2.1.16: fix Rust CR-01 (no child-process timeout while WRITE_LOCK / isolation LOCK are held, privileged.rs:58-68) and CR-02 (net_safety.rs:281-302 tests only a CIDR's base address, so 172.0.0.0/8 and 192.0.0.0/8 pass), or consciously accept them"
    expected: "A gap-closure plan (or a quick fix) lands both, with tests: a hung child is killed after a deadline and the pass returns an error; a network that overlaps any non-global range is refused by the agent (and by backend signals.global_range, which has the same flaw)"
    why_human: "Both are real in the committed code and verified here. Neither defeats a must-have as written (see Gaps Summary), but both sit in code the user is about to ship, so the user decides whether to fix first. Review also lists agent WR-17, WR-18, WR-19, WR-14 as worth fixing in the same pass."
  - test: "Read the sentences the UI-SPEC does not word (83-20 Live list item 1) and confirm A-83-LEVEL-SUGGEST (item 2: which Suggest-level rows appear as approvable lines)"
    expected: "Wording accepted, or edited, before the UI is published"
    why_human: "Product wording and a product-rule choice"
  - test: "Accept the two agent behaviour changes before publishing 2.1.16 (item 3): a block_ip with no ttl_seconds lasts 24 hours; the agent refuses every non-global address (RFC 1918 included), the platform host, gateway, DNS servers and networks wider than /8"
    expected: "Accepted"
    why_human: "Changes the behaviour of an existing instruction on every host"
  - test: "Publish the UI (dist-new index-VUPN-kZs.js) and then agent 2.1.16 with _LATEST_AGENT_VERSION bumped from 2.1.14; confirm meta.response_actions tokens arrive from a test host (items 4-5)"
    expected: "Cards, Undo and settings render; heartbeat carries tokens block_ip_ttl, block_ip_range, quarantine_file, unquarantine_file, kill_process_exe, restart_service, service_failures, isolate_host, restore_host, reboot_host; RESP-10 can then be ticked"
    why_human: "Publishing is the user's step; nothing of the agent half has run on a real host"
  - test: "Lift one tenant out of shadow and watch what the sweep does; set ABUSE_CH_AUTH_KEY, restart the backend and count edr_ioc by source_feeds (items 6-7)"
    expected: "Simulation rows only while in shadow; automatic block/quarantine stay uncommon until two real origins exist (A-83-SCAN, A-83-ONHOST); with the key set the public-feed origin gets rows"
    why_human: "Needs live data and a Super Admin decision; 4 of 4 tenants are in shadow"
  - test: "Firewall round trip on real Linux (beside ufw or firewalld) and on EILT0197 with Defender on, IPv4 and IPv6, both directions, using a routable address such as 45.33.32.156 (item 8)"
    expected: "Rule exists after block (verify check firewall_rule_present), traffic is dropped, Undo removes it; no Defender interference"
    why_human: "Real firewall behaviour; every agent test uses a recorder, none touches a real firewall"
  - test: "A 1-hour block expiring while the host is offline, across an agent restart and a reboot (item 9)"
    expected: "Rule gone at expiry without any platform contact; backend row unchanged"
    why_human: "Real clock, real reboot; only unit-tested with an injectable clock"
  - test: "Quarantine and restore of a running harmless test binary on Windows, including the kill-only card (item 10)"
    expected: "Correct one of 'still running' or 'locked'; kill card ends the process before the row reads Done; restore returns the file; quarantine directory ACL checked"
    why_human: "Windows file locking and process semantics were written from documentation"
  - test: "Isolation on a throwaway host with a shortened revert first (item 11), including a reboot while isolated and a Group Policy firewall"
    expected: "Management connection stays open; host really is cut off from everything else (review WR-20: the agent's own verify does not test this); automatic revert and Confirm isolation work; a host with a missing state file does not stay isolated (WR-17)"
    why_human: "A mistake can lose a host; no test proves the effect on traffic"
  - test: "Capture real Windows output (sc, netsh, route print, error codes 5, 225, 4551) on EILT0197 and compare with the parser fixtures; check Defender history for netsh/sc/shutdown spawned by the agent (items 12, 14)"
    expected: "Parsers match; no blocked_by_local_security; written exclusion guidance produced (open threat T-83-15)"
    why_human: "Cannot be checked off-host"
  - test: "Crash and stop a test service on both operating systems (item 13)"
    expected: "Only the crash restarts it; an administrator stop does not"
    why_human: "Real service manager behaviour"
  - test: "Browser pass of cards, Undo and settings, light and dark, 640/1024/1280 px, no sideways scroll at 1280 (item 15)"
    expected: "Matches 83-UI-SPEC; 83-UI-REVIEW warnings (role=status on li, SwarmDashboard dark style, 16px checkboxes) decided"
    why_human: "Visual; UI unpublished and no screenshots were captured"
  - test: "Decide the open known defects (items 16-17): the over-budget restart card stays approvable after the service recovers (WR-03); remediation_service.py still marks a vulnerability Patched after a worker task answering not_sent (A-83-PATCHED, T-83-27)"
    expected: "Fixed, deferred to a later phase, or accepted"
    why_human: "Product and risk decision; both are open at medium severity"
---

# Phase 83: Autonomous Security Response Verification Report

**Phase Goal:** Security findings turn into containment on their own when it is undoable (block a malicious IP, quarantine a malicious file, restart a failed service) and into one-click approval cards when it is destructive, with each action verified, undoable from the Autonomous Ops screen where an inverse exists, and never repeated or amplified.
**Verified:** 2026-11-02T12:40:00Z
**Status:** human_needed
**Re-verification:** No, initial verification

## Verdict in one paragraph

The code delivers each of the five roadmap success criteria, and I found no must-have that is missing, stubbed or unwired. Nothing has run on a real host: the agent (2.1.16) and the UI are unpublished, every tenant is in shadow, and `_LATEST_AGENT_VERSION` is still 2.1.14. So the honest status is `human_needed`, not `passed`: the real-firewall, real-Windows, real-isolation and browser behaviour is unproven, and two critical review findings in the unpublished Rust agent are real and should be fixed (or consciously accepted) before the agent is published. I classify them as defects to fix before publishing, not as gaps against a must-have (reasons under Gaps Summary).

## Goal Achievement

### Observable Truths (roadmap Success Criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A scan verdict / vulnerability / file change becomes a playbook action through the gate; at Undoable-auto a two-source IP is blocked 24 h (agent removes it at expiry without the platform), a malicious file is quarantined (moved, not deleted), a failed service is restarted within budget; one signal is a suggestion; an IP range or exhausted budget needs approval | VERIFIED (code and unit tests); real-host behaviour to human | `sweep.py:63` stages `sweep_security, sweep_suggestions, sweep_restart, isolation.run`, started at `app_startup.py:513-515`. `sweep_security.run` (369 lines): two origins within 24 h go through `gate.decide` and `response_dispatch.send` (L288-293); one origin calls `gate.suggest` (L194-203, L360); params `ttl_seconds = block_hours*3600`, default 24 h (`response_settings`, plan 83-01 truth). Range: `registry.py:62` `cidr_params`, `gate.py:200` `escalate ... "range_block"`. Restart: `sweep_restart.py` `RESTART_BUDGET = 3`, over-budget becomes one `playbook_raise` card. Agent: `lib.rs:46` `spawn_sweeper` before `ensure_registered` (L94); `response_sweeper.rs` 15 s pass; quarantine moves, original removed only after a re-hashed copy (`quarantine.rs:57-59,233-252`). My runs: 378 backend tests passed (block_contract, two_signal, sweep_dedupe, verify, structural, range_block, restart_budget, dormancy, approvals, xdr_fence, origins, incidents); Rust `--lib capabilities::` 374 passed, 0 failed. |
| 2 | Kill process and isolate host appear as approval cards, one card per incident; isolation keeps the agent's management connection open and reverts automatically after a set time unless confirmed | VERIFIED (code and unit tests); effect on real traffic to human | `registry.py:46-48` `isolate_host`, `kill_process`, `reboot_host` are `approve`. `incidents.py`: one open incident per host (unique partial index `incident_one_open`), 1 h quiet gap, `claim_isolate` compare-and-set so one isolate line per incident; `sweep_security._propose_isolation` L241-262. Kill lines only from `followups.py` (quarantine `locked`), never sent from there (PROH-83-15). Agent: `isolation_plan.rs` header and `isolation.rs` order every allow rule and its check before any block step; `REVERT_SECONDS = 14_400`; `isolation::revert_due` called from the sweeper; `start_up` and `due_pass`. UI: `AutonomousOpsDecisions.tsx` fetches `/incidents`; `AutonomousOpsIncidentCard.tsx` Approve / Deny / Confirm isolation. WR-20: the agent's own "isolated" check does not test that traffic is actually cut; live item 11. |
| 3 | Each action is verified by its own check, a successful block is never reverted; the same finding does not create a new action every cycle; an action an operator undid is not redone for 24 h | VERIFIED | `verify.py` header and `settle`: moves `executed` to `verified` or `failed verify_failed` from the agent's own result only; grep for `security_scan_results`, `remediate`, `_dispatch_and_verify` in `verify.py`, `response_dispatch.py`, `reconciler.py` returns nothing, and a structural test keeps it that way (passed). Dedupe: `sweep_memory.skip_reason` before any gate call, `signals.remember`, open-dedupe unique index; `_act` L275-282 records one refused row within `COOLDOWN` (24 h) of an undo and sends nothing. Tests `sweep_dedupe` (ten ticks, undo edge at exactly 24 h) and `verify` passed in my run. |
| 4 | From the Autonomous Ops screen an operator can approve or deny pending actions and undo done actions that have an inverse, with one click | VERIFIED (code and vitest); browser pass to human | Routes `autonomous_ops_endpoints.py:416,428,441` (`approve`, `deny`, `undo`) and `autonomous_ops_response_endpoints.py:130,153` (`incidents`, `confirm-isolation`). Client `services/autonomousOpsApi.ts:406` `undoAutonomousOpsAction`, `autonomousOpsIncidentsApi.ts:107-113`. Components `AutonomousOpsRowActions.tsx` (Undo, server `canUndo`) and `AutonomousOpsIncidentCard.tsx`. Registry inverse: `block_ip` to `unblock_ip`, `quarantine_file` to `unquarantine_file`, `isolate_host` to `restore_host`. My vitest run of `autonomousOpsDecisionsCards` and `autonomousOpsResponse`: 39 passed; orchestrator's full vitest 938 passed, `npm run build` ok. |
| 5 | The Rust agent supports restart service, quarantine/restore file, isolate/restore host, reboot host, each gated by the tenant's capability ticks, dormant until the agent reports support; swarm "propagate antibody" and SOAR block/isolate are fenced | VERIFIED in code; agent publication is the user's step | `response_actions.rs:36-51` `SUPPORTED_TOKENS` and `HANDLED`; heartbeat carries `meta.response_actions` (HEAD `heartbeat.rs`). `agent_capabilities.py:74-87` maps the new commands. `agent_support.check` (capability, then online, then token, never a version number) and `gate_step`, re-run at approval. Python agent: not supported by decision D-19 (Rust only), so the requirement's "where that agent stays supported" clause does not apply and it never reports tokens, so its rules stay dormant. Fences: `swarm_service.py` propagate-antibody sends nothing (`not_sent`); `soar_engine.py:179-186` `block_ip_firewall` sends nothing; `swarm_endpoints.py:34,126` strips `isolate_host`; `delivery.py:48-56` refuses any unstamped `GATE_ONLY_COMMANDS` item at the agent poll. Manifest 2.1.16 committed (`git show HEAD:.../Cargo.toml`); `_LATEST_AGENT_VERSION` still 2.1.14 (`agent_auto_update_service.py:20`). |

**Score:** 5/5 roadmap truths verified (0 present-but-behavior-unverified: each behavior-dependent truth has a passing test that exercises the transition or invariant; what no test can reach is a real host, and that is listed under Human Verification).

### Required Artifacts (Level 1-3)

| Artifact | Status | Details |
|----------|--------|---------|
| `shared/agent-response-contract.json` | VERIFIED | read by `agent_support.py:29-34` at import and by the Rust contract tests |
| `backend/autonomous_ops/{sweep,sweep_security,sweep_restart,sweep_suggestions,signals,sweep_memory,verify,response_dispatch,decision_row,incidents,followups,agent_support,delivery,protected_paths,response_settings,response_views,incident_views,response_messages}.py` | VERIFIED | exist, substantive (sweep_security 369 lines, signals 499), wired (sweep started in `app_startup.py`, stages in `sweep._STAGES`, gate steps in `gate.py`) |
| `backend/migrations/028_security_response.py` | VERIFIED | exists; orchestrator reports applied 04:07:43 today |
| Rust `capabilities/{privileged,response_state,firewall,net_safety,response_actions,response_sweeper,isolation,isolation_plan,quarantine,quarantine_paths,service_watch,host_power,process_kill}.rs` | VERIFIED | committed at HEAD and declared in HEAD `capabilities/mod.rs:25-36`; `lib.rs` `spawn_sweeper` in HEAD; uncommitted hunks in `lib.rs`, `heartbeat.rs`, `mod.rs` are the user's unrelated flate2/interval work |
| `components/AutonomousOps{Decisions,IncidentCard,RowActions,ResponseSettings*}.tsx`, `services/autonomousOps{Api,IncidentsApi}.ts` | VERIFIED | wired through `AutonomousOpsActivity.tsx`; real fetches, no static fallbacks |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `app_startup.py:513` | `sweep.sweep_loop` | `_safe_bg_task` | WIRED |
| `sweep_security` | `gate.decide` then `response_dispatch.send` only on `dispatching` | L288-293, L212-231 | WIRED |
| `reconciler` | `verify.settle` | security_response rows after `executed` | WIRED (tests) |
| `agent poll` | `delivery.hold_back_*` | unstamped gate-only command refused | WIRED |
| `lib.rs agent_loop` | `response_actions::spawn_sweeper` | L46, before registration L94 | WIRED |
| `heartbeat.rs` | `meta.response_actions` | `build_payload` | WIRED (HEAD) |
| Incident card | `/approve` `/deny` `/confirm-isolation`, row Undo | `autonomousOpsIncidentsApi.ts`, `autonomousOpsApi.ts:406` | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| Decisions section | incident cards | `GET /incidents` reads ledger and incidents collections | yes | FLOWING |
| Row Undo | `canUndo`, `undoHint`, `blockedUntil` | `response_views.row_extras` computed from the ledger row and viewer | yes | FLOWING |
| Sweep candidates | origins | native scan results, `edr_ioc` feeds, FIM/VT alerts via `signals.observe` | yes (but feed rows need `ABUSE_CH_AUTH_KEY`; no scan is scheduled, A-83-SCAN) | FLOWING, thin on a live tenant |

### Behavioral Spot-Checks and Test Evidence

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Core response path (12 files) | `pytest` on private mongod 27998: block_contract, two_signal, sweep_dedupe, verify, structural, range_block, restart_budget, dormancy, approvals, xdr_fence, origins, incidents | 378 passed in 244 s | PASS |
| Agent capabilities | `cargo test --offline --lib capabilities::` (no-debug target) | 374 passed, 0 failed, 27 filtered | PASS |
| Decisions and settings UI | `npx vitest run` decisions cards + response tests | 39 passed | PASS |
| Full gates (orchestrator, not re-run) | build; vitest 938; backend 5,711 passed / 4 failed / 47 skipped; Rust lib 400 passed; Windows `cargo check --lib` exit 0 | all 4 backend failures are in the 2026-10-31 baseline (82-VALIDATION.md); no new failure | PASS (relied on) |
| `ipaddress.ip_network("172.0.0.0/8").is_global` | `backend/venv/bin/python -c ...` | `True` (also `192.0.0.0/8`), so the backend range filter shares CR-02 | evidence for CR-02 |

### Probe Execution

SKIPPED: the phase declares no `probe-*.sh` scripts.

### Requirements Coverage (all 12 phase IDs are claimed by plan frontmatter, none orphaned)

| Requirement | Plans | Status | Evidence | REQUIREMENTS.md now |
|-------------|-------|--------|----------|---------------------|
| RESP-01 | 83-01, 05, 06, 11, 15 | SATISFIED | sweep to gate, legacy loop gone (Phase 81), legacy `quarantine_file` playbook path still noisy (WR-08, not a miss) | ticked |
| RESP-02 | 83-01, 02, 03, 04, 08, 10 | SATISFIED in code, live-unproven | 24 h default, agent expiry, range needs approval, Undo; CR-01/WR-18/WR-19 fault-path caveats | unticked: can be ticked once the user accepts the pre-publish decision |
| RESP-03 | 83-03, 09, 10, 11, 16 | SATISFIED in code, live-unproven | moved never deleted, restore, Undo | unticked: same |
| RESP-04 | 83-07, 13, 14, 17 | SATISFIED in code, live-unproven | budget 3 per hour from the ledger, then one card; WR-03, WR-04 open | unticked: same |
| RESP-05 | 83-09, 11, 12, 16, 18, 19 | SATISFIED in code, live-unproven | approval cards, carve-out, 4 h revert; WR-17, WR-20 | ticked (see human items 9-11) |
| RESP-06 | 83-01, 02, 09, 16 | SATISFIED | own-check verify, structural no-reread test | unticked: can be ticked |
| RESP-07 | 83-05 | SATISFIED | dedupe windows, 24 h undo suppression, tests | unticked: can be ticked |
| RESP-08 | 83-03, 05, 07, 13 | SATISFIED | two-origin rule, mirrored alerts collapse, tenant and Super Admin switch with ledger row (PROH-83-09) | unticked: can be ticked |
| RESP-09 | 83-11, 18, 19 | SATISFIED | one open incident per host, one card per incident | ticked |
| RESP-10 | 83-02, 08, 09, 12, 14, 20 | NOT YET: code complete, not shipped | actions, tokens and dormancy exist; agent unpublished, `_LATEST_AGENT_VERSION` 2.1.14 | leave unticked until publish (human items 4-5) |
| RESP-11 | 83-06 | SATISFIED | fences and delivery rule; IN-08 residual below | ticked |
| ACTV-02 | 83-01, 03, 07, 10, 18, 19 | SATISFIED | approve, deny, undo routes and UI | ticked |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| Phase files (backend `autonomous_ops`, endpoints, migration 028, Rust response/isolation/quarantine files, `AutonomousOps*.tsx`, services, contract) | `TBD`/`FIXME`/`XXX` grep | none found | no debt-marker blocker |
| `agent-install/omni-agent-rs/src/capabilities/privileged.rs:58-68` | `Command::output()` with no timeout while `WRITE_LOCK` (`response_state.rs:127,182`) / `isolation::LOCK` are held (review CR-01, confirmed by reading) | Defect, fix before publish | a hung `iptables -w` or `netsh` stops expiry, the isolation revert and, because quarantine/block arms run inline, the agent loop |
| `agent-install/omni-agent-rs/src/capabilities/net_safety.rs:287-293` | judges a network by its base address (review CR-02, confirmed) | Defect, fix before publish | `172.0.0.0/8`, `192.0.0.0/8`, `100.0.0.0/8`, `169.0.0.0/8` pass the agent; backend `signals.global_range` passes them too |
| `agent-install/.../isolation.rs:310-338` | `restore` with no record returns `not_found`, `verify ok` without looking at the firewall (WR-17, confirmed) | Warning, fix before publish | a missing state file leaves a Windows host isolated |
| `backend/autonomous_ops/sweep.py:79-84` | one `try` around all stages (WR-07, confirmed) | Warning | a failing early stage skips restarts and isolation bookkeeping for that tenant |
| `backend/autonomous_ops/delivery.py:48-56` | gate-only list excludes `block_ip`, `kill_process` (IN-08) | Info | a model-planned swarm step typed `block_ip` is not refused at poll; it carries `payload: {}` so the agent has no address to act on |
| `components/` and `src/` (83-UI-REVIEW) | 19/24, no blocker | Warning | `role=status` on `<li>`, SwarmDashboard dark style, 16 px checkboxes, stale chip on a 409 |

83-REVIEW.md: 2 critical, 30 warning, 23 info, all `open` in 83-REVIEW-DISPOSITION.md (55 open). 83-SECURITY.md: 76 threats, `threats_open: 0` at the blocking severity, two medium open (T-83-15 written AV-exclusion guidance, T-83-27 A-83-PATCHED). I read the review's criticals, WR-01 to WR-22, IN-08 and the finding map headings; I did not read the frontend warnings WR-23 to WR-30 or IN-01 to IN-07, IN-09 to IN-23 in full.

### Prohibitions (judgment-tier, non-authoritative LLM-judge verdicts; every one is flagged `unverified-prohibition: human review recommended`)

| ID | Statement (short) | My verdict |
|----|-------------------|------------|
| PROH-83-01 | no LLM / free text chooses an action | Holds: `sweep_security.py` imports no model and reads structured fields (`signals`); SOAR and swarm fences added |
| PROH-83-02 | no rule without an agent-held expiry | Holds on the normal path (claim written before the rule, sweeper before registration). Fault paths: CR-01 delays it behind a hung command, WR-18 (unreadable state) and WR-19 (failed check drops a live claim) can strand a rule |
| PROH-83-03 | one signal never counted as two | Holds in tests (mirrored alerts collapse); WR-01/WR-05 affect staleness and the "why" text, not counting |
| PROH-83-04 | agent never deletes a user's file | Holds in the move design; IN-14 notes a cross-volume file changed after the verified copy can still lose its original |
| PROH-83-05 | isolation never strands a host | Mostly: corrupt/unreadable state lifts isolation; WR-17 (missing record, rules present) does not. Needs live item 11 |
| PROH-83-06 | success never undone because finding persists | Holds (structural test) |
| PROH-83-07 | a block never cuts platform, gateway, DNS | Holds for those three (best-effort reads); CR-02 means a wide LAN-covering network is not refused by either layer |
| PROH-83-08 | no cross-host action, no feed-only action | Holds (candidates need an observation on the host) |
| PROH-83-09 | two-source rule never loosened silently | Holds (ledger control row and audit event) |
| PROH-83-10 | nothing "sent" reports success | Holds for SOAR/swarm; WR-11 (run-level `completed`) and A-83-PATCHED remain |
| PROH-83-11 | plumbing never trips the breaker | Holds except WR-04 (restart budget equals breaker threshold) |
| PROH-83-12 | no approve-all / undo-all, no client-side authority guess | Holds (server flags; no bulk undo) |
| PROH-83-13 | isolation, kill, reboot never without a person | Holds (`registry.py` approve class; follow-ups never send) |
| PROH-83-14 | no restart after an admin stop, off the watched list, agent itself or critical service | Backend holds; agent does not re-check the watched list (WR-21) |
| PROH-83-15 | no automatic kill | Holds |
| PROH-83-16 | restart budget not resettable | Holds (counted from the ledger) |
| PROH-83-17 | API key never decides; no offered control the server did not grant | Holds in code; WR-27 (browser clock) is cosmetic |
| PROH-83-18 | kill never reports gone while alive; never signals a reused PID | Holds for the `expected_exe` path; legacy path without `expected_exe` is WR-14 |

### Human Verification Required

See the `human_verification` list in the frontmatter (13 items, drawn from the 83-20 Live list plus the pre-publish decision on CR-01/CR-02). Nothing in the agent half has run on a real host, the UI is unpublished, and all four tenants are in shadow, so these are the expected live checks, not code gaps.

### Gaps Summary

No must-have gap. The two critical review findings, decided as asked:

- **CR-02 (network guard tests only the base address): a defect to fix before publishing, not a gap.** It is real: `refuse_reason` calls `is_global_address(target.addr)` once on the masked base address and then only refuses prefixes shorter than /8; the backend's `global_range` has the same weakness (`ip_network('172.0.0.0/8').is_global` is `True`). It does not defeat a must-have because (a) every network block is forced to an approval card at the gate (`range_block`), so no automatic or "amplified" action can carry a range; (b) a range candidate exists only when a global feed lists it and a host actually talked to an address inside it, so reaching it takes a mis-listed feed plus a person approving the card; (c) the platform, gateway and DNS checks still refuse a network that covers them, so PROH-83-07 holds for what it names; (d) the plan's literal truth (refuse a network wider than /8, or one containing the platform host) is met. What it does falsify is 83-SECURITY T-83-12 being "closed", and the agent's stated independence from the backend, so fix both layers and the threat row.
- **CR-01 (no child-process timeout under the process locks): a defect to fix before publishing, not a gap.** It is real (`privileged.rs:58-68`, `response_state.rs:127,182`, sweeper `spawn_blocking(...).await`). Under normal operation the success criteria hold: expiry runs every 15 s, the revert runs from the same pass, and nothing in the criteria promises survival of a hung firewall tool. It does not touch "never repeated or amplified". But it is the more serious of the two for publishing: one stuck `iptables -w` or `netsh` can stall every block expiry and the isolation revert (so a host stays isolated, which breaks D-15's promise that the agent holds its own revert) and, since block, unblock and quarantine run inline on the agent loop, stop heartbeats for the whole host. Publishing is what exposes this, and it would be a regression for hosts that run the new binary today. Recommend a fix before 2.1.16 ships, together with WR-17 (missing state file leaves isolation in place), WR-19 and WR-18 (a block that can outlive its claim), which are the same family: the guarantee "the agent ends its own blocks and isolations" is correct on the normal path and not yet fault-tolerant.

If the user would rather have these tracked as a gap round, `/gsd-plan-phase 83 --gaps` with CR-01, CR-02, WR-17, WR-18, WR-19, WR-14, WR-16 and the backend WR-07 is the natural scope; I did not mark the phase `gaps_found` because no roadmap criterion or plan must-have is unmet as written.

Residuals that are not gaps: A-83-SCAN (no scan is scheduled, so automatic block and quarantine will be rare until real origins exist, D-23 accepted), the swarm mission fence is a one-value denylist backed by the unstamped-command refusal at delivery (IN-08), the legacy `quarantine_file` playbook yields noise cards (WR-08), and the unticked `_LATEST_AGENT_VERSION`.

### What I did not read or run

Read in full or in the relevant part: ROADMAP phase block, REQUIREMENTS lines, frontmatter must-haves of plans 83-01 to 83-11, 83-20-SUMMARY, 83-REVIEW-DISPOSITION, 83-REVIEW (criticals, WR-01 to WR-22, IN-08), 83-UI-REVIEW (top 80 lines), 83-SECURITY (header and open rows), 83-VALIDATION (first 40 lines), and the code cited above. Not read: frontmatter must-haves of plans 83-12 to 83-19 (the roadmap criteria and the code and test names stand in), the bodies of every SUMMARY except 83-20, 83-CONTEXT (only grep for D-19), 83-UI-SPEC, 83-RESEARCH, 83-PATTERNS, review WR-23 to WR-30 and most Info items, the Rust `response_state.rs` expiry code beyond the lock lines, `gate.py` and `reconciler.py` beyond the cited lines, and `response_settings.py`. Not run: the full backend suite (the orchestrator did, 5,711 passed / 4 baseline failures), the Rust integration targets, the Windows build, `npm run build`, and anything against the live mongod. My Rust run is the Linux `cargo test --lib capabilities::`; Windows `cfg(windows)` arms were exercised only by the orchestrator's `cargo check`.

---

_Verified: 2026-11-02T12:40:00Z_
_Verifier: Claude (gsd-verifier)_
