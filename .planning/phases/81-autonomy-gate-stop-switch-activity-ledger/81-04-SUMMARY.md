---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 04
subsystem: autonomous-ops
tags: [approvals, undo, circuit-breaker, reconciler, distributed-lock, tenant-isolation, mongo, pytest]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-01)
    provides: gate.decide / gate.execute, ledger.transition compare-and-set, settings, registry
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-03)
    provides: distributed_lock.lock_with_renewal
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-11)
    provides: protected.check, messages, notify, complete GATE-03 order
provides:
  - "approvals.approve / deny / undo / register_dispatcher / expire_due"
  - "breaker.evaluate / restore (manual-only re-arm)"
  - "reconciler.tick / run_once / reconciler_loop under lock autonomous_ops_reconciler"
  - "app_startup registration of the reconciler and an ensure_all_tenants backstop"
affects: [81-05, 81-06, 81-08, 81-09, 81-12]

actuals:
  tokens: 19800
  tasks: 3
  commits: 3

plan_head_before: d02802d1a52afc178150eceaa84035db26e75abc
plan_head_after: afb65926c873722b4ca4a94c7a0deba725950359
commits: 3

tech-stack:
  added: []
  patterns:
    - "Approve is one compare-and-set with the expiry in the filter; the loser reads already_handled"
    - "Breaker trip and restore are conditional update_one on the settings document (modified_count == 1 wins)"
    - "Reconciler tenants are processed sorted, each inside tenant_scope, one try/except per tenant"

key-files:
  created:
    - backend/autonomous_ops/approvals.py
    - backend/autonomous_ops/breaker.py
    - backend/autonomous_ops/reconciler.py
    - backend/tests/test_autonomous_ops_approvals.py
    - backend/tests/test_autonomous_ops_breaker.py
    - backend/tests/test_autonomous_ops_reconciler.py
    - backend/tests/test_autonomous_ops_isolation.py
  modified:
    - backend/app_startup.py
    - backend/autonomous_ops/messages.py

key-decisions:
  - "Approve checks, in order: row exists for the tenant (not_found), stop (stopped), dispatcher known (refused no_dispatcher), row still open (already_handled), expiry (expired), then the compare-and-set"
  - "A stop landing between the approval and the dispatch moves the row to cancelled_by_stop and returns stopped; any other dispatch refusal or exception moves it to failed (dispatch_failed)"
  - "Undo that cannot write its instruction puts the row back to its previous state instead of leaving a row that claims it was undone"
  - "Breaker only trips a tenant whose stored level is undoable_auto (tripping a tenant at Off would raise it to Suggest)"
  - "Trip and restore are conditional raw updates, not settings.update, so concurrent evaluations trip once and notify once"
  - "A dispatching or approved row with no instruction, or with a pending/queued one, older than the stuck limit fails as not_delivered; a sent instruction with no result is left alone"

requirements-completed: [GATE-10, GATE-14, GATE-11, GATE-06]

coverage:
  - id: D1
    description: "Approve dispatches exactly one stamped instruction; two and five concurrent approves on a real database give one dispatched and the rest already_handled; audit order approved then dispatching"
    requirement: GATE-10
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_approvals.py#test_concurrent_approves_dispatch_exactly_once"
        status: pass
    human_judgment: false
  - id: D2
    description: "Approve at or after expiresAt expires the card and dispatches nothing; one second before dispatches; reconciler/expire_due expire overdue cards during a stop and an expired card never dispatches after resume"
    requirement: GATE-10
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_approvals.py#test_approve_exactly_at_expiry_is_expired_and_one_second_before_is_dispatched"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_approvals.py#test_expiry_runs_during_a_stop_and_an_expired_card_never_dispatches_after_resume"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_reconciler.py#test_overdue_cards_expire_also_while_a_stop_is_on"
        status: pass
    human_judgment: false
  - id: D3
    description: "A stop (platform, tenant or unreadable) freezes approving and changes nothing; deny and undo still work during a stop"
    requirement: GATE-06
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_approvals.py (stop tests, deny during a stop, undo during a stop)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Deleted, moved, newly protected target, level turned off or screen unticked after the card was made: row becomes refused with the reason code and nothing is dispatched"
    requirement: GATE-10
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_approvals.py (re-validation tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Undo writes one instruction of the undo command with kind undo, marks the row undone with undo fields, refuses non-undoable rows, reports no_undo, runs the breaker afterwards, restores the row when the instruction cannot be written"
    requirement: GATE-10
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_approvals.py (undo tests)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Breaker: 3 bad of 3 within 24 h trips once (level suggest, previousLevel, actionIds, control row, one notice); 2 of 3, a good one among them, oldest older than 24 h, shadow/control/manual rows do not; no double trip, no re-arm; restore capped at maxLevel"
    requirement: GATE-14
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_breaker.py (15 tests)"
        status: pass
    human_judgment: false
  - id: D7
    description: "Reconciler: empty tick clean, outcome mapping, not_delivered, one runner at a time, lost lock stops the pass, sorted order with per-tenant failure isolation, ContextVar None after every tick"
    requirement: GATE-11
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_reconciler.py (22 tests)"
        status: pass
    human_judgment: false
  - id: D8
    description: "Two tenants with identical hostnames, finding ids and dedupe keys: every operation for one leaves the other's documents identical before and after"
    requirement: GATE-11
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_isolation.py (7 tests)"
        status: pass
    human_judgment: false
  - id: D9
    description: "The reconciler runs inside the live backend and ensure_all_tenants runs at startup"
    requirement: GATE-11
    verification: []
    human_judgment: true
    rationale: "Needs a backend restart, which the shared-tree rules forbid here; import of app_startup and reconciler verified"

duration: 19min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 04: Approvals, undo, circuit breaker and reconciler Summary

**Single-use 24 h approval cards (one compare-and-set, re-validated before dispatch), deny, undo that works during a stop, a circuit breaker that drops a tenant to Suggest after 3 bad automatic outcomes and never re-arms itself, and a lock-renewed reconciler that expires cards even during a stop and follows dispatched rows to their outcome, proven not to cross tenants**

## Accomplishments

- `approvals.approve` returns exactly one `dispatched` under 2 and 5 concurrent callers (real MongoDB, `asyncio.gather`); one stamped instruction, audit order `approved` then `dispatching`.
- A stop freezes approving but not deny, undo or expiry; an expired card cannot be approved after the stop clears (PROH-81-08).
- `breaker.evaluate` / `restore` implement D-18; nothing time-driven calls `restore` (AST-checked on `approvals.py` and `reconciler.py`).
- `reconciler.reconciler_loop` is registered in `app_startup.py` as `autonomous_ops_reconciler`, and `settings.ensure_all_tenants` runs once after the migrations as a backstop.

## Approve status vocabulary

| `approve` status | Meaning | Row afterwards |
|---|---|---|
| `dispatched` (+ `dispatch`) | CAS won, re-check passed, dispatcher ran | `dispatching` (dispatchers move it from `approved`) |
| `stopped` | a platform or tenant stop is on (unreadable counts as stopped), or one landed after the approval | unchanged, or `cancelled_by_stop` if it landed after the CAS |
| `expired` | now at or after `approval.expiresAt` | `expired` |
| `already_handled` | not open any more, or another caller won | unchanged |
| `not_found` | no such row for this tenant | none |
| `refused` + `reason` | `no_dispatcher` (row unchanged); `no_target`, `cross_tenant_target`, `protected_target`, `invalid_target`, `not_enabled`, `platform_tenant`, `level_off`, `settings_unreadable` (row `refused`); `dispatch_failed` or the gate's reason (row `failed`) | as stated |

`deny`: `denied` / `already_handled` / `not_found`. `undo`: `undone` / `no_undo` / `already_handled` / `not_found` / `refused` (`not_undoable`, `no_target`, `dispatch_failed`).

## Instruction status to ledger state (reconciler)

| Latest instruction or response task status (case-insensitive) | Row `dispatching` becomes |
|---|---|
| completed, success, executed, done | `executed` (`result.instructionStatus`) |
| failed, failure, refused, error, rejected | `failed`, reasonCode `agent_failed` |
| pending, queued, no instruction, or no such document, and the row untouched for `AUTONOMOUS_OPS_STUCK_DISPATCH_MIN` (default 30) | `failed`, reasonCode `not_delivered` (also applies to a stuck `approved` row) |
| anything else (for example `sent`) | unchanged |

Env: `AUTONOMOUS_OPS_RECONCILE_INTERVAL_SEC` (default 60), `AUTONOMOUS_OPS_STUCK_DISPATCH_MIN` (default 30). Lock `autonomous_ops_reconciler`, TTL 120 s, renewed every 30 s.

## Task Commits

1. **Task 1 (tracer): approve once, re-validate, dispatch through the gate** - `621019424`
2. **Task 2: deny, expiry, undo, stop interplay, circuit breaker** - `66e8f0845`
3. **Task 3: reconciler, startup wiring, isolation proof** - `afb65926c`

## Own hunks of app_startup.py

Confirmed: only this plan's hunks were committed to `backend/app_startup.py` (14 added lines: the reconciler registration after the approval-timeout loop, and the `ensure_all_tenants` try/except after `run_migrations`). The user's `agent_telemetry_retention_loop` import and registration lines remain uncommitted in the working tree, and nothing committed references them.

## Deviations from Plan

**1. [Rule 2 - race] Breaker trip and restore use conditional raw updates**
- **Issue:** the plan said "through settings.update". That is an unconditional `$set`, so an undo click and the reconciler evaluating at the same moment could both trip (two control rows, two notices).
- **Fix:** `update_one` filtered on `{level, breaker: None}` (trip) and `{breaker != None}` (restore), winner = `modified_count == 1`. Tested with 4 concurrent evaluates.

**2. [Rule 1 - gap] Breaker does not trip a tenant already at Suggest or Off**
- Tripping an Off tenant would have raised it to Suggest. Evaluate returns False unless the stored level is `undoable_auto`.

**3. [Rule 2 - missing handling] Undo that cannot dispatch, a stop after the CAS, approved rows stuck**
- Undo reverts the row if `gate.execute` refuses; a stop after the approval cancels the row (`cancelled_by_stop`); a dispatcher exception or refusal fails it; a stuck `approved` row is failed by the reconciler. Not in the plan; all tested.

**4. [Scope] messages.py gained three entries** (`dispatch_failed`, `not_delivered`, `agent_failed`) so rows written by approvals and the reconciler carry plain-words text. No banned term; the 81-11 coverage test still passes.

**5. [Interface] Optional keyword arguments added without changing the contract:** `expire_due(..., tenant_id=None)` and `tick(..., lost=None)`; `reconciler.run_once` added (lock plus tick, used by the loop).

**6. [Process] No red run observed.** Test modules were written before the implementation but were not run red first; correctness was checked with hand mutations instead: removing the approve stop check, the tenant filter in `expire_due` and the tenant filter in the instruction lookup each failed tests. Removing the CAS expiry filter, or the breaker's second guard, did not fail a test (each is defence in depth behind an earlier check).

**7. [Process] Distributed lock handle.** `lock_with_renewal` reads `db._db`, so `run_once` hands it `SimpleNamespace(_db=raw(db))` rather than the raw handle the plan named.

**8. [Scope] Indexes.** The plan assigns no `ensure_indexes` call to this plan, so none was added to startup; 81-12's migration 024 owns them. Until it runs, the `open_dedupe` unique index and the `state_expiry` index do not exist on the live database.

## Known Stubs

None.

## Issues Encountered

- The backend runs from this checkout without auto-reload; nothing here is live until the user restarts it.
- A `sent` instruction that never reports a result keeps its row `dispatching` (and its dedupe key open). Plan scope was undelivered only; the stuck rule can be widened to `sent` later if autonomous actions turn out to be long-running.

## User Setup Required

Steps left for the user (not run, per the shared-tree rules): restart `omni-backend.service` to start the reconciler and the settings backstop; migration 024 (81-12) to create the indexes. Nothing was deployed, restarted or migrated, and no live database was touched.

## Next Phase Readiness

- 81-08 registers its remediation dispatcher with `approvals.register_dispatcher("remediation", fn)`; 81-09 wires `approve`, `deny`, `undo` and `breaker.restore` to routes (permission check there). Phase 83's approve buttons should run approval as a background task, since a remediation dispatch may poll for about two minutes (A-81-INLINE-DISPATCH).
- Verification run: 10 test modules, 167 passed, 0 skipped (`test_autonomous_ops_{reconciler,isolation,approvals,breaker,gate,gate_order,ledger,protected,registry}.py` and `test_distributed_lock.py`).

## Self-Check: PASSED

Created files exist (7 of 7), commits 621019424, 66e8f0845 and afb65926c are ancestors of HEAD, acceptance greps re-run (5 function definitions in approvals, 2 in breaker, `reconciler_loop` and `ensure_all_tenants` in app_startup, `restore` never called by approvals or reconciler, no direct instruction writes in approvals), `import app_startup` and `reconciler` succeed with `ENVIRONMENT=development`.

---
*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Completed: 2026-10-26*
