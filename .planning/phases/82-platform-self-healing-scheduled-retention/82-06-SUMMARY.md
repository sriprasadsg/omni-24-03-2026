---
phase: 82-platform-self-healing-scheduled-retention
plan: 06
subsystem: infra
tags: [systemd, polkit, watchdog, install-checklist, node-harness]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "plan 82-01 ingest token via CREDENTIALS_DIRECTORY/omni-watchdog-token; plan 82-02 watchdog package, entry script omni-watchdog.py, config keys and state paths"
provides:
  - "deploy/omni-watchdog/systemd/: hardened Type=oneshot omni-watchdog.service (User=omni-watchdog, TimeoutStartSec=45) and omni-watchdog.timer (60 s)"
  - "deploy/omni-watchdog/polkit/49-omni-watchdog.rules: restart/start/reset-failed of mongod, omni-backend, nginx for omni-watchdog only; ES5"
  - "Drop-ins under new file names only: omni-backend 10-omni-watchdog.conf (LoadCredential), mongod and nginx 50-omni-restart.conf (Restart=on-failure, RestartSec=5s)"
  - "etc/watchdog.conf.example and etc/oncall.env.example (no secrets)"
  - "deploy/omni-watchdog/INSTALL.md operator checklist (path returned as installChecklist.path by 82-08)"
  - "backend/tests/polkit_rule_harness.js and backend/tests/test_watchdog_artifacts.py"
affects: [82-08 install checklist endpoint, 82-05 verification, operator install of the watchdog]

actuals:
  tokens: 9500
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Install files are repo-only artifacts; tests copy units to a temp dir for systemd-analyze and evaluate the polkit rule with a stub polkit object, never touching the host"
    - "Structural guard tests that the app installs nothing (start-all-services.sh and Phase 82 backend modules)"

key-files:
  created:
    - deploy/omni-watchdog/systemd/omni-watchdog.service
    - deploy/omni-watchdog/systemd/omni-watchdog.timer
    - deploy/omni-watchdog/systemd/omni-backend.service.d/10-omni-watchdog.conf
    - deploy/omni-watchdog/systemd/mongod.service.d/50-omni-restart.conf
    - deploy/omni-watchdog/systemd/nginx.service.d/50-omni-restart.conf
    - deploy/omni-watchdog/polkit/49-omni-watchdog.rules
    - deploy/omni-watchdog/etc/watchdog.conf.example
    - deploy/omni-watchdog/etc/oncall.env.example
    - deploy/omni-watchdog/INSTALL.md
    - backend/tests/polkit_rule_harness.js
    - backend/tests/test_watchdog_artifacts.py
  modified: []

key-decisions:
  - "No ConfigurationDirectory= in the unit: INSTALL.md creates /etc/omni-watchdog root:omni-watchdog 0750 so systemd cannot reset its owner and mode"
  - "polkit rule UNITS omits ollama.service; INSTALL.md documents the one-line addition plus ollama_expected = true"
  - "The harness is an ES module (.js) because the repository root package.json sets type module"
  - "Structural 'installs nothing' test skips modules that later Phase 82 plans create (4 of 7 exist today); 82-05's verification re-runs this file when all exist"

patterns-established:
  - "Operator-owned install: files ship in deploy/, INSTALL.md names every one with destination, owner and mode, and the code never installs them"

requirements-completed: [HEAL-08, HEAL-01]

coverage:
  - id: D1
    description: "omni-watchdog.service and .timer: Type=oneshot as omni-watchdog, TimeoutStartSec=45, hardening keys, 60 s cadence, no RuntimeMaxSec, systemd-analyze verify clean"
    requirement: HEAL-08
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_artifacts.py#test_systemd_analyze_verify_is_clean_for_service_and_timer"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_artifacts.py#test_service_is_a_hardened_oneshot_run_as_the_watchdog_user"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_artifacts.py#test_timer_fires_every_minute_and_is_wanted_by_timers_target"
        status: pass
    human_judgment: false
  - id: D2
    description: "polkit rule grants YES only to omni-watchdog for restart/start/reset-failed of three units; NO for every other systemd1 action or detail; NOT_HANDLED otherwise; ES5 only"
    requirement: HEAL-01
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_artifacts.py#test_polkit_rule_harness_passes_every_case"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_artifacts.py#test_polkit_rule_uses_ecmascript_5_only"
        status: pass
    human_judgment: false
  - id: D3
    description: "Drop-ins use new file names, set no Environment=, never touch kernel-rseq-check.conf; example configs parse with the 82-02 loaders and hold no secret"
    requirement: HEAL-08
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_artifacts.py (drop-in and example-file tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "INSTALL.md names every shipped file with its destination and covers run-on-ubuntu.sh, pkcheck, the mongod before/after diff, HEARTBEAT_URL, STOP, Ollama and the first retention count (D-15)"
    requirement: HEAL-08
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_artifacts.py#test_install_checklist_names_every_shipped_file_with_its_destination"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_artifacts.py#test_install_checklist_covers_the_safety_steps"
        status: pass
    human_judgment: false
  - id: D5
    description: "The app installs nothing: start-all-services.sh never mentions the watchdog or polkit; existing Phase 82 backend modules use no systemctl, subprocess or /etc writes"
    requirement: HEAL-08
    verification:
      - kind: unit
        ref: "backend/tests/test_watchdog_artifacts.py#test_start_all_services_does_not_know_about_the_watchdog"
        status: pass
      - kind: unit
        ref: "backend/tests/test_watchdog_artifacts.py#test_phase_82_backend_modules_install_nothing (3 of 7 modules exist; 4 skipped until created)"
        status: pass
    human_judgment: false
  - id: D6
    description: "On a real server the checklist works: polkit allows nginx.service restart and refuses ssh.service (assumption A-82-A3), systemctl reaches the bus under the unit hardening (A-82-A4), the mongod drop-in diff shows only the added block"
    verification: []
    human_judgment: true
    rationale: "Installing on the live server is the operator's step; the app and this plan install nothing. INSTALL.md steps 5, 6 and 8 are the proof, run at end of phase."

duration: 5min
completed: 2026-10-27
status: complete
plan_head_before: 0e935071ad12f527404ebaa1b417410f43e0244a
plan_head_after: 603f951533af0b8f294001c242862106c95c087b
commits: 3
---

# Phase 82 Plan 06: Watchdog install files and checklist Summary

**Hardened oneshot unit and 60 s timer, a polkit rule limited to three units and three verbs and proven by a node harness, non-clobbering drop-ins, example configs and a 12-step operator INSTALL.md, with tests proving the app installs nothing**

## Performance

- **Duration:** 5 min
- **Started:** 2026-10-27T08:23:22Z
- **Completed:** 2026-10-27T08:28:00Z
- **Tasks:** 3
- **Files modified:** 11 (all new)

## Accomplishments
- `omni-watchdog.service` (Type=oneshot, `User=omni-watchdog`, `TimeoutStartSec=45`, `StateDirectory`, NoNewPrivileges, ProtectSystem=strict, ProtectHome, PrivateTmp, address-family restriction, empty capability set, UMask 0077) running the root-owned `/usr/local/lib/omni-watchdog/omni-watchdog.py`; `omni-watchdog.timer` with OnBootSec/OnUnitActiveSec 60 and AccuracySec 5s.
- Polkit rule `49-omni-watchdog.rules` (ES5, type-guarded) and a stub-polkit node harness covering 22 cases.
- Backend credential drop-in plus optional mongod/nginx `Restart=on-failure` drop-ins under new names only; `kernel-rseq-check.conf` is never touched and no shipped file sets `Environment=`.
- `INSTALL.md`: user, root-owned script, `/etc/omni-watchdog` root:omni-watchdog 0750 with 0640 secrets, token generation, drop-ins with the `systemctl cat mongod` before/after diff, polkit install with two `pkcheck` commands (allowed nginx.service, refused ssh.service), Ollama one-liner, timer, hardening relaxation order (A4), heartbeat, STOP file, first retention count (D-15), uninstall.

## Verification output

`systemd-analyze verify` over copies of the service and timer in a temp dir: no output, exit 0 (no RuntimeMaxSec message).

Polkit harness (expected / actual, all equal, exit 0):

| Case | Expected | Actual |
|------|----------|--------|
| omni-watchdog x {mongod, omni-backend, nginx}.service x {restart, start, reset-failed} (9 cases) | YES | YES |
| stop; kill; ssh.service; ollama.service (default); unit without suffix | NO | NO |
| missing unit detail; missing verb detail; non-string detail | NO | NO |
| manage-unit-files; reload-daemon (other systemd1 action) | NO | NO |
| azureuser restart nginx; omni-watchdog login1.reboot; azureuser login1.reboot | NOT_HANDLED | NOT_HANDLED |

`backend/venv/bin/python -m pytest backend/tests/test_watchdog_artifacts.py`: 18 passed, 4 skipped (the four Phase 82 backend modules not yet created: `autonomous_ops/oncall.py`, `retention_gate.py`, `retention_job.py`, `autonomous_ops_retention_endpoints.py`). Acceptance greps: RuntimeMaxSec 0, ConfigurationDirectory 0, `Environment=` 0 in every file, ES5 lint 0, `start-all-services.sh` 0 mentions, `pkcheck` 4 mentions in INSTALL.md.

## Task Commits

1. **Task 1: Tracer - service and timer pass systemd-analyze verify** - `9629518ca` (feat)
2. **Task 2: Polkit rule and harness, drop-ins, example configs** - `2721219ff` (feat)
3. **Task 3: INSTALL.md and installs-nothing guards** - `603f95153` (docs)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

_Tasks were test-first: each task's tests were run before its files existed (4, 8 and 2 failures from missing artifacts), then the artifacts made them pass. Test and artifact share one commit per task as the plan's per-task commit rule asks._

## Files Created/Modified
- `deploy/omni-watchdog/systemd/*` - unit, timer and three drop-ins
- `deploy/omni-watchdog/polkit/49-omni-watchdog.rules` - the privilege allowlist
- `deploy/omni-watchdog/etc/*.example` - config examples
- `deploy/omni-watchdog/INSTALL.md` - operator checklist
- `backend/tests/polkit_rule_harness.js`, `backend/tests/test_watchdog_artifacts.py` - proof without installing

## Decisions Made
- No `ConfigurationDirectory=`: the checklist owns `/etc/omni-watchdog` so the watchdog user can read but never write its config.
- Ollama is absent from the rule by default; INSTALL.md gives the one-line addition and the matching `ollama_expected = true`.
- The structural installs-nothing test skips not-yet-created modules with a reason; it covers all seven once they exist.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Harness written as an ES module**
- **Found during:** Task 2
- **Issue:** the repository root `package.json` sets `"type": "module"`, so a CommonJS `require` in `backend/tests/polkit_rule_harness.js` threw `require is not defined`.
- **Fix:** switched to `import fs/vm/process from "node:..."`; file name unchanged as the plan requires.
- **Files modified:** backend/tests/polkit_rule_harness.js
- **Verification:** `node backend/tests/polkit_rule_harness.js ...` exits 0.
- **Committed in:** 2721219ff

**2. [Rule 1 - Bug] Comments contained strings the acceptance greps forbid**
- **Found during:** Tasks 1 and 2
- **Issue:** comments in the unit mentioned `RuntimeMaxSec` and `ConfigurationDirectory`, and one in the rule contained "let " (ES5 lint), making the plan's `grep -c` criteria non-zero.
- **Fix:** reworded the comments; behavior unchanged.
- **Committed in:** 9629518ca, 2721219ff

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug in comments)
**Impact on plan:** No scope change.

## Issues Encountered
None. Per the environment constraints nothing was installed, enabled or run on the host; `pkcheck`, `systemctl` and `sudo` were never invoked.

## User Setup Required
Operator install on the server (not done and not doable by the app): follow `deploy/omni-watchdog/INSTALL.md`, then the two `pkcheck` commands in step 6 (allowed for nginx.service restart, refused for ssh.service) and the mongod before/after diff in step 5. Assumptions A-82-A3 (unit detail suffix) and A-82-A4 (systemctl under ProtectSystem=strict) stay unverified until that run.

## Next Phase Readiness
- 82-08 can return `deploy/omni-watchdog/INSTALL.md` as `installChecklist.path`.
- Re-run `backend/tests/test_watchdog_artifacts.py` when the remaining four Phase 82 backend modules exist (82-05 verification) so their skips become checks.

## Self-Check: PASSED

All 11 created files exist; commits 9629518ca, 2721219ff and 603f95153 are on the branch; the plan-level verification (harness, pytest) passes.

---
*Phase: 82-platform-self-healing-scheduled-retention*
*Completed: 2026-10-27*
