---
phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
plan: 02
subsystem: api
tags: [mongodb, append-only-audit, nat-flip-denoise, state-machine, tenant-toggle]

# Dependency graph
requires: []
provides:
  - "backend/agent_location_history_service.py — get_track_agent_location(db, tenant_id) + record_location_change(db, existing_agent, agent_id, tenant_id, public_ip, geo, asn_enrichment, now=None); locationConfirmed/locationPending agent-doc shadow fields; agent_location_history append-only collection"
  - "backend/migrations/003_agent_location_history_indexes.py — compound (agent_id, tenantId, timestamp) + standalone timestamp indexes on agent_location_history"
affects: [46-03, 46-04, 46-05, 46-06, 46-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "4-branch NAT-flip de-noise state machine over agent-doc shadow fields (locationConfirmed/locationPending), rather than diffing the raw agents.publicIp field that's overwritten every heartbeat regardless of whether a history row was written"
    - "Per-tenant system_settings toggle lookup (tenant -> global -> hardcoded default), cloned verbatim from compliance_remediation_sla_service.get_sla_at_risk_window()"
    - "Append-only audit collection: insert_one only, no update/delete/replace path, enforced by grep gate absence rather than a DB-level constraint"

key-files:
  created:
    - backend/tests/test_agent_location_history.py
    - backend/agent_location_history_service.py
    - backend/migrations/003_agent_location_history_indexes.py

key-decisions:
  - "DEBOUNCE_WINDOW locked at timedelta(minutes=10) (Claude's Discretion per CONTEXT.md D-06) — matches the stated NAT-lease-flip timescale; exported as a module constant so both the implementation and its tests read the same value"
  - "record_location_change() itself calls get_track_agent_location() internally (rather than requiring every caller to check the toggle first) — the must_haves truth 'when it returns False the record path is a no-op' is satisfied at the single call boundary the 46-05 heartbeat wiring will use"
  - "A candidate matching the confirmed baseline (branch 1) actively clears any stale locationPending via a dedicated agents.update_one — this is what makes an A->B->A flip-flop discard B's dwell time instead of letting it silently keep accumulating toward a future incorrect promotion"
  - "No dwell-time field is stored on agent_location_history rows — GAUD-02's dwell-time display is a read-time computation deferred to the GET endpoint (46-04/46-06), never persisted per Pitfall 2"
  - "Migration file follows 002_scale_indexes.py's MIGRATION_ID/DESCRIPTION/async up(db) convention (not the runner.py docstring's stale VERSION-attribute wording) — the runner discovers version purely from the NNN_ filename prefix via regex, never reads a module attribute for it"

requirements-completed: [GAUD-01]

coverage:
  - id: D1
    description: "A publicIp OR resolved city/country change vs the last confirmed location writes exactly one new agent_location_history row"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history.py::TestChangeDetection"
        status: pass
    human_judgment: false
  - id: D2
    description: "A public IP that flip-flops A->B->A within the debounce window never promotes B to a written row"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history.py::TestDenoise::test_denoise_flip_flop_a_b_a_never_writes"
        status: pass
    human_judgment: false
  - id: D3
    description: "Two genuine changes spaced further apart than the debounce window each write exactly one row"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history.py::TestDenoise::test_denoise_two_genuine_changes_each_write_one_row"
        status: pass
    human_judgment: false
  - id: D4
    description: "agent_location_history.timestamp is inserted as a native datetime (BSON Date), never an ISO string"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history.py::TestBsonDate"
        status: pass
      - kind: grep
        ref: "grep -n 'isoformat' backend/agent_location_history_service.py (returns nothing)"
        status: pass
    human_judgment: false
  - id: D5
    description: "get_track_agent_location resolves per-tenant -> global -> default True; when False the record path is a no-op"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_location_history.py::TestToggle"
        status: pass
    human_judgment: false
  - id: D6
    description: "record_location_change never mutates or deletes any existing agent_location_history row"
    requirement: "GAUD-01"
    verification:
      - kind: grep
        ref: "grep -nE 'agent_location_history\\.(update|delete|replace|find_one_and)' backend/agent_location_history_service.py (returns nothing)"
        status: pass
    human_judgment: false
  - id: D7
    description: "003 migration creates the compound + timestamp indexes with no auto-expiring (TTL) index"
    requirement: "GAUD-01"
    verification:
      - kind: grep
        ref: "grep -nE 'expireAfterSeconds|TTL' backend/migrations/003_agent_location_history_indexes.py (returns nothing)"
        status: pass
      - kind: automated
        ref: "python -c \"import ast; ast.parse(open('migrations/003_agent_location_history_indexes.py').read())\""
        status: pass
    human_judgment: false

duration: ~35min
completed: 2026-07-29
status: complete
---

# Phase 46 Plan 02: Location-History Change-Detection Service Summary

**`agent_location_history_service.py` — the 4-branch NAT-flip de-noise state machine that decides when a public-IP/geo change is real enough to append an immutable `agent_location_history` row, plus the per-tenant `track_agent_location` toggle**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-29
- **Tasks:** 3/3 completed
- **Files modified:** 3 (all new)

## Accomplishments

- `backend/agent_location_history_service.py`: `get_track_agent_location(db, tenant_id)` (tenant → global → default-True `system_settings` lookup, cloned verbatim from `compliance_remediation_sla_service.get_sla_at_risk_window()`) and `record_location_change(db, existing_agent, agent_id, tenant_id, public_ip, geo, asn_enrichment, now=None)` implementing the 4-branch de-noise state machine over two new agent-doc shadow fields (`locationConfirmed`/`locationPending`) — never diffing the raw `agents.publicIp` field, which is overwritten every heartbeat regardless of whether a history row was written.
- First-ever observation (no `locationConfirmed`) promotes immediately. A candidate matching the confirmed baseline is a no-op and actively discards any stale pending candidate (this is what collapses an A→B→A flip-flop — B never accumulates enough dwell time before the agent flips back to A). A candidate matching the current pending candidate promotes once `DEBOUNCE_WINDOW` (10 minutes) has elapsed. Any other new candidate resets the pending window.
- Compares `publicIp` AND resolved `city`/`country` (D-05) — a same-IP geo change still counts as a change and eventually writes a row through the same debounce pipeline.
- Every write is `insert_one` only; `timestamp` is a native `datetime.now(timezone.utc)` object, never `.isoformat()`'d.
- `backend/tests/test_agent_location_history.py`: 11 hermetic tests (`TestChangeDetection`, `TestDenoise`, `TestToggle`, `TestBsonDate`) using a hand-rolled `AsyncMock`-backed fake db plus a small `_apply_agent_update()` helper that threads shadow-field state between successive `record_location_change()` calls exactly as a real heartbeat's re-fetched `existing_agent` would.
- `backend/migrations/003_agent_location_history_indexes.py`: compound `(agent_id, tenantId, timestamp)` index for the tenant-scoped GET-by-agent timeline read (GAUD-02), plus a standalone `timestamp` index for the 365-day retention `$lt` sweep. Deliberately no auto-expiring index — retention is the app-level `cleanup_agent_location_history()` sweep (46-03), not a competing Mongo mechanism.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write change-detection + de-noise + toggle test scaffold** — `8728e33` (test)
2. **Task 2: Implement agent_location_history_service.py** — `b591df2` (feat)
3. **Task 3: Add 003 index migration for agent_location_history** — `3e93cd0` (feat)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Replaced an orphaned, untracked draft of `agent_location_history_service.py` found already present in the working tree**
- **Found during:** Task 1 (writing the test scaffold surfaced a `TypeError` instead of the expected `ImportError`, revealing the module already existed)
- **Issue:** An untracked `backend/agent_location_history_service.py` was already present at session start (not from git history — `git log` shows zero commits touching it, `git status` showed `??`). It used a single `agent_doc` parameter instead of the plan's required `(db, existing_agent, agent_id, tenant_id, public_ip, geo, asn_enrichment, now=None)` signature, had no deterministic `now` override (real `datetime.now()` calls throughout, making the debounce window untestable), never called `agents.update_one` to actually persist the shadow-field updates, used `agentId`/`db[collection]` instead of this codebase's `agent_id`/`raw = db._db if hasattr(db, "_db") else db` conventions, and had a logic bug in its same-IP-different-geo branch that wrote a history row immediately without going through the debounce window at all.
- **Fix:** Rewrote the file from scratch to match the plan's exact function signatures and the `compliance_remediation_sla_service.py` conventions (raw-db unwrap, shadow-field `$set`/`$unset` via `agents.update_one`, `now` parameter for deterministic testing).
- **Files modified:** `backend/agent_location_history_service.py`
- **Commit:** `b591df2`

**2. [Rule 3 - Blocking] Reworded two anti-pattern explanations in comments/docstrings to avoid tripping their own literal grep gates**
- **Found during:** Task 2 and Task 3 verification
- **Issue:** The plan's acceptance criteria include `grep -n 'isoformat'` (service file) and `grep -nE 'expireAfterSeconds|TTL'` (migration file) gates intended to catch actual code usage of those anti-patterns. My own explanatory docstrings/comments describing *why* those anti-patterns must be avoided contained the literal substrings ("isoformat", "TTL", "expireAfterSeconds"), tripping the gates on prose, not code.
- **Fix:** Reworded the explanatory text ("string-formatted" instead of "`.isoformat()`'d", "auto-expiring index" instead of "TTL index") without changing the technical meaning.
- **Files modified:** `backend/agent_location_history_service.py`, `backend/migrations/003_agent_location_history_indexes.py`
- **Commit:** `b591df2`, `3e93cd0`

## Full Suite Regression Check

`backend/venv/bin/python -m pytest tests/ -q --ignore=tests/test_graphql.py` (excluding `test_graphql.py`, which fails at collection due to a pre-existing, unrelated `strawberry`/`pydantic` version incompatibility in this environment, not touched by this plan):

**1363 passed / 35 skipped / 6 failed.** All 6 failures confirmed pre-existing and unrelated to this plan's 3 new files:
- `test_agentic_ai.py::TestRunCallsAnthropicWithToolChoiceAny`, `test_e2e_integration.py::test_golden_path_evidence_to_remediation`, `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls` — the project's documented pre-existing baseline (per memory: e2e evidence, rust parity, agentic tool_choice).
- `test_support_admin_to_user.py` (3 failures, `RuntimeError: There is no current event loop in thread 'MainThread'`) — confirmed order-dependent full-suite flake, not a real regression: `venv/bin/python -m pytest tests/test_support_admin_to_user.py -q` run in isolation passes 3/3.

No new failures attributable to `agent_location_history_service.py`, its test file, or the 003 migration.

## Self-Check: PASSED

- `backend/agent_location_history_service.py` — FOUND
- `backend/tests/test_agent_location_history.py` — FOUND
- `backend/migrations/003_agent_location_history_indexes.py` — FOUND
- Commit `8728e33` — FOUND
- Commit `b591df2` — FOUND
- Commit `3e93cd0` — FOUND
