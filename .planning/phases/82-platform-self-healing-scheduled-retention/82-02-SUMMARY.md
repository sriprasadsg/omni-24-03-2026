---
phase: 82-platform-self-healing-scheduled-retention
plan: 02
subsystem: infra
tags: [watchdog, stdlib, systemd, mongodb-op-msg, debounce, ndjson-spool, flock]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "plan 82-01: POST /api/internal/watchdog/sync (frozen v1 contract), platform_health ledger rows"
provides:
  - "deploy/omni-watchdog/: stdlib-only watchdog package and root entry script (not installed anywhere)"
  - "One run checks mongod (is-active + OP_MSG ping), omni-backend (/api/health/ready), nginx (is-active + TLS probe), Ollama (expected state only)"
  - "D-06 debounce: checking after 1 failed check, down after 2, service_recovered on return"
  - "Sync client with fsynced NDJSON spool, ordered replay, 50 events per call, 2,000-line cap"
  - "D-11 three-source stop: STOP file, last database stop (cached in state.json), cache, none"
  - "Config loading, oncall.env parsing with secret-safe repr, atomic state, corrupt-state quarantine, flock run lock"
  - "backend/tests/_watchdog_support.py: FakeRun, FakeHttp, FakeClock, fake mongo and TLS servers"
affects: [82-03 restart state machine, 82-04 cert and disk warnings, 82-05 paging, 82-06 install files, 82-07 outbox and test alert]

actuals:
  tokens: 17100
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Every external effect is an injected seam (run, http, now); tests never touch the host"
    - "Events are fsynced to the spool before any send and leave it only on backend acknowledgement"
    - "Watchdog sends structured fields only; the backend renders the words"

key-files:
  created:
    - deploy/omni-watchdog/omni-watchdog.py
    - deploy/omni-watchdog/omni_watchdog/__init__.py
    - deploy/omni-watchdog/omni_watchdog/config.py
    - deploy/omni-watchdog/omni_watchdog/state.py
    - deploy/omni-watchdog/omni_watchdog/checks.py
    - deploy/omni-watchdog/omni_watchdog/services.py
    - deploy/omni-watchdog/omni_watchdog/sync.py
    - deploy/omni-watchdog/omni_watchdog/run.py
    - backend/tests/_watchdog_support.py
    - backend/tests/test_watchdog_checks.py
    - backend/tests/test_watchdog_sync.py
  modified: []

key-decisions:
  - "A 200 sync clears every sent event except ones the response neither accepted nor dropped; those are retried and abandoned after 3 hand-overs (counted in state spoolAbandoned), matching the 82-01 rule that an unrecorded event must be re-sent"
  - "observe() takes an optional target keyword so events carry the service id; the plan's four-argument form still works"
  - "Loopback probe targets (mongo_host/port, nginx_host/port, ollama_url) are DEFAULTS keys that watchdog.conf cannot override, so tests can point at fake servers without widening what an operator can configure"
  - "A corrupt state.json is detected in load_state, which returns an empty state flagged _reset; run_once turns the flag into exactly one state_reset event"
  - "With ollama_expected true the check also needs an HTTP 200 from the local Ollama port, not just an active unit"

patterns-established:
  - "Seams: run(argv, timeout) -> (rc, stdout); http(method, url, headers, body, timeout) -> (status, bytes), raises on connection errors; now() -> epoch float"
  - "Stop resolution happens at the start of a run from file or cache; the sync response refreshes the cache for the next run"

requirements-completed: [HEAL-01, HEAL-05]

coverage:
  - id: D1
    description: "One run checks mongod, the backend, nginx and Ollama's expected state, reports them in the fixed order in the v1 body with the bearer token, and never starts an unexpected Ollama"
    requirement: HEAL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_checks.py#test_run_once_reports_the_four_services_in_fixed_order_with_the_bearer_token"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_checks.py#test_run_once_with_ollama_running_unexpectedly_never_starts_it"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_checks.py (OP_MSG alive/dead, backend 503 demo_mode, nginx TLS probe tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-06 debounce: checking after 1 failed check, down after 2 in a row, service_recovered on the first pass"
    requirement: HEAL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_checks.py#test_debounce_one_failure_is_checking_two_is_down_then_recovered"
        status: pass
    human_judgment: false
  - id: D3
    description: "Events are spooled before sending, replayed oldest first at most 50 per call, capped at 2,000 lines, and kept on 401, 503 or no connection"
    requirement: HEAL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_sync.py (spool on backend down, replay order, 50-per-call cap, 2,000-line cap, non-200 answers)"
        status: pass
    human_judgment: false
  - id: D4
    description: "D-11 stop: STOP file beats the database, database stop is cached, cache is used when the backend is down, nothing means off"
    requirement: HEAL-05
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_sync.py (stop file precedence, database stop cached, cache fallback, none, next-run use)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Atomic state, corrupt-state quarantine with one state_reset event, run lock, secret-safe on-call object, stdlib-only imports, no shell"
    requirement: HEAL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_checks.py (crash before replace, corrupt state, lock, oncall repr, AST import scan, ping-only MongoDB contact)"
        status: pass
    human_judgment: false
  - id: D6
    description: "The watchdog works on a real host: real systemctl, real mongod and nginx, the polkit-less is-active calls, python3 -I from the install path"
    verification: []
    human_judgment: true
    rationale: "Everything is proven against fakes and throwaway loopback servers by design (no install on this VM); first live run happens after the operator installs it from 82-06's checklist"

duration: 37min
completed: 2026-10-27
status: complete
plan_head_before: cadea0c851c746c40d99728dcb2b40c527f2b595
plan_head_after: 3a3aee32b1719cf15a44760773e040c38fdc3666
commits: 3
---

# Phase 82 Plan 02: Stdlib watchdog - checks, debounce, spool and stop Summary

**Stdlib-only watchdog that checks MongoDB (OP_MSG ping), the backend, nginx and Ollama's expected state each run, debounces failures, spools its events through backend outages and reports through the frozen v1 sync contract**

## Performance

- **Duration:** 37 min wall clock (07:43Z to 08:20Z, includes a pause for a usage limit)
- **Tasks:** 3
- **Files:** 11 created, none modified (nothing installed, nothing under /etc or /var/lib touched)

## Accomplishments

- `run_once` checks the four services in the fixed order mongod, omni-backend, nginx, ollama; Ollama with `ollama_expected` false is only ever asked `is-active` (state `expected_off`, or `unexpected_running` with one event).
- Debounce per D-06; the sync body carries the v1 service fields, services keyed in fixed order, `Authorization: Bearer <ingest.token>`.
- Offline spool and replay, three-source stop, config loading, crash-safe state, flock run lock, and tests that prove the package imports only the standard library.

## Seam signatures (82-03, 82-04 and 82-05 call these)

```python
run(argv: list[str], timeout: float) -> (returncode: int, stdout: str)
http(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> (status: int, body: bytes)   # raises on connection error
now() -> float            # epoch seconds
run_mod.run_once(config: dict, state_dir: str, *, run, http, now) -> dict
    # {"synced", "response", "events", "stop": {"effective","source"}, "spooled", "services": {id: state}}   or {"skipped": "locked"}
checks.check_all(run, http, config) -> [(service id, ok, detail)]            # SERVICE_ORDER
services.observe(service_state, ok, detail, now, target=None) -> (new state, [events])
services.make_event(kind, severity, target, now, params=None) -> event dict (32-hex id, ISO "at")
sync.build_body(host, services, certs, disks, oncall, stop, events, delivered, *, sent_at)
sync.post_sync(http, base_url, token, body) / post_results(...) -> (ok, response | None)
sync.sync_cycle(http, config, token, body_without_events, spool, state) -> (ok, response | None)
sync.resolve_stop(stop_file, last_sync_response, state, now=None) -> (active, source)
state.Spool(path): append(events) -> dropped, read(n), remove(ids), bump_tries(ids), len()
state.load_state(path, now=None) / save_state(path, state) / run_lock(path) / new_event_id()
config.load_config(path) / load_oncall(path) -> Oncall / read_token(path)
```

State file keys (epoch seconds): `services` (per service: state, since, failedChecks, restartsInWindow, nextRestartAt, budgetReturnsAt, pagedAt, waitingOn, detail), `stopCache {active, pressedAt, at}`, `spoolDropped`, `spoolAbandoned`, `oncallLast`. Test stubs: `FakeRun(active)`, `FakeHttp.set(method, path, *responses)` and `FakeHttp.accept_all`, `FakeClock.advance`, fixtures `fake_mongo_server`, `fake_tls_server`.

## Task Commits

1. **Task 1: Tracer - one run checks the four services, debounces and posts the v1 body** - `d95c79439` (feat)
2. **Task 2: Offline spool, ordered replay and the three-source stop** - `94de64e4d` (feat)
3. **Task 3: Config files, crash-safe state, run lock and stdlib-only guarantee** - `3a3aee32b` (feat)

**Plan metadata:** committed separately (docs: complete plan).

Tracer gate: the tracer's automated `<verify>` passed end to end before expansion; no human check was attached.

## Decisions Made

See key-decisions. The `certs`, `disks` blocks of the body are empty lists and `oncall.last` is whatever `state.oncallLast` holds (null) until 82-04 and 82-05 fill them.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Unrecorded events are retried instead of cleared**
- **Found during:** Task 2
- **Issue:** The plan says every sent id leaves the spool after a 200. The 82-01 backend deliberately leaves an event it could not record out of both `acceptedEventIds` and `droppedEvents` so the watchdog re-sends it; clearing it would lose that event.
- **Fix:** `sync_cycle` clears accepted ids and, when `droppedEvents` covers the rest, those too; otherwise the leftovers stay with a `tries` counter and are abandoned after 3 hand-overs. A response with no id list clears everything.
- **Files modified:** deploy/omni-watchdog/omni_watchdog/sync.py, state.py
- **Verification:** `test_unaccepted_events_are_kept_then_abandoned_after_three_hand_overs`, `test_events_the_backend_dropped_leave_the_spool`
- **Committed in:** 94de64e4d

**2. [Rule 3 - Blocking] state.py created in Task 1**
- **Found during:** Task 1
- **Issue:** The tracer needs event ids and a saved state, but the plan lists state.py under Tasks 2 and 3.
- **Fix:** Task 1 creates `state.py` with `new_event_id`, `load_state` and atomic `save_state`; Tasks 2 and 3 add the spool, corrupt-file recovery and the run lock.
- **Committed in:** d95c79439

### Process note (TDD)

The tasks are marked `tdd="true"`, but the plan is `type: execute`, so no RED/GREEN gate applies. Tests and code were committed together per task (one commit each, as the plan asks); for Tasks 1 and 2 the implementation was written before the tests, so there is no separate failing-test commit.

---

**Total deviations:** 2 auto-fixed (1 missing-critical, 1 blocking), 1 process note.
**Impact on plan:** No scope creep; the first keeps the watchdog consistent with the committed 82-01 contract.

## Issues Encountered

- Tests need no MongoDB: no private test mongod was started and nothing touched the live database or any service. The fake servers bind ephemeral loopback ports only.
- Pre-existing failures listed in the environment notes were not touched. The new tests were run on their own (51 passed).

## Known Stubs

`certs: []`, `disks: []` and the on-call `last: null` in the sync body are intentional placeholders resolved by 82-04 (certificates, disks) and 82-05 (paging). Restart fields (`restartsInWindow`, `nextRestartAt`, `budgetReturnsAt`, `pagedAt`, `waitingOn`) are present and null/0 until 82-03.

## Threat Flags

None beyond the plan's register: T-82-06 to T-82-09 are mitigated as specified (isolated-mode entry script, atomic state with lock and quarantine, argument-list subprocess with unit names from a constant, secret-safe on-call repr). The nginx probe disables certificate verification on loopback by design (liveness only).

## User Setup Required

None - nothing is installed by this plan. The install checklist and units come in 82-06.

## Next Phase Readiness

82-03 plugs restarts into `_run_locked` after the observe loop (using `stop` and `services.observe` states); 82-04 fills `certs` and `disks`; 82-05 fills `oncall` and `delivered`. Note for them: `run.py` is at 111 lines, `state.py` 189, `sync.py` 130, all well under 500.

---
*Phase: 82-platform-self-healing-scheduled-retention*
*Completed: 2026-10-27*

## Self-Check: PASSED

All 11 created files exist; commits `d95c79439`, `94de64e4d` and `3a3aee32b` are ancestors of HEAD; 51 watchdog tests pass; `python3 -I deploy/omni-watchdog/omni-watchdog.py --help` exits 0.
