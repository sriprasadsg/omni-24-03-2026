---
phase: 83-autonomous-security-response
plan: 05
subsystem: autonomous-ops
tags: [autonomous-ops, sweep, two-signal-rule, threat-feeds, decision-memory, mongodb, pytest]

requires:
  - phase: 83-autonomous-security-response
    provides: "83-01 sweep + signals + gate path; 83-03 response_messages (WHY_TEMPLATES, ORIGIN_NAMES) and row_extras"
provides:
  - signals.py with the six origins (native, feed:urlhaus, feed:malwarebazaar, feed:otx, virustotal, onhost), alert_origin, every reader, counting_origins and the two-origin rule
  - sweep_security: one origin suggests, a second inside 24 hours acts, the tenant switch is honoured, evidence before an expired block is ignored (D-14)
  - sweep_memory (WINDOWS, latest_state, block_window, skip_reason) and the per-computer hourly cap
  - threat_feed_sync: ABUSE_CH_AUTH_KEY header to abuse.ch only, source_feeds and feed_seen per indicator
  - migration 028 (indexes only)
affects: [83-06, 83-07, 83-08, 83-09, 83-11, 83-16, 83-17]

actuals:
  tokens: 24990
  tasks: 3
  commits: 7
plan_head_before: 6c861a541fa4463907c4374bef4da769711e1c8c
plan_head_after: fda46a1c5bbc08ad8d33377b7f74d3a727039f31

tech-stack:
  added: []
  patterns:
    - "Telemetry says what a host HAS; only an origin makes a candidate; a feed row counts only for a host that has the thing"
    - "The ledger row, not the sweep's memory, is the truth about a decision: the memory only points at it"
    - "A suggestion is kept alive by a non-state update (no audit event) while its origin is still seen"

key-files:
  created:
    - backend/autonomous_ops/sweep_memory.py
    - backend/migrations/028_security_response.py
    - backend/tests/test_autonomous_ops_origins.py
    - backend/tests/test_autonomous_ops_two_signal.py
    - backend/tests/test_autonomous_ops_sweep_dedupe.py
    - backend/tests/test_threat_feed_sync_origins.py
  modified:
    - backend/autonomous_ops/signals.py
    - backend/autonomous_ops/sweep_security.py
    - backend/autonomous_ops/ledger.py
    - backend/autonomous_ops/gate.py
    - backend/autonomous_ops/response_messages.py
    - backend/threat_feed_sync.py
    - backend/tests/autonomy_support.py
    - backend/tests/test_autonomous_ops_block_contract.py

key-decisions:
  - "A mirrored alert is classified back to its source (native, virustotal) so one event is one origin; only an alert that is neither is onhost. onhost has no live writer today."
  - "The edr_ioc sync also writes feed_seen.<feed> (when each feed last listed an indicator), so a feed that stopped listing something cannot keep counting because another feed refreshed the row's updated_at."
  - "corroborated: any two origins within 24 hours agree (inclusive), whatever a third one did; the first-to-last span the 83-01 version used would have let a late third origin spoil a real pair."
  - "Suggestions are not written to the signal's decision memory: that slot also holds blockedFrom/blockedUntil, which D-14 needs after a block runs out."
  - "A refusal written for an undo carries holdUntil (the end of the 24 hour undo window) in the memory, so it does not extend the hold to a day after the refusal."

patterns-established:
  - "skip_reason(decision, ledger row, current origins, now) returns a short code or None; the sweep skips before any gate call"
  - "ActionRequest.record_suppressed lets one caller record the undo-window refusal that every other caller drops"

requirements-completed: []

coverage:
  - id: D1
    description: "Origins are native, feed:urlhaus, feed:malwarebazaar, feed:otx, virustotal and onhost; two entries of one origin are one origin; the alert a native verdict writes collapses to native and the one a VirusTotal FIM match writes to virustotal"
    requirement: "RESP-08"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_origins.py#test_mirrored_native_alert_adds_no_second_origin"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_origins.py#test_mirrored_virustotal_alert_adds_no_second_origin"
        status: pass
    human_judgment: false
  - id: D2
    description: "Tenant-added IOC rows, deception data, free text and another tenant's rows never count; a feed row for a thing no host has makes no candidate; a hostname shared by two agents is skipped"
    requirement: "RESP-08"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_origins.py#test_one_tenants_rows_never_reach_another_and_a_global_feed_row_serves_both"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_origins.py#test_a_feed_listing_on_no_host_makes_no_candidate"
        status: pass
    human_judgment: false
  - id: D3
    description: "One origin records one suggestion (no instruction); a second origin 23 or 24 hours later, in either order, turns it into the automatic action and the suggestion ends expired/superseded; at 24 hours plus 1 second or later it stays a suggestion"
    requirement: "RESP-08"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_two_signal.py#test_the_second_origin_promotes_inside_24_hours_in_either_order_and_not_after"
        status: pass
    human_judgment: false
  - id: D4
    description: "With response.twoSignal false one origin acts and says so; every other limit still applies; after a block ran out old evidence does not count and two fresh origins decide again; expiry is never an undo"
    requirement: "RESP-08"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_two_signal.py#test_with_the_rule_off_one_origin_acts_and_says_so"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_two_signal.py#test_after_a_block_expires_old_evidence_does_not_count_and_fresh_evidence_from_two_origins_does"
        status: pass
    human_judgment: false
  - id: D5
    description: "Ten ticks over an unchanged finding leave one row for an automatic action, a recorded refusal and a simulation; a tick with no new data changes no document; two racing sweeps leave one open row"
    requirement: "RESP-07"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_sweep_dedupe.py#test_ten_ticks_over_a_recorded_refusal_leave_one_refused_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_sweep_dedupe.py#test_two_sweeps_racing_on_one_finding_leave_one_open_row_and_one_instruction"
        status: pass
    human_judgment: false
  - id: D6
    description: "Denied and expired cards wait 24 hours, failed rows 1 hour, refused rows 24 hours unless a new origin arrives; inside 24 hours of an undo exactly one refused row names the undo date and sends nothing; an undo exactly 24 hours old no longer suppresses"
    requirement: "RESP-07"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_sweep_dedupe.py#test_an_undo_exactly_24_hours_old_no_longer_suppresses_and_one_second_younger_does"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_sweep_dedupe.py#test_skip_reason_holds_a_decision_for_its_window"
        status: pass
    human_judgment: false
  - id: D7
    description: "The fourth automatic block or quarantine on one computer in a rolling hour becomes an approval card; a row exactly 1 hour old and a restart row do not count"
    requirement: "RESP-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_sweep_dedupe.py#test_the_per_computer_cap_counts_blocks_and_quarantines_in_a_rolling_hour"
        status: pass
    human_judgment: false
  - id: D8
    description: "ABUSE_CH_AUTH_KEY travels only as an Auth-Key header on the two abuse.ch calls, is never logged and changes nothing when unset; two feeds listing one indicator keep both names; migration 028 creates only the four indexes"
    requirement: "RESP-08"
    verification:
      - kind: integration
        ref: "backend/tests/test_threat_feed_sync_origins.py#test_with_the_key_set_both_abuse_ch_calls_carry_it_as_a_header_and_nothing_logs_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_origins.py#test_migration_028_creates_only_indexes_and_a_second_run_changes_nothing"
        status: pass
    human_judgment: false
  - id: D9
    description: "On a real tenant the platform finds two origins for one address (native verdict plus a live public feed) and the abuse.ch feed returns rows once the key is set"
    requirement: "RESP-08"
    verification: []
    human_judgment: true
    rationale: "No live feed or key in tests (A-83-A2). The live count of feed rows, and the fact that two origins on this platform will mostly mean native plus a public feed because onhost has no writer today (A-83-ONHOST), are UAT items."

duration: 95min
completed: 2026-11-01
status: complete
---

# Phase 83 Plan 05: Origins, two-source rule, feed key, decision memory, per-host cap Summary

**The sweep now reads every origin honestly (a mirrored alert never makes a second one), records one suggestion for one source and promotes it to the automatic block only when a second different source arrives within 24 hours, honours the tenant's switch, and never decides the same finding twice: ten ticks leave one row, an undone action is refused once and left alone for exactly 24 hours, and one computer is capped at three automatic block or quarantine actions an hour.**

## Performance

- **Duration:** about 95 min
- **Tasks:** 3 (all TDD)
- **Commits:** 7 (3 test, 3 feat, 1 refactor), measured from `6c861a541` to `fda46a1c5`
- **Files:** 14 changed (6 created, 8 modified), 1,829 insertions, 155 deletions

## Accomplishments

### Final origin table (which readers have a live writer today)

| Origin | Read from | Live writer today |
|--------|-----------|-------------------|
| `native` | `security_scan_results` (source native, Malicious; ip, url with an IP-literal host, file, hash) and the `security_alerts` row it mirrors (`source: native`) | yes: `ingest_scan_result`, but only when an operator or the scan skill asks for a scan (A-83-SCAN) |
| `feed:urlhaus`, `feed:malwarebazaar`, `feed:otx` | global `edr_ioc` rows (tenantId absent), for something a host of this tenant HAS (process sha256, file-change hash, connection address, native verdict) | yes: `threat_feed_sync`; abuse.ch rows need `ABUSE_CH_AUTH_KEY` (A-83-A2), OTX needs `OTX_API_KEY` |
| `virustotal` | `security_alerts` with `vt_detection_ratio` (the alert a VirusTotal FIM match writes) | yes: `agent_security_endpoints._raise_malware_alert` |
| `onhost` | any other `security_alerts` row with a 64-hex `sha256` | no: the two writers of a sha256 alert are the native and VirusTotal mirrors (A-83-ONHOST). On this platform two origins will mostly mean native plus a public feed. |

Telemetry that binds a thing to a host but is never an origin: `agents.meta.process_monitor.processes[].sha256/exe`, `agents.meta.runtime_security.connections[].remote_address` (host:port and [v6]:port parsed, anything else skipped), `fim_events.hash_after/sha256/path`.

### What was built

- **`signals.py` (499 lines):** `alert_origin`, `feed_origins` (48-hour freshness per feed), `observe` (returns the candidates as an `Observed` list with `.new_evidence`, at most 500 candidates in sorted (agentId, kind, indicator) order; writes nothing when the merge would change nothing; first sightings never move), `counting_origins`, `corroborated(..., evidence_after=)`, `ensure_indexes` (unique, 30-day TTL on a top-level `lastSeenAt`, two `edr_ioc` lookups). Candidate kinds: `ip`, `file` (sha256), `range` (a feed CIDR a host talks into).
- **`sweep_security.py`:** suggestion path (`gate.suggest`, key `{tenant}|sweep-suggest|block_ip|{agent}|{ip}`, `reason.inputs` `{suggestionOnly, origins, indicator, twoSignal, suggestion: {kind: single_signal}}`), action path (`gate.decide`, key `{tenant}|sweep|...`, `ruleId sweep:block_ip`), supersede, keep-alive, dormant hosts silent, memory skip, undo window, per-host cap.
- **`sweep_memory.py`:** `WINDOWS`, `latest_state`, `block_window`, `skip_reason`.
- **`threat_feed_sync.py`:** `_abuse_headers()`, `$addToSet source_feeds`, `feed_seen.<feed>` timestamps.
- **`migration 028`:** indexes only.
- **Gate:** `ActionRequest.record_suppressed`; `ledger.open_row`, `refresh_suggestion`, `latest_undone`, `count_host_auto_since`.

## Task Commits

| Task | Commit | Type |
|------|--------|------|
| 1 RED: origins, feed sync, migration | `755e7eaa0` | test |
| 1 Every origin read honestly, feeds keep their names | `e9a424e80` | feat |
| 2 RED: suggestion, promotion, switch | `2952717d1` | test |
| 2 One origin suggests, a second within 24 hours acts | `d7748f199` | feat |
| 3 RED: memory, undo window, per-host cap | `ae7f24046` | test |
| 3 Nothing repeats | `8d87c7672` | feat |
| Unused import | `fda46a1c5` | refactor |

## Verification Results

Run with the private mongod on 27998 (`MONGO_TEST_URL`, `MONGODB_URL`, `MONGO_URI`), `-p no:cacheprovider -rs`, no skips anywhere:

- Task 1 command (origins, feed sync): 64 passed.
- Task 2 command (origins, sweep, block contract) plus the new two-signal file: 161 passed.
- Task 3 command (sweep dedupe, gate order, gate): 90 passed.
- Structural and copy (banned terms): 53 passed.
- Wider regression, every other `test_autonomous_ops_*.py` plus `test_autonomous_remediation_loop.py`: 358 passed, no skips. `test_agentless_features.py` (imports `threat_feed_sync`): passed. The full backend suite was not run (run notes). `test_catalogue_route_parity.py` was not run (no route changed).
- Acceptance: `ABUSE_CH_AUTH_KEY` appears 4 times in `threat_feed_sync.py` and in no logger line (a test scans every `logger.` line); `deception_alerts` appears 0 times in `signals.py`; `signals.py` 499 lines, `gate.py` 448, `sweep_security.py` 230, `sweep_memory.py` 70; `refresh_suggestion` appears once in `ledger.py`; `superseded` appears in `sweep_security.py`; `record_suppressed` appears 3 times in `gate.py`; the ten-tick tests assert one row in `autonomy_actions` for an automatic action, a protected-target refusal and a tenant in shadow; the 24-hour cases cover exactly 24 hours, 24 hours plus 1 second and both arrival orders.
- No test touched the real firewall, a real agent or the live mongod.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Per-feed listing times (`feed_seen`)**
- **Found during:** Task 1 design of `feed_origins`
- **Issue:** with only `source_feeds` and the row's `updated_at`, a feed that stopped listing an indicator would keep counting as an origin for as long as another feed kept refreshing the row (a stale origin satisfies the two-source rule, T-83-16).
- **Fix:** the sync also sets `feed_seen.<feed>` on every upsert; the reader uses it per feed and falls back to `updated_at` only for a name with no stamp.
- **Files modified:** `backend/threat_feed_sync.py`, `backend/autonomous_ops/signals.py`
- **Commit:** `e9a424e80`

**2. [Rule 1 - Bug] `corroborated` compared the first with the LAST sighting**
- **Found during:** Task 2
- **Issue:** the 83-01 rule (`firsts[-1] - firsts[0] <= 24 h`) refused a real pair (A at 0 h, B at 1 h) when a third origin arrived at 30 h. The plan says any two different origins within 24 hours agree.
- **Fix:** any adjacent pair of first sightings within 24 hours (inclusive); the row names the origins of that cluster.
- **Files modified:** `backend/autonomous_ops/signals.py`, `backend/autonomous_ops/sweep_security.py`
- **Commit:** `d7748f199`

**3. [Rule 3 - Blocking] Three 83-01 tests asserted the behaviour this plan replaces**
- **Found during:** Tasks 2 and 3
- **Issue:** `test_only_one_origin_produces_no_block` and `test_two_origins_more_than_a_day_apart_do_not_corroborate` expected no row at all (now: one suggestion row, still no instruction); `test_after_an_undo_ticks_inside_a_day_add_no_instruction` expected one row (now: the undone row plus exactly one refused row).
- **Fix:** updated those three expectations, keeping the no-instruction assertions.
- **Files modified:** `backend/tests/test_autonomous_ops_block_contract.py`
- **Commits:** `d7748f199`, `8d87c7672`

### Plan departures that are choices, not fixes

- **Task 2 tests live in a new file** `backend/tests/test_autonomous_ops_two_signal.py`, not in `test_autonomous_ops_origins.py`, to keep both under 500 lines. The Task 2 verify command still runs the origins file; the new file is additional.
- **`skip_reason(decision, row, origins, now)`** takes the ledger row (from `latest_state`) instead of a state string, so a failed row's 1-hour window can start at its `finishedAt`. `latest_state` returns the row.
- **`ledger.open_row`** is an extra helper (find the open row for a dedupe key); `signals.remember` also keeps `origins` and `holdUntil`.
- **Suggestions are not remembered** (see key-decisions). Their own open row, the gate's duplicate answer and `_keep_alive` stop them repeating.
- **A suggestion records only the earliest origin** in `inputs.origins` when two origins exist but not inside the window, so the existing Why wording ("Only one source flagged this: X") stays true.
- **Keep-alive writes only when needed:** the suggestion is refreshed when its origins changed or less than half its 24 hours remains, so a tick that learned nothing changes no row.
- File candidates: a single-origin file with a path gets a `quarantine_file` suggestion (params `{path, sha256}`); a corroborated file does nothing until 83-11. Range candidates are observed and recorded, never decided (83-08).
- `tests/autonomy_support.py` carries a docstring that says only 81-08 and 81-15 may extend it; this plan lists it in `files_modified`, so it was extended (`seed_alert`, `seed_fim_event`, `seed_telemetry`, extra keywords on `seed_feed_ioc`). The docstring was not changed.

### TDD evidence (honest)

- **Order bent once:** `signals.py` was drafted before its tests. To get a real RED I put the committed `signals.py` back, wrote the tests against it, ran them, committed the RED, then restored the draft.
- **Task 1 RED:** 51 failed, 13 passed. Most failures are missing names (`AttributeError` on `alert_origin`, `ORIGIN_IDS`, `_abuse_headers`, `remote_host`, `counting_origins`; `ImportError` for migration 028), plus feed-sync tests that failed on the old behaviour. The 13 passes are negative cases the old code also satisfied.
- **Task 2 RED:** 15 failed, 6 passed, all on behaviour (the old sweep never suggested and acted on two origins only); no import error.
- **Task 3 RED:** 31 failed, 10 passed: the 16 `skip_reason` table cases failed on `ImportError` (`sweep_memory` did not exist); the tick scenarios failed on behaviour. No `gsd_run check tdd-red-evidence` record was produced.

### Wording

One user-visible sentence is not in the UI-SPEC: `WHY_TEMPLATES["host_cap"]` in `response_messages.py`: "This computer already had 3 automatic actions in the last hour, so this one needs your approval." Please read it. Every other sentence the sweep writes is an existing `response_messages` text (`why_one_source`, `why_two_sources`, `why_rule_off`, `undone_earlier`, `superseded`).

### Files not read in full

`83-CONTEXT.md`, `83-PATTERNS.md`, `83-03-SUMMARY.md` and `.planning/PROJECT.md` were not read; `83-RESEARCH.md` was read only for Pattern 3, Pitfalls 1 and 2 and the R2 row; `STATE.md` only the frontmatter and the tail; `runtime_security.rs` and `process_monitor.rs` only around the output field names; `agent_heartbeat_endpoints.py` only the `meta` storage and the runtime-security block.

## Known Limitations (carried forward, not stubs)

- A signal is acted on only in a tick that observes it: once its native verdict is older than 25 hours and nothing else binds the thing to the host, it drops out of consideration even though its document is kept for 30 days.
- A failed row (including `verify_failed`) is now retried after 1 hour; 83-01 held it until `blockedUntil`.
- `onhost` has no live writer (A-83-ONHOST); live abuse.ch rows need the key (A-83-A2).
- No scan is scheduled in this phase (A-83-SCAN), so a native verdict exists only when someone asks for one.

## Threat Flags

None beyond the plan's threat model. The new reads (`security_alerts`, `fim_events`, `edr_ioc`) all filter by tenantId or by tenantId-absent; the only new outbound surface is the `Auth-Key` header to the two abuse.ch URLs already called.

## Requirements

`RESP-01`, `RESP-07`, `RESP-08` are NOT ticked: each spans later plans (RESP-08's tenant and Super Admin write path is 83-07; RESP-07 also covers the aggregate suggestions and restarts; RESP-01 the file, vulnerability and file-change stages). The orchestrator ticks them at the phase gate.

## Self-Check: PASSED

- Files found: `signals.py`, `sweep_security.py`, `sweep_memory.py`, `ledger.py`, `gate.py`, `response_messages.py`, `threat_feed_sync.py`, `migrations/028_security_response.py`, `tests/autonomy_support.py`, `tests/test_autonomous_ops_origins.py`, `tests/test_autonomous_ops_two_signal.py`, `tests/test_autonomous_ops_sweep_dedupe.py`, `tests/test_threat_feed_sync_origins.py`.
- Commits found in HEAD: `755e7eaa0`, `e9a424e80`, `2952717d1`, `d7748f199`, `ae7f24046`, `8d87c7672`, `fda46a1c5`.
