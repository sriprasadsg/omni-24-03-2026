---
phase: 82-platform-self-healing-scheduled-retention
plan: 16
subsystem: platform-health
tags: [watchdog, sync, self-healing, activity, certificates, mongodb, gap-closure, wr-02, wr-03]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "82-01 watchdog sync route and selfheal ingest; 82-04 watchdog cert and disk events; 82-08 GET /health document"
provides:
  - "selfheal._storable, clean_params dropping and _scrub storing None for numbers a row cannot hold"
  - "ingest_events isolates each event: a failure other than a ledger outage counts as dropped and the loop goes on"
  - "health_messages._finite, a _num that never raises, _cert_rule from the unrounded daysLeft, rule id cert-unreadable"
affects: [82 verification (HEAL-03, HEAL-07), 82-17]

requirements-completed: [HEAL-03, HEAL-07]

actuals:
  tokens: 5000
  tasks: 2
  commits: 2

key-files:
  modified:
    - backend/autonomous_ops/health_messages.py
    - backend/autonomous_ops/selfheal.py
    - backend/tests/test_platform_health_sync.py
    - backend/tests/test_platform_health_status.py

key-decisions:
  - "math.isfinite only ever runs on a float: on a 400-digit int it raises OverflowError, so ints are range-checked against signed 64-bit instead"
  - "ingest_events keeps LedgerUnavailable as neither accepted nor dropped; any other Exception counts as dropped and logs the validated event id plus the exception class, never the text; CancelledError is not an Exception and propagates"
  - "clean_params moved inside the per-event try, so even a failure in parameter cleaning costs one event"
  - "The certificate rule id compares the unrounded daysLeft against the watchdog's own ladder (1, 7, 14, else 30); the rung picks nothing and the rounding _num is not used for it"
  - "selfheal._num (GET /health copy) is untouched: once _scrub stores None for infinity, infinity cannot reach it"

patterns-established:
  - "A poison body is built with json.dumps from marker strings replaced in the text (_raw), because Python's json refuses to dump 1e999 or Infinity as valid JSON the way the backend parser reads it"

duration: 12min
completed: 2026-10-31
status: complete
plan_head_before: a2827058125b82be30b52650f8669d18796d92bb
plan_head_after: 14d343740434038e68d35f2087ffdd84d41ca7dd
commits: 2
---

# Phase 82 Plan 16: WR-03 poison numbers and WR-02 certificate rule ids Summary

**One malformed watchdog number (infinity, NaN, a 400-digit integer) now costs one dropped event or one null field instead of a 503 on every sync, and a certificate row's rule id names the threshold that actually fired, with an unreadable certificate reported as unreadable.**

## Accomplishments

- `selfheal.py`: `_storable` (bool, int within signed 64-bit, finite float) is used by `clean_params` (the key is dropped) and `_scrub` (the value becomes None at any depth; bools and in-range numbers unchanged). `post_sync` runs `store_snapshot` before `ingest_events`, so a bad snapshot number can no longer fail the request before events are read.
- `ingest_events`: the try now wraps `clean_params` and `record_platform_health`. `LedgerUnavailable` keeps its meaning (logged, stays in the spool). Any other `Exception` increments `dropped`, logs `selfheal: event <id> dropped: <ClassName>` and continues.
- `health_messages.py`: `_finite` and a `_num` returning None for non-finite input; `_CERT_LADDER` mirroring the watchdog's `CERT_LADDER`; `_cert_rule(params)`; `cert-unreadable` added to `RULE_IDS`; the unreadable branch of `_reason_and_result` returns reason `Can't read this file.` and result `<path> could not be read, so its expiry date is unknown.` The chip stays rung based (rung 2 stays Warning).

## Task Commits

1. **Task 1 (tracer)** `ab2907a7c` fix - poison numbers and per-event isolation
2. **Task 2** `14d343740` fix - certificate rule from daysLeft, cert-unreadable

## RED evidence (Task 1, before the fix, private mongod on 27997)

The poison batch answered 503, and the route logged the overflow:

```
ERROR watchdog_ingest_endpoints: watchdog sync could not be served: cannot convert float infinity to integer
```

That is the OverflowError from `int(round(inf))` in `health_messages._num`. The same run showed the 400-digit integer failing at insert (`MongoDB can only handle up to 8-byte ints`), and the render-failure test logged `secret-text` through the route's own handler. 21 tests failed in the two modules before the change; 90 passed after it. Task 2: 36 new cases failed first, then passed.

## Rule ids as tested (daysLeft to rule, run with rung 1, 2 and 3)

| daysLeft | rule |
|----------|------|
| 31, 30, 15, 14.4 | cert-expiry-30d |
| 14, 8, 7.4 | cert-expiry-14d |
| 7, 2, 1.4 | cert-expiry-7d |
| 1, 0, -3, 0.6 | cert-expiry-1d |
| none, inf, nan | cert-unreadable |

The stored row through the sync route: daysLeft 12.5 / rung 1 stores `cert-expiry-14d`; rung 2 with `error: unreadable` stores `cert-unreadable` with `healthChip` warning. A readable certificate keeps `Expires in 12 days.` and the pinned-certificate result line.

## Verification

Plan-level run on the private mongod (27997): `test_platform_health_sync`, `_activity`, `_status`, `_oncall`, `test_autonomous_ops_copy`, `test_watchdog_contract`: 214 passed, 0 skipped. `test_chip_and_rule_tables_cover_every_kind` passes unchanged. No frontend file holds a `cert-expiry-` list. `deploy/omni-watchdog/` is unchanged (`git diff` against HEAD empty). The private mongod was stopped through its pidfile; the live mongod (pid 605) was not touched.

## Requirements

HEAL-03 and HEAL-07 are listed in the frontmatter as the plan's requirements but are NOT ticked in REQUIREMENTS.md: the plan says not to mark any HEAL requirement complete, so they stay Pending until phase verification.

## Deviations from Plan

None - plan executed as written. Small additions inside the plan's scope: `test_scrub_keeps_numbers_a_row_can_hold` and `test_scrub_keeps_bools_and_reaches_every_depth` split the plan's scrub table so each case reads on its own, and `test_a_readable_certificate_keeps_its_copy` pins the unchanged copy.

## Known Stubs

None.

## Threat Flags

None. T-82-49 to T-82-52 are mitigated as planned: numbers are dropped or nulled, the per-event guard bounds a failure to one event, the log line carries id and class only, and the rule id follows the unrounded daysLeft.

## Notes

- Assumptions A-82-A18 and A-82-A19 stay flagged for the verifier; no change was made for an integer beyond the JSON digit limit (invalid JSON, 422 for the whole request, and the watchdog cannot produce one).
- Nothing deployed: no backend restart, UI publish, watchdog install or push.

## Self-Check: PASSED

Files and commits `ab2907a7c`, `14d343740` exist on the branch; acceptance greps match (5 sync tests, `_storable` and `_finite` defined once, `_storable(` 3 uses, `type(exc).__name__` present, `cert-unreadable` 2, `Can't read this file.` 1).
