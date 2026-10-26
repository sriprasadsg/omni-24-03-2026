---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 11
subsystem: autonomous-ops
tags: [gate, never-touch, protected-targets, rate-limit, dedupe, shadow-mode, messages, pytest]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-01)
    provides: gate.decide step tuple with six deferred steps, registry, settings, ledger, autonomy_support fixtures
provides:
  - "backend/autonomous_ops/protected.py: built-in (computed) and stored never-touch entries, strict ipaddress matching, check()"
  - "backend/autonomous_ops/messages.py: ACTION_LABELS, REASON_TEXT, CLASS_LINES, CONTROL_LABELS, PLATFORM_ADMIN_DISPLAY, NOTICES, simulation_result"
  - "backend/autonomous_ops/notify.py: never-raising in-app notice to the platform feed and the tenant's admins"
  - "gate.decide with the complete GATE-03 order and gate.REASON_CODES (22 codes)"
affects: [81-04, 81-05, 81-06, 81-08, 81-09, 81-10, 81-12]

actuals:
  tokens: 19500
  tasks: 2
  commits: 2

plan_head_before: c0c7031122f08b784b444669f1a32b4bf3803615
plan_head_after: 1b4b24574adb2039b76ea6b0d1ef916aeadacfff
commits: 2

tech-stack:
  added: []
  patterns:
    - "Hard refusal short-circuits the step tuple; soft escalations accumulate and the strongest wins, ties keep the first"
    - "A row is recorded unless the tenant is Off (unticked, platform-admin, level off, duplicate, suppressed, ledger down)"
    - "Built-in never-touch entries computed in code and cached 60 s per database; stored entries read on every call"
    - "Independent oracle in the test for an exhaustive itertools.product enumeration"

key-files:
  created:
    - backend/autonomous_ops/protected.py
    - backend/autonomous_ops/messages.py
    - backend/autonomous_ops/notify.py
    - backend/tests/test_autonomous_ops_protected.py
    - backend/tests/test_autonomous_ops_gate_order.py
  modified:
    - backend/autonomous_ops/gate.py
    - backend/tests/test_autonomous_ops_gate.py

key-decisions:
  - "Targets are checked as agents (id, hostname, recorded address) for every action, and every ip_params value is checked as an address; the management subnet therefore also protects agents that sit on it"
  - "Refusals for an Off tenant (not_enabled, platform_tenant, level_off, no_tenant) and for duplicate / suppressed_by_undo / ledger_unavailable are not recorded; every other refusal is recorded as state refused, including platform_stop and tenant_stop for a tenant above Off"
  - "The rate limit is only evaluated when the outcome is still allow_auto, so an approval-class request never sends a rate-limit notice"
  - "Unreadable inputs fail closed: unreadable platform stop = stopped, unreadable agent or never-touch list = refuse, unreadable rate-limit count = hold for approval"
  - "Reason text for refused and escalated rows is messages.REASON_TEXT[code]; only an allow_auto row keeps the caller's own reason_text"

patterns-established:
  - "Enumeration test: seed one tenant per (eligibility, level, stop, shadow-flag) once, then iterate decisions and clear the ledger between combinations"

requirements-completed: [GATE-02, GATE-03, GATE-04, GATE-08, GATE-09]

coverage:
  - id: D1
    description: "A block_ip aimed at the backend's own address, an interface subnet, a configured platform host or a platform-admin agent address is refused protected_target at every level (including Suggest) with a recorded plain-words reason and no instruction"
    requirement: GATE-08
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate.py#test_tracer_own_address_is_refused_protected_target_at_every_level"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate.py#test_platform_agent_address_other_tenant_target_and_empty_targets_are_refused"
        status: pass
    human_judgment: false
  - id: D2
    description: "Never-touch built-ins cannot be removed; subnet first and last addresses and IPv4-mapped forms are protected, the first address outside is not; unparsable or leading-zero IPs are invalid_target; a stored entry applies to the next check; 501st entry refused"
    requirement: GATE-08
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_protected.py (21 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Exhaustive 6480-combination table (platform stop x eligibility x tenant stop x level x class x protected x targets x shadow) equals an independent oracle; no instruction is ever written; Off tenants leave no row or audit event; destructive-only equals plain auto; master shadow only turns a dispatching outcome into a simulation"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate.py#test_every_combination_of_inputs_matches_the_oracle"
        status: pass
    human_judgment: false
  - id: D4
    description: "Shipped block_ip playbook stays allow_auto/dispatching through decide; a gate_class approve step raises it to needs_approval playbook_raised"
    requirement: GATE-04
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate.py#test_vendored_block_ip_playbook_stays_automatic_through_decide"
        status: pass
    human_judgment: false
  - id: D5
    description: "Host cap (1 passes, 2 escalate, 0 refuse), rolling-hour rate limit (20th allowed, 21st held, 60-minute-old row out) with one notice per window"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate_order.py#test_host_cap_one_target_passes_two_escalate_zero_refuse"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate_order.py#test_twentieth_automatic_action_in_the_hour_is_allowed_the_twenty_first_waits"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate_order.py#test_rate_limit_notice_is_sent_once_per_window"
        status: pass
    human_judgment: false
  - id: D6
    description: "Dedupe, 24 h shadow cooldown, undo suppression and the open_dedupe index race are refused without a new row; empty inputs, ordering, timestamp precision and unreadable settings (Suggest) behave as specified"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_gate_order.py (21 tests)"
        status: pass
    human_judgment: false
  - id: D7
    description: "messages.py covers every reason code and registry command, and contains no banned term"
    requirement: GATE-03
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_gate.py#test_messages_cover_every_reason_code_and_every_registry_command"
        status: pass
    human_judgment: false

duration: 33min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 11: Never-touch list and the complete GATE-03 decision order Summary

**`gate.decide` now applies the whole GATE-03 order (platform stop, eligibility, tenant stop, level, class, protected targets, host cap and rolling-hour rate limit, dedupe/cooldown/undo suppression, shadow wrapper), backed by a computed-plus-stored never-touch list, a plain-words `messages.py` and a never-raising `notify`, pinned by a 6480-combination table against an independent oracle**

## Performance

- **Duration:** about 33 min (started 08:07 UTC, last task commit 08:40 UTC)
- **Tasks:** 2 (tracer + expansion)
- **Files:** 5 created, 2 modified; 1308 insertions across the plan's commits

## Accomplishments

- A `block_ip` aimed at this host's own address (`10.0.0.4` on this VM), an interface subnet, the host named by `PLATFORM_URL`/`BACKEND_HOST`/`BACKEND_WS_HOST`, or a platform-admin agent is refused `protected_target` even at Suggest, recorded with the plain-words reason, and no instruction is written. Unparsable or leading-zero IPs are `invalid_target`; IPv4-mapped IPv6 forms are unwrapped; no DNS lookups.
- A target that is not an enrolled agent of the request's tenant is `cross_tenant_target`; an empty list is `no_target`; more than one distinct target is `needs_approval blast_radius` (D-17).
- The 21st automatic action inside a rolling 60 minutes becomes `needs_approval rate_limit` (D-20); shadow rows, control rows and a row exactly 60 minutes old do not count. The notice goes out once per window through the `rateLimitNotifiedAt` marker.
- Dedupe: an open twin, a shadow row younger than 24 h (cooldown) and an undone row younger than 24 h (`suppressed_by_undo`) are refused without recording; the `open_dedupe` index still catches a race.
- The shipped `block_ip` playbook (step carries `destructive: true`) stays `allow_auto`/`dispatching`; a `gate_class: approve` step raises it to `playbook_raised`.

## Final decision-order table

| # | Step | Hard refusal (reason code, recorded?) | Soft escalation |
|---|------|---------------------------------------|-----------------|
| 1 | platform_stop | `platform_stop` (recorded when the tenant is above Off; an unreadable stop counts as stopped) | |
| 2 | eligibility | `no_tenant`, `platform_tenant`, `not_enabled` (never recorded) | `settings_unreadable` -> suggest |
| 3 | tenant_stop | `tenant_stop` (recorded above Off) | |
| 4 | level | `level_off` (never recorded) | `level_suggest`, `suggest_requested` -> suggest |
| 5 | class | `unregistered_action` (recorded) | `class_approve`, `playbook_raised` -> needs_approval |
| 6 | protected_targets | `no_target`, `cross_tenant_target`, `protected_target`, `invalid_target` (recorded) | |
| 7 | blast_radius | | `blast_radius`, `rate_limit` -> needs_approval |
| 8 | dedupe | `duplicate`, `suppressed_by_undo` (never recorded) | |
| 9 | shadow | | any dispatching, card or suggest outcome becomes state `shadow` with `wouldHave` |
| - | write-ahead | `ledger_unavailable` (never recorded) | |

The other codes in `REASON_CODES` are `class_auto` (plain allow_auto). 22 codes in all; `messages.REASON_TEXT` has a plain-words entry for each.

## Enumerated combinations

6480 (3 platform-stop states x 5 eligibility kinds x 2 tenant-stop x 3 levels x 4 classes x 2 protected x 3 target counts x 3 shadow modes), run in about 33 s. Five hand mutations of `gate.py` (level_off ignored, tenant stop ignored, host cap raised, unreadable platform stop treated as running, protected check skipped) each failed the table; four further mutations (rate limit `>` for `>=`, shadow cooldown removed, notice every time, eligibility before platform stop) each failed the edge tests. All reverted.

## Class each vendored playbook resolves to through `decide`

(Eligible tenant, level Undoable-auto, both shadow layers off, one unprotected target.)

| Playbook | Outcome | State | Code |
|----------|---------|-------|------|
| block_ip | allow_auto | dispatching | class_auto |
| disable_service | needs_approval | awaiting_approval | class_approve |
| kill_process | needs_approval | awaiting_approval | class_approve |
| patch_package | needs_approval | awaiting_approval | class_approve |
| restore_file | needs_approval | awaiting_approval | class_approve |
| rotate_key | needs_approval | awaiting_approval | class_approve |

## Built-in never-touch entries computed on this VM (addresses only)

Computed against an empty throwaway database, so platform-admin agent entries (read from the live agents collection at run time) are not listed:

- Special ranges: `127.0.0.0/8`, `::1/128`, `169.254.0.0/16`, `fe80::/10`, `0.0.0.0/32`, `::/128`, `224.0.0.0/4`, `ff00::/8`
- Interfaces: `10.0.0.4` and subnet `10.0.0.0/24` (eth0), `127.0.0.1`, `::1`, `fe80::20d:3aff:fe1f:c2a9` and `fe80::/64`
- From the process environment (`PLATFORM_URL`/`BACKEND_HOST`/`BACKEND_WS_HOST`, loaded by the backend's dotenv on import): `192.168.10.70`

## Task Commits

1. **Task 1 (tracer): never-touch list, messages, notify and the complete decision order** - `baa4a475c` (feat)
2. **Task 2: enumeration and edge-case tests** - `1b4b24574` (test)

## Files Created/Modified

- `backend/autonomous_ops/protected.py` - Entry, builtin_entries, list_entries, add_entry, remove_entry, check, ensure_indexes, cache_clear (324 lines)
- `backend/autonomous_ops/messages.py` - every user-visible string (98 lines)
- `backend/autonomous_ops/notify.py` - in-app notice via `pending_agents.post_to_recipients` (24 lines)
- `backend/autonomous_ops/gate.py` - all steps live, `REASON_CODES`, reason text from messages (496 lines)
- `backend/tests/test_autonomous_ops_protected.py` (21 tests), `test_autonomous_ops_gate.py` (10 tests, 398 lines), `test_autonomous_ops_gate_order.py` (21 tests)

## Decisions Made

See `key-decisions`. Worth knowing for later plans: the management-subnet rule also covers agents that sit on the backend's own subnet (they can never be an automatic target), and a stop, a Suggest tenant or an unticked screen each short-circuit before any target is read.

## Deviations from Plan

### Auto-fixed / judgement calls

**1. [Plan deviation - process] Implementation written before the new tests**
- **Found during:** Task 1
- **Issue:** The plan asks for tests first and a red run. The gate, protected, messages and notify modules were drafted together, so no red run of the new tests was observed. The 81-01 tests that cover the same module (5) were run green after the change.
- **Fix:** Compensated with mutation checks (nine hand mutations of `gate.py`, each caught by a test, then reverted) instead of a red run.

**2. [Plan deviation - structure] Edge tests live in a second file**
- **Found during:** Task 2
- **Issue:** Putting the enumeration and every edge case into `test_autonomous_ops_gate.py` would pass the 500-line limit in CLAUDE.md.
- **Fix:** The enumeration and vendored block_ip test (which carry the acceptance greps) are in `test_autonomous_ops_gate.py`; rate limit, dedupe, empty, ordering, precision and unreadable-settings tests are in the new `test_autonomous_ops_gate_order.py`. Both are in the plan's verification run only by name; the verify command in the plan does not list the new file, so run it explicitly.

**3. [Commit split] Task 2's commit is test-only**
- `gate.py` and `notify.py` were needed together (gate imports notify), so Task 1's commit holds the complete gate; Task 2 added the tests that pin the remaining steps.

**4. [Rule 1 - existing tests updated] 81-01 tests now seed their target agent**
- **Found during:** Task 1
- **Issue:** With the protected-targets step live, the 81-01 gate tests that targeted agent `a1` without enrolling it are refused `cross_tenant_target`.
- **Fix:** Two 81-01 tests now seed `a1` for tenant `t1`. No assertion changed.

**Total deviations:** 4 (2 process/structure, 1 commit split, 1 test seed). **Impact:** none on behaviour.

## Issues Encountered

- The protected-targets step refuses an unenrolled target before the never-touch check, so a typo'd agent id is `cross_tenant_target`, not `no_target`.
- Refused rows are terminal, so a sweep that keeps asking for a protected target (or during a stop with the level above Off) writes one `refused` row per request. 81-11 follows the plan (refusals for recorded tenants are recorded); a later plan may want to collapse repeated refusals if the Activity list floods.
- A tenant whose tenant document cannot be read has no settings loaded, so its stop flag is not seen; it is Suggest with the tenant shadow default (on), so nothing dispatches. The enumeration oracle encodes this.

## Known Stubs

None. The six deferred steps left by 81-01 (platform stop, tenant stop, stored level, protected targets, blast radius, dedupe) are all live.

## Threat Flags

None. The plan adds the `autonomy_never_touch` collection (named in the plan's artifacts) but no endpoint; the routes that edit it arrive in 81-09. T-81-02, T-81-46 and T-81-47 mitigations are implemented and tested.

## User Setup Required

None for this plan. Nothing was deployed, restarted or migrated, and no live database was touched (tests use throwaway `omni_test_*` databases). For the user, later in the phase: call `protected.ensure_indexes` and `ledger.ensure_indexes` at startup/migration (81-04), and set `PLATFORM_URL`, `BACKEND_HOST` and `BACKEND_WS_HOST` correctly on the live VM, since the management-network protection includes the hosts they name.

## Next Phase Readiness

- 81-04, 81-05, 81-06, 81-08 and 81-09 can now call `gate.decide`; the gate is complete. No caller is wired yet, so the running system is unchanged.
- Verification run: `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_gate.py backend/tests/test_autonomous_ops_gate_order.py backend/tests/test_autonomous_ops_registry.py backend/tests/test_autonomous_ops_protected.py backend/tests/test_autonomous_ops_ledger.py backend/tests/test_audit_ledger.py -q -p no:cacheprovider` -> 93 passed, 0 skipped.

## Self-Check: PASSED

All created files exist on disk, commits `baa4a475c` and `1b4b24574` are ancestors of HEAD, acceptance greps re-run (itertools.product 2, count_auto_since 1, rateLimitNotifiedAt 4, protected.check 2, PLATFORM_ADMIN_DISPLAY 1, hypothesis absent), every module is under 500 lines.

---
*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Completed: 2026-10-26*
