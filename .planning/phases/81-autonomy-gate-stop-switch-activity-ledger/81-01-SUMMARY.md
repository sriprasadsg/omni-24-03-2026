---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 01
subsystem: autonomous-ops
tags: [gate, registry, ledger, audit-mirror, mongo, shadow-mode, pytest]

requires:
  - phase: 75-permission-resolver-single-source-of-truth
    provides: tenant enabledFeatures tick model that eligibility reads literally
provides:
  - "backend/autonomous_ops package: constants, scope, registry, settings, ledger, gate"
  - "gate.decide: ordered GATE-03 step function with eligibility, class and shadow steps live and a write-ahead intent row"
  - "gate.execute / gate.execute_response_task: the only stamped instruction and response-task writers"
  - "registry.playbook_raises (gate_class key) pinned against the shipped playbooks"
  - "tests/autonomy_support.py: seed_tenant, seed_agent, seed_platform_stop, FakeLedger, permissive_gate"
affects: [81-02, 81-04, 81-05, 81-06, 81-08, 81-09, 81-11, 81-12]

actuals:
  tokens: 20500
  tasks: 3
  commits: 3

plan_head_before: 3d1c262185d90eef8babfe3691663c80d31cca2a
plan_head_after: 49fb0b8724a2e09a8cd44c7fe3a125c73bae0e22
commits: 3

tech-stack:
  added: []
  patterns:
    - "Raw Mongo handle plus explicit tenantId on every filter and document; the tenant ContextVar is never read"
    - "Write-ahead decision row, then awaited audit_ledger.event mirror; a failed insert refuses the decision"
    - "Compare-and-set transition via find_one_and_update with a state filter; None means the caller lost"
    - "Decision as an ordered tuple of named async steps appending {check, result, code} to a trace"

key-files:
  created:
    - backend/autonomous_ops/__init__.py
    - backend/autonomous_ops/scope.py
    - backend/autonomous_ops/registry.py
    - backend/autonomous_ops/settings.py
    - backend/autonomous_ops/ledger.py
    - backend/autonomous_ops/gate.py
    - backend/tests/autonomy_support.py
    - backend/tests/test_autonomous_ops_gate.py
    - backend/tests/test_autonomous_ops_registry.py
    - backend/tests/test_autonomous_ops_ledger.py
  modified: []

key-decisions:
  - "GATE-04 raise is the explicit per-step key gate_class, never destructive (every vendored step except patch_package sets destructive, block_ip included); no shipped YAML sets gate_class, so every vendored path keeps its registry class"
  - "Level, maximum level and shadow are read on every call (no in-process cache): one find_one each, nothing to invalidate"
  - "Unreadable tenant read yields eligible True and readable False so the tenant is Suggest, not Off (D-23 fail closed); an unreadable stored value (bad level, non-bool shadow) also sets readable False"
  - "A duplicate open dedupeKey (DuplicateKeyError from the open_dedupe partial unique index) is refused duplicate and not recorded; ledger.create_intent re-raises it rather than calling it LedgerUnavailable"
  - "The shadow wrapper covers allow_auto, needs_approval and suggest (any outcome that would dispatch or create a card); shadow rows carry no approval expiry and autoDispatched False"

patterns-established:
  - "Gate callers build an ActionRequest and branch on Decision.outcome; execute/execute_response_task re-read the row per kind"
  - "Tests seed through tests/autonomy_support.py; legacy MagicMock tests use permissive_gate"

requirements-completed: [GATE-02, GATE-03, GATE-04, GATE-07, GATE-09]

coverage:
  - id: D1
    description: "Eligible tenant's block_ip request is decided once, written ahead to autonomy_actions as a shadow simulation, mirrored to the audit chain (chain valid) and listed under the simulation bucket; nothing dispatched"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate.py#test_tracer_shadow_decision_is_written_ahead_and_listed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Unticked tenant and platform-admin are Off: refused not_enabled / platform_tenant with no row and no audit event"
    requirement: GATE-02
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate.py#test_unticked_tenant_is_off_and_unrecorded"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate.py#test_platform_tenant_is_always_off"
        status: pass
    human_judgment: false
  - id: D3
    description: "Locked auto/approve split, aliases, ACTION_MAP coverage, immutability, raise-never-lower and the shipped-playbook path (block_ip stays auto)"
    requirement: GATE-04
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_registry.py (6 tests)"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate.py#test_class_step_escalates_approve_actions_and_refuses_unregistered"
        status: pass
    human_judgment: false
  - id: D4
    description: "Write-ahead: a failing insert refuses ledger_unavailable and writes no instruction or response task; one winner per concurrent transition with one audit event; intent event precedes dispatch"
    requirement: GATE-07
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate.py#test_a_ledger_that_cannot_be_written_refuses_the_decision"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_ledger.py#test_concurrent_transitions_have_one_winner_and_one_audit_event"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_ledger.py#test_intent_event_precedes_the_dispatch_and_the_chain_verifies"
        status: pass
    human_judgment: false
  - id: D5
    description: "gate.execute and execute_response_task are the only stamped writers; refuse non-dispatchable rows, unknown rows, other tenants, and a stop (undo/compensate exempt)"
    requirement: GATE-07
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_ledger.py#test_execute_writes_one_stamped_instruction_and_links_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_ledger.py#test_a_stop_holds_back_actions_and_probes_but_not_undo_or_compensate"
        status: pass
    human_judgment: false
  - id: D6
    description: "Shadow wrapper: master flag or tenant flag turns a would-dispatch outcome into a shadow row with wouldHave and no instruction"
    requirement: GATE-09
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate.py#test_tracer_shadow_decision_is_written_ahead_and_listed"
        status: pass
    human_judgment: false
  - id: D7
    description: "Decision collections sit outside retention_service, retention_endpoints and audit_ledger.purge_expired; floor is 365 days; paging is stable; empty tenant lists and counts are zero"
    requirement: GATE-07
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_ledger.py#test_decision_records_sit_outside_every_retention_path"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_ledger.py#test_rows_sharing_a_created_at_page_in_a_stable_order"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 01: Gate, registry and decision ledger core Summary

**New `backend/autonomous_ops` package: a write-ahead decision ledger with compare-and-set transitions and an awaited audit mirror, a code-owned action registry whose GATE-04 raise is the explicit `gate_class` step key, and an ordered-step `gate.decide` (eligibility, class and shadow live) with the only stamped instruction writers**

## Performance

- **Duration:** 12 min
- **Started:** 2026-10-26T07:28:53Z
- **Completed:** 2026-10-26T07:41Z
- **Tasks:** 3
- **Files modified:** 10 created, 0 modified

## Accomplishments

- An eligible tenant's `block_ip` request is decided once, recorded as a shadow row before anything else, mirrored into the hash chain (verified valid) and listed under the simulation bucket. An unticked tenant, and `platform-admin`, are Off and leave no row, no audit event.
- `registry.ACTIONS` is a read-only `MappingProxyType`; the locked split holds (block_ip, quarantine_file, restart_service auto; isolate_host, kill_process, reboot_host, upgrade_software approve). A playbook raises a class only with `gate_class`; the shipped `block_ip` playbook (step carries `destructive: true`) still resolves to auto.
- `ledger.transition` is one `find_one_and_update` with a state filter: two concurrent callers produce one winner and one audit event. A failing insert refuses the decision (`ledger_unavailable`) and no agent document is written.
- `gate.execute` / `gate.execute_response_task` re-read the row per kind (action: approved/dispatching; probe: dispatching/executed; compensate: dispatching/failed; undo: undone), refuse during a platform or tenant stop (undo and compensate exempt, an unreadable stop counts as stopped) and are the only code that writes the `triggered_by: autonomous_ops` stamp.

## Decision steps and reason codes (as implemented here)

| Step (GATE-03 position) | State in 81-01 | Codes |
|---|---|---|
| 1 platform_stop | declared, records `deferred` | 81-11 |
| 2 eligibility | live | `no_tenant`, `platform_tenant`, `not_enabled` (all refuse, unrecorded); `settings_unreadable` (escalate to suggest) |
| 3 tenant_stop | declared, `deferred` | 81-11 |
| 4 level | only caller-forced Suggest (`suggest_requested`); stored level handling `deferred` | 81-11 |
| 5 class | live | `unregistered_action` (refuse, recorded), `class_approve`, `playbook_raised` (needs_approval), `class_auto` |
| 6 protected_targets | declared, `deferred` | 81-11 |
| 7 blast_radius | declared, `deferred` | 81-11 |
| 8 dedupe | declared, `deferred`; open duplicates are caught at insert by the `open_dedupe` index | `duplicate` (refuse, unrecorded) |
| 9 shadow wrapper | live | trace `shadow` with source `deployment` or `tenant` |
| write-ahead | live | `ledger_unavailable` |

81-11 fills steps 1, 3, 4, 6, 7, 8 in the `_STEPS` tuple of `gate.py` without reshaping `decide`.

## Row-state map

| Outcome | Row state | Notes |
|---|---|---|
| allow_auto | `dispatching` | `autoDispatched` True |
| needs_approval | `awaiting_approval` | `approval.expiresAt = createdAt + APPROVAL_TTL` (24 h) |
| suggest | `suggested` | same expiry |
| refuse (tenant recorded) | `refused` | `reasonCode` set |
| any of the three, shadow on | `shadow` | `wouldHave` = underlying outcome, no expiry, `autoDispatched` False |

## Registry class table (shipped playbooks resolve to)

| Playbook | Action | Registry class | `playbook_raises` |
|---|---|---|---|
| block_ip | block_ip | auto | False (destructive true is ignored) |
| kill_process | kill_process | approve | False |
| patch_package | upgrade_software (alias) | approve | False |
| restore_file | restore_file | approve | False |
| disable_service | disable_service | approve | False |
| rotate_key | rotate_key | approve | False |

Other auto: quarantine_file, restart_service. Other approve: isolate_host (alias isolate_endpoint), reboot_host, rollback_ransomware. Undo-only: unblock_ip, enable_service, unquarantine_file, restore_host, rotate_key_rollback. Probes: scan_file, scan_ip, scan_url, scan_hash.

## Task Commits

1. **Task 1: Tracer - decide, write ahead, mirror, list** - `ac1e633b9` (feat)
2. **Task 2: GATE-04 pinned (gate_class raise)** - `8c101bf9b` (feat)
3. **Task 3: transitions, stamped writers, shared fixtures** - `49fb0b872` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

Single commit per task (the plan is `type: execute`, not `type: tdd`). RED was confirmed by running each test module before its implementation existed (Task 2: 2 failed on the missing `GATE_CLASS_KEY`/`playbook_raises`); Task 3's ledger functions had been written during Task 1 so its tests passed on first run.

## Files Created/Modified

- `backend/autonomous_ops/__init__.py` - levels, permissions, limits, states, buckets, `PROTECTED_COLLECTIONS`, `STAMP_SOURCE`
- `backend/autonomous_ops/scope.py` - `raw(db)`, `tenant_scope(tenant_id)`
- `backend/autonomous_ops/registry.py` - action table, aliases, `resolve`, `playbook_raises`, `effective_class`, `commands`
- `backend/autonomous_ops/settings.py` - `TenantSettings`, `load`, `effective_level`, master/tenant shadow, platform stop, setters, `ensure_*`
- `backend/autonomous_ops/ledger.py` - `create_intent`, `transition`, `record_control`, `get`, `list_actions`, `counts`, `count_auto_since`, `recent_finished_auto`, `ensure_indexes`
- `backend/autonomous_ops/gate.py` - `ActionRequest`, `Decision`, `decide`, `suggest`, `execute`, `execute_response_task`
- `backend/tests/autonomy_support.py` - shared fixtures
- `backend/tests/test_autonomous_ops_gate.py`, `test_autonomous_ops_registry.py`, `test_autonomous_ops_ledger.py`

## Decisions Made

See `key-decisions` above. In short: `gate_class` (not `destructive`) is the raise, per the locked split; no settings cache; unreadable data is Suggest; duplicates are refused unrecorded; the shadow wrapper covers suggest as well as dispatch and approval cards.

## Deviations from Plan

None - plan executed exactly as written. Two small additions inside the plan's scope: `decide` also refuses an empty or non-string tenant id as `no_tenant` (unrecorded) because settings cannot be loaded without one (81-11 lists the same code), and `settings.stop_active()` was added as a tiny helper so callers test `stop.active is True` in one place.

**Total deviations:** 0 auto-fixed.

## Issues Encountered

- A dataclass field named `settings` shadowed the `settings` module inside `_Ctx` (import-time AttributeError on first test run); renamed the field to `tenant`. No behaviour change.
- Motor returns naive datetimes from a default client; the ledger normalizes datetimes to timezone-aware UTC on every read, so consumers can compare with aware `now` values.

## Known Stubs

The six steps listed as `deferred` in `gate.py` (`_step_platform_stop`, `_step_tenant_stop`, stored-level part of `_step_level`, `_step_protected_targets`, `_step_blast_radius`, `_step_dedupe`) are intentional placeholders owned by plan 81-11 (same wave-2 dependency chain; nothing calls the gate before 81-11 completes: 81-04, 81-05, 81-06, 81-08, 81-09 all depend on it). Not recorded in WINDOWS.md as defects because 81-11's must-haves cover each one.

## Notes for later plans

- ACTV-08: the registry's command names `rollback_ransomware` and `rotate_key_rollback` contain the word rollback. They are agent instruction identifiers, not user-visible text; the scan of `messages.py` (81-10/81-11) must keep labels qualified ("rollback where supported").
- Indexes (`ledger.ensure_indexes`, `settings.ensure_indexes`) are not created lazily; migration 024 / startup (81-04) must call them. Tests call `ledger.ensure_indexes` themselves.
- `ledger.create_intent` re-raises `pymongo.errors.DuplicateKeyError`; any caller other than `gate.decide` must handle it.

## User Setup Required

None - no external service configuration required. Nothing was deployed, no service restarted, no live database touched (all tests use the throwaway `omni_test_*` database).

## Threat Flags

None. The package adds no network endpoint, auth path or schema at a trust boundary beyond the plan's threat model; T-81-01, T-81-03, T-81-04 mitigations are implemented and tested (T-81-05 cross-tenant target check is part of 81-11).

## Next Phase Readiness

- 81-11 can fill the deferred steps in `_STEPS` and add `protected.py`, `messages.py`, `notify.py`; 81-02/81-03 are independent.
- Verification run: `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_gate.py backend/tests/test_autonomous_ops_registry.py backend/tests/test_autonomous_ops_ledger.py backend/tests/test_audit_ledger.py -q -p no:cacheprovider` -> 46 passed, 0 skipped.

## Self-Check: PASSED

All 10 created files exist; commits ac1e633b9, 8c101bf9b, 49fb0b872 are ancestors of HEAD; task acceptance criteria re-run and pass; vendored playbooks and loader unchanged (`git status --porcelain` empty for them).

---
*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Completed: 2026-10-26*
