---
phase: 82-platform-self-healing-scheduled-retention
plan: 04
subsystem: infra
tags: [watchdog, stdlib, openssl, statvfs, certificate-expiry, disk-forecast, incidents]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "plan 82-03 incident store (incidents.open_incident / clear_incident), the run sequence in run._run_locked, the spool"
provides:
  - "warnings.evaluate(state, config, now, run, *, clock, fs) -> (certs, disks, events): certificate expiry ladder, disk fullness ladder with hysteresis, 7-day least-squares fill forecast"
  - "certs and disks blocks in the v1 sync body; cert_warning, disk_warning and disk_forecast events in the same spool as the restart events"
  - "Open incidents cert:*, disk:*, disk-forecast:* in state[incidents] for the 82-05 pager"
  - "Structural guard: the watchdog can only read (no delete calls outside state.py, only openssl x509 -noout -enddate)"
affects: [82-05 paging (incident keys and kinds below), 82-08 backend rendering of the certificate and disk cards and of cert_warning / disk_warning / disk_forecast events]

actuals:
  tokens: 13200
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "One open incident per check: _settle() clears any other open key of the check and opens the wanted one; a newly opened key emits exactly one event"
    - "Hysteresis by 'held' level: the open incident's rung is kept while the value is within 2 points (disk) or 20 percent (forecast) of its threshold"
    - "Every external effect is a seam: run (openssl), fs (statvfs/stat), clock (read allowance); the fake host lives in tests/_watchdog_warnings_world.py"

key-files:
  created:
    - deploy/omni-watchdog/omni_watchdog/warnings.py
    - backend/tests/_watchdog_warnings_world.py
    - backend/tests/test_watchdog_warnings.py
  modified:
    - deploy/omni-watchdog/omni_watchdog/run.py
    - backend/tests/_watchdog_restart_world.py
    - backend/tests/test_watchdog_checks.py
    - backend/tests/test_watchdog_sync.py

key-decisions:
  - "Certificates block capped at MAX_CERTS = 32 (pinned first, then extra_certs in config order, no repeats); the backend model rejects the whole sync body above 32 certs entries. Disks capped at MAX_DISKS = 32 for the same reason. The backend model is unchanged."
  - "Certificate reads share CERT_BUDGET = 6 s of clock time, each read has a READ_TIMEOUT of min(3, what is left). A certificate not reached, or whose read timed out (exit 124), keeps its last reported entry and incident for the run; it is never reported as unreadable."
  - "State is saved right after the spool append and before the sync, so incidents are on disk before any network or (from 82-05) paging; a run killed earlier leaves the previous complete state.json (atomic replace)."
  - "Forecast sufficiency is judged on all retained samples (8 days): span >= 7 days; the slope is fitted over the newest 7 days of them. This avoids a permanent 'insufficient' when run jitter makes the oldest sample inside a strict 7-day window a little younger than 7 days."
  - "Incident kinds are cert_expiring / cert_expired / cert_unreadable / disk_full / disk_forecast; the kind is fixed when the incident opens."

patterns-established:
  - "Warning stage position: restart.decide -> warnings.evaluate -> spool.append -> save_state -> sync"
  - "Suites about something else stub run_mod.warnings.evaluate (autouse), as 82-03 did for restart.decide"

requirements-completed: [HEAL-03, HEAL-04]

coverage:
  - id: D1
    description: "HEAL-03: a certificate 14 days from expiry (real openssl on a certificate generated in tmp_path) is a rung-1 entry in the sync body, one cert_warning event with params {target, rung, daysLeft, notAfter} and an open cert:<path>:14d incident; a second run at the same clock emits nothing"
    requirement: HEAL-03
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_a_certificate_14_days_from_expiry_is_a_rung_1_entry_one_event_and_one_open_incident"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_the_next_run_at_the_same_clock_opens_nothing_and_emits_no_second_event"
        status: pass
    human_judgment: false
  - id: D2
    description: "HEAL-03 ladder: at-most thresholds 30/14/7/1 days with exact-value and one-second tests either side, expired stays on the 1d key, walking down the ladder gives one open incident and four events, float daysLeft never rounded"
    requirement: HEAL-03
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_cert_ladder_boundaries_at_most_thresholds"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_cert_walk_down_the_ladder_opens_each_key_once_and_clears_the_old_one"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_cert_days_left_is_a_float_that_is_never_rounded"
        status: pass
    human_judgment: false
  - id: D3
    description: "Unreadable certificate file is a rung-2 warning with error 'unreadable' and the other certificates are still checked; extra_certs are checked after the pinned nginx certificate, only that one is pinned; a certificate removed from watchdog.conf stops being watched"
    requirement: HEAL-03
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_cert_unreadable_file_is_a_warning_and_the_others_are_still_checked"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_cert_extra_paths_are_checked_in_config_order_and_only_the_nginx_cert_is_pinned"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_cert_removed_from_the_config_stops_being_watched_and_its_incident_clears"
        status: pass
    human_judgment: false
  - id: D4
    description: "Orchestrator note 1: a long extra_certs list is capped at 32 certs entries (pinned first) so the backend never rejects the whole sync body"
    requirement: HEAL-03
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_cert_a_long_extra_certs_list_is_capped_at_32_entries_pinned_first"
        status: pass
    human_judgment: false
  - id: D5
    description: "Orchestrator note 2: certificate reads share a 6 s allowance (3 s each); an unreached or timed-out certificate keeps its last entry and incident and is not reported unreadable (fake-clock tests)"
    requirement: HEAL-03
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_cert_reads_share_a_six_second_allowance_and_an_unreached_one_keeps_its_last_entry"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_cert_a_timed_out_read_is_not_a_statement_about_the_file"
        status: pass
    human_judgment: false
  - id: D6
    description: "HEAL-04 disk ladder: df-semantics percent, 80/90/95 (info/warning/critical), paths on one st_dev are one entry, two devices two entries, cleared only 2 points below the threshold, exact boundaries 80.0 / 79.99 / 95.0"
    requirement: HEAL-04
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_disk_ladder_moves_up_without_repeating_and_keeps_a_rung_until_two_points_below"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_disk_ladder_boundaries_exact_threshold_and_one_hundredth_of_a_point_below"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_disk_two_filesystems_make_two_entries"
        status: pass
    human_judgment: false
  - id: D7
    description: "HEAL-04 forecast: one sample per hour (kept 8 days, backward clock steps discarded), insufficient under 7 days (exactly 7 days computes), flat when not growing, 10-day growth opens disk-forecast:/:14d, 0.9 days opens the critical :1d, cleared 20 percent above the threshold or when flat"
    requirement: HEAL-04
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_forecast_growth_that_fills_in_ten_days_is_rung_1_with_the_14d_incident"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_forecast_under_a_day_is_critical_with_the_1d_incident"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_forecast_needs_exactly_seven_days_of_span_not_a_second_less"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_forecast_incident_clears_only_when_days_rise_twenty_percent_above_its_threshold"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_disk_one_sample_per_hour_never_more_and_none_older_than_eight_days"
        status: pass
    human_judgment: false
  - id: D8
    description: "Orchestrator note 3 / stage order: warning events share one spool with the restart events so a backend outage loses neither; a run killed during the warning stage leaves the previous complete state.json"
    requirement: HEAL-03
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_restart_and_warning_events_share_one_spool_so_an_outage_loses_neither"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_a_run_that_dies_during_the_warning_stage_leaves_the_previous_complete_state"
        status: pass
    human_judgment: false
  - id: D9
    description: "PROH-82-03 / D-24: the watchdog never renews a certificate and never deletes, truncates or compresses a file; no backend module reads certificates or calls statvfs for this feature (AST scan over every .py under deploy/omni-watchdog)"
    requirement: HEAL-03
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_never_deletes_or_renews_a_certificate_or_a_file"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_never_runs_openssl_with_any_verb_but_x509_enddate_and_names_no_renewal_tool"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_warnings.py#test_never_reads_certificates_or_disks_in_the_backend_for_this_feature"
        status: pass
    human_judgment: false
  - id: D10
    description: "On the real server, with the watchdog installed: the real /etc/nginx/ssl/omni.crt reads as about 800 days, / and /var/lib/mongodb appear as one disk entry, and the panel shows both cards"
    verification: []
    human_judgment: true
    rationale: "Needs the watchdog installed and a sync to the live backend, which is the operator's step (INSTALL.md); this plan reads no real certificate or disk and installs nothing. The backend cards are plan 82-08."

duration: 25min
completed: 2026-10-30
status: complete
plan_head_before: 1f859802061bba952e3cf9a96d4cff0a77116e4f
plan_head_after: 9c59bc9a503147c25b69c1660c9d93f5651c77d3
commits: 3
---

# Phase 82 Plan 04: Certificate, disk and disk-forecast warnings Summary

**The watchdog now reads the pinned nginx certificate plus any extra certificates and every configured filesystem on each run, and turns them into deduplicated, hysteresis-protected incident ladders (certificate 30/14/7/1 days, disk 80/90/95 percent, 7-day least-squares fill forecast 14/7/1 days) that enter the same spool as the restart events, while the code provably only reads.**

## Performance

- **Duration:** about 25 min
- **Started:** 2026-10-30T19:19Z (ledger base)
- **Completed:** 2026-10-30
- **Tasks:** 3
- **Files:** 7 (3 new)
- **commits: 3** measured from the ledger base `1f8598020`: `62eac8aa0`, `9e1dbde4d`, `9c59bc9a5` (all three are task commits)

## Accomplishments

- `warnings.py` (320 lines): `CERT_LADDER`, `DISK_LADDER`, `FORECAST_LADDER`, `HYSTERESIS_POINTS = 2.0`, `FORECAST_CLEAR_FACTOR = 1.2`, `SAMPLE_EVERY = 3600`, `SAMPLE_KEEP = 8 days`, `FORECAST_SPAN = 7 days`, `MAX_CERTS = 32`, `MAX_DISKS = 32`, `READ_TIMEOUT = 3`, `CERT_BUDGET = 6`; functions `cert_paths`, `cert_days_left`, `cert_level`, `check_certs`, `disk_usage`, `record_sample`, `forecast`, `forecast_rung`, `disk_level`, `forecast_level`, `check_disks`, `evaluate`, class `RealFs`.
- `run.py`: `warnings.evaluate(state, cfg, t, run, clock=now, fs=fs)` runs after `restart.decide` and before the spool append; certs and disks go into `sync.build_body`; `save_state` runs right after the spool append (before the sync). `run_once` gained an optional `fs` seam.
- 51 tests in `test_watchdog_warnings.py` (472 lines) on a fake host (`_watchdog_warnings_world.py`). All watchdog suites together: 168 passed (warnings, restart, restart_order, checks, sync, artifacts).

## Incident keys (82-05 pages these)

`state["incidents"]` entries use the 82-03 shape (`key, severity, kind, target, params, openedAt, pageKey, sent, clearedAt`). One check has at most one open incident; moving along a ladder clears the old key and opens the new one. `target` is the certificate path or the mount name. Every newly opened key emits exactly one event.

| Key format | Severity | Kind | Opens when | Clears when | Params (incident and event) |
|---|---|---|---|---|---|
| `cert:<path>:30d` | info (rung 1) | `cert_expiring` | daysLeft <= 30 and > 14 | daysLeft > 30, or moves to another rung | `rung, daysLeft, notAfter` |
| `cert:<path>:14d` | info (rung 1) | `cert_expiring` | daysLeft <= 14 and > 7 | as above | `rung, daysLeft, notAfter` |
| `cert:<path>:7d` | warning (rung 2) | `cert_expiring` | daysLeft <= 7 and > 1 | as above | `rung, daysLeft, notAfter` |
| `cert:<path>:1d` | critical (rung 3) | `cert_expiring`; `cert_expired` if it opens with daysLeft <= 0 | daysLeft <= 1 or already expired (stays open, no new event, when the certificate expires while it is open) | certificate replaced (daysLeft > 1) | `rung, daysLeft, notAfter` |
| `cert:<path>:unreadable` | warning (rung 2) | `cert_unreadable` | openssl fails or prints no valid `notAfter=` | file readable again | `rung, error: "unreadable"` |
| `disk:<mount>:80` | info (rung 1) | `disk_full` | usedPct >= 80 | usedPct < 78 | `rung, usedPct` |
| `disk:<mount>:90` | warning (rung 2) | `disk_full` | usedPct >= 90 | usedPct < 88 (then `:80` if still >= 80) | `rung, usedPct` |
| `disk:<mount>:95` | critical (rung 3) | `disk_full` | usedPct >= 95 | usedPct < 93 | `rung, usedPct` |
| `disk-forecast:<mount>:14d` | info (rung 1) | `disk_forecast` | days_to_full <= 14 | days > 16.8, or growth stops | `rung, forecastDays` |
| `disk-forecast:<mount>:7d` | warning (rung 2) | `disk_forecast` | days_to_full <= 7 | days > 8.4, or growth stops | `rung, forecastDays` |
| `disk-forecast:<mount>:1d` | critical (rung 3, the page at 1 day) | `disk_forecast` | days_to_full <= 1 | days > 1.2, or growth stops | `rung, forecastDays` |

An open forecast incident is left unchanged while the forecast is `insufficient` (history missing, for example after a state reset); it clears only when the state becomes `flat` or the days rise as above. Events use `kind` `cert_warning` (certificates, including unreadable), `disk_warning` (fullness) and `disk_forecast`, with `severity` equal to the incident's, `target` the path or mount, and params limited to the backend's closed list: `target, rung, daysLeft, notAfter` / `target, rung, usedPct` / `target, rung, forecastDays` (unreadable: `target, rung, error`).

### Blocks in the sync body

- `certs`: `[{path, notAfter (ISO or null), daysLeft (float or null), rung (0-3), pinned (true only for /etc/nginx/ssl/omni.crt), error (null or "unreadable")}]`, pinned certificate first, then `extra_certs` in config order.
- `disks`: `[{mount, paths, usedPct (float), freeBytes (available to users, df Avail), totalBytes, rung, forecast: {state: ok|flat|insufficient, days (float or null), rung}}]`. `mount` is the first configured path of each filesystem; `paths` lists all configured paths on that st_dev.
- State: `state["certs"]` (path -> last entry), `state["disk"]` (mount -> `[[epoch, usedBytes, availBytes], ...]`, one per hour, 8 days), `state["incidents"]`.

## Task Commits

1. **Task 1: Tracer - certificate 14 days out is a rung-1 entry, one event, one incident** - `62eac8aa0` (feat)
2. **Task 2: Disk ladder with hysteresis, filesystem de-duplication, hourly samples, 7-day forecast** - `9e1dbde4d` (feat)
3. **Task 3: Ladder boundaries, expired/unreadable certificates, extra paths, caps, allowance, never-delete guard** - `9c59bc9a5` (test; `warnings.py` needed no change, the branches were already built in Tasks 1 and 2)

**Plan metadata:** committed with this SUMMARY (docs).

## Decisions Made

- See `key-decisions` in the frontmatter. In short: certs and disks capped at 32 entries (backend limit), reads share a 6 s allowance, state saved before the sync, forecast sufficiency judged on the 8 retained days, a timed-out or unreached read keeps the last entry.
- A clock step back by more than 5 minutes discards the new sample (literal reading of Pitfall 7); a clock that stays far behind therefore records no samples until real time catches up. The forecast then reads `insufficient` or uses the older samples; no false alarm results.

## Deviations from Plan

### Orchestrator additions (required, applied)

**1. [Rule 2 - Missing critical functionality] Certificate cap of 32 (orchestrator note 1)**
- **Issue:** `POST /api/internal/watchdog/sync` declares `certs` with `max_length=32`; a longer `extra_certs` list would fail validation for the whole body and the watchdog would look silent.
- **Fix:** `MAX_CERTS = 32` in `warnings.py`, pinned certificate first then `extra_certs` in config order without repeats. The same limit exists for `disks`, so `MAX_DISKS = 32` caps that block too (not named in the note; same failure mode). Backend model unchanged.
- **Verification:** `test_cert_a_long_extra_certs_list_is_capped_at_32_entries_pinned_first` (40 extras give 32 entries and 32 reads, and a full run's body has 32 certs).
- **Committed in:** `62eac8aa0` (code), `9c59bc9a5` (test)

**2. [Rule 2 - Missing critical functionality, safety] Time budget (orchestrator note 2)**
- **Issue:** the unit has `TimeoutStartSec=45` and `restart.POLL_BUDGET` can spend 30 s of a run.
- **Fix:** `READ_TIMEOUT = 3` per openssl read (reduced to what is left of the allowance) and `CERT_BUDGET = 6` for all reads of a run, measured on the `clock` seam. A certificate not reached keeps its last reported entry (state `certs`) and its incident, and is not reported unreadable. Two choices of mine inside that note: (a) a read that times out (exit 124) is treated like "not reached", not like an unreadable file, because a slow read says nothing about the file; (b) an unreached certificate with no earlier entry is left out of the block rather than invented (only possible for an extra certificate on the very first run, because the pinned one is read first).
- **Verification:** fake-clock test with 2.5 s per read: reads are exactly `[PINNED, a, b]` with timeouts `[3, 3, 1.0]`, c and d keep their previous entries and open incidents, no events; the next run catches up.
- **Committed in:** `62eac8aa0`, `9c59bc9a5`

**3. [Rule 2 - Missing critical functionality] Stage order (orchestrator note 3)**
- **Fix:** `warnings.evaluate` runs after `restart.decide` and before the spool append, so warning events share the spool with the restart events. `save_state` (atomic replace) now also runs right after the spool append, before the sync, so incidents are on disk before the network (and the 82-05 paging stage). A killed run leaves the previous `state.json` because `evaluate` only changes the in-memory dict.
- **Verification:** `test_restart_and_warning_events_share_one_spool_so_an_outage_loses_neither` (backend down for two runs, mongod restarted, a 3-day certificate, everything delivered later) and `test_a_run_that_dies_during_the_warning_stage_leaves_the_previous_complete_state` (state.json bytes identical).
- **Committed in:** `62eac8aa0`

### Other deviations and plan-text notes

**4. [Rule 3 - Blocking] Other suites stub the new stage.** `evaluate` would read the real disks and, on the fake hosts' `(0, "")` openssl answer, open an "unreadable" incident in every run-level test of 82-02/82-03. As 82-03 did for `restart.decide`, `test_watchdog_checks.py` and `test_watchdog_sync.py` (autouse) and the `rig` fixture in `_watchdog_restart_world.py` stub `warnings.evaluate`. Not in `files_modified`. The 82-04 suite uses its own `WarnRig` (real stage, fake certificates and disks).

**5. Test layout.** The fake host (`CertRun`, `FakeFs`, `Bench`, `WarnRig`) is in `backend/tests/_watchdog_warnings_world.py` (154 lines) so `test_watchdog_warnings.py` stays under 500 lines (472) while keeping all forecast, disk and "never" tests in the one file the plan's acceptance commands name (`-k forecast` selects 9 tests).

**6. Plan text interpreted.** (a) The truth "at least 7 days between the oldest and newest sample in the last 7 days" cannot hold literally with hourly samples and run jitter (the oldest sample inside a sliding 7-day window would always be a little younger than 7 days, so a forecast would never start). Sufficiency is therefore judged on all retained samples (8 days) and the slope is fitted over the newest 7 days of them; exactly 7 days computes, 7 days minus one second is `insufficient`. (b) Exact 14.0 / 7.0 / 1.0 days are pinned on `forecast_rung`; the end-to-end least-squares test uses an exact linear series and matches 14.0 to 1e-9 rather than bit-for-bit, because float regression is not guaranteed bit-exact.
(c) A tracer/test used a real `openssl req -x509` certificate generated in tmp_path only to feed the read path; no code in `deploy/omni-watchdog` can create one.

**Total deviations:** 3 orchestrator additions (all Rule 2, safety), 1 blocking (suite stubs), plus layout and interpretation notes. **Impact:** no scope change; HEAL-03 and HEAL-04 behave as specified.

## Verification

- `backend/venv/bin/python -m pytest backend/tests/test_watchdog_warnings.py backend/tests/test_watchdog_restart.py backend/tests/test_watchdog_restart_order.py backend/tests/test_watchdog_checks.py backend/tests/test_watchdog_sync.py backend/tests/test_watchdog_artifacts.py -q -p no:cacheprovider`: 168 passed.
- Acceptance greps: `cert_time_to_seconds` 1 line, `"-enddate"` 1 line, `grep -rn "certbot\|genrsa\|req -new" deploy/omni-watchdog` prints nothing, `warnings.py` is 320 lines.
- No real certificate or disk was read by any test; nothing was installed or restarted; no MongoDB was touched. One read-only `statvfs` of `/` was made by hand to confirm the real `RealFs` works (69 percent used on this VM).

## Known Stubs

None.

## Threat Flags

None. The module adds no network endpoint; its only host access is the read-only `openssl x509 -noout -enddate -in <path>` (path as one argv element, no shell) and `statvfs`/`stat`, as the plan's T-82-13..15 mitigations require.

## Issues Encountered

- The plan's tasks marked `tdd="true"` were built test-with-code per task (one commit each, as in 82-03), not as separate RED and GREEN commits; the module did not exist before Task 1, so there was no meaningful isolated RED.
- HEAL-03 and HEAL-04 are shared with plan 82-08; see the requirements note in the metadata commit step.

## Next Phase Readiness

Ready for 82-05 (pages the incidents in the table above; the resolve is sent when `clearedAt` is set) and 82-08 (renders the `certs` and `disks` blocks and the three event kinds). End-of-phase operator step outstanding: after installing per INSTALL.md, confirm on the server that the real certificate and the `/` + `/var/lib/mongodb` disk entry show up in the sync.

## Self-Check: PASSED

Files exist (`warnings.py`, `_watchdog_warnings_world.py`, `test_watchdog_warnings.py`, `run.py`); commits `62eac8aa0`, `9e1dbde4d`, `9c59bc9a5` are ancestors of HEAD.
