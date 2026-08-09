---
phase: 47-agent-scoped-geo-security-detectors
plan: 02
subsystem: backend-detectors
tags: [geo-security, impossible-travel, geo-fence, dedup, ueba, tdd]
dependency-graph:
  requires:
    - "ueba_service.persist_security_alert (47-01, alias, imported by 47-03 only)"
    - "ueba_service._haversine_km (existing, reused verbatim)"
  provides:
    - "geo_security_service.evaluate_impossible_travel"
    - "geo_security_service.evaluate_geo_fence"
    - "geo_security_service.get_geo_security_settings"
    - "geo_security_service.dedup_and_maybe_alert"
    - "geo_security_service.run_geo_security_detectors"
  affects:
    - "backend/agent_heartbeat_endpoints.py (47-03 wires the orchestrator in)"
    - "backend/geo_security_endpoints.py (later plan — admin config surface)"
tech-stack:
  added: []
  patterns:
    - "tenant -> global -> hardcoded-default system_settings resolution (cloned from get_track_agent_location / get_sla_at_risk_window)"
    - "shadow-field dedup/cooldown state on the agents doc (geoSecurityState.<type>.{violating,lastAlertedAt}) — zero extra reads"
    - "pure boolean-returning detector functions, orchestrator returns alert payloads rather than calling the persistence layer directly"
key-files:
  created:
    - backend/geo_security_service.py
    - backend/tests/test_geo_security_service.py
  modified: []
decisions:
  - "Impossible-travel and geo-fence evaluate against RAW existing_agent.geo/lastSeen, never Phase 46's debounced locationConfirmed/locationPending shadow fields (Pitfall 2)"
  - "vpn_heuristic suppression checks `is True` only — None/False never suppress (Pitfall 5, D-02)"
  - "MIN_ELAPSED_MINUTES=15 floor applied before the speed check, independent of the VPN suppression path (D-08)"
  - "Cooldown re-fires after 6h if still violating (D-07) rather than firing exactly once per transition forever"
  - "run_geo_security_detectors returns alert payload dicts; it never imports or calls the alert-persistence fan-out itself, keeping 47-03's heartbeat wiring the sole caller"
metrics:
  duration: "~25 minutes"
  completed: 2026-07-29
status: complete
---

# Phase 47 Plan 02: Agent-Scoped Geo Security Detector Core Summary

Built the pure detector + dedup + config core (`backend/geo_security_service.py`) for agent-scoped impossible-travel (GSEC-02) and country-code geo-fence (GSEC-03) as a hermetically-tested sibling module to `agent_heartbeat_endpoints.py`, reusing `ueba_service._haversine_km` and `system_settings`'s tenant->global->default resolution pattern rather than inventing new infrastructure.

## What Was Built

- **`evaluate_impossible_travel(prev_geo, prev_last_seen_iso, curr_geo, now, prev_vpn, curr_vpn) -> bool`** — haversine distance ÷ elapsed hours > 1000 km/h (D-01), guarded by: missing prior/lat-long state → False (first check-in), either endpoint's `vpn_heuristic is True` → False (D-02, full suppression), clock skew (elapsed ≤ 0) → False, elapsed < 15 minutes → False (D-08 noise floor).
- **`evaluate_geo_fence(country_code, allowlist) -> bool`** — case-insensitive ISO 3166 alpha-2 allowlist check (D-03); empty allowlist or missing country_code never fires.
- **`get_geo_security_settings(db, tenant_id) -> dict`** — tenant doc → global doc → hardcoded default (`impossible_travel_enabled: True`, `geo_fence_enabled: False`, `allowed_country_codes: []`), cloned from `get_track_agent_location`/`get_sla_at_risk_window`'s 3-step resolution.
- **`dedup_and_maybe_alert(raw_db, agent_id, existing_agent, violation_type, violating) -> bool`** — shadow field `geoSecurityState.<violation_type>.{violating,lastAlertedAt}` on the `agents` doc; fires once on clean→violating transition, suppresses within the 6h cooldown, re-fires after the cooldown elapses if still violating (D-05/D-07), clears state on a clean call.
- **`run_geo_security_detectors(db, existing_agent, agent_id, tenant_id, curr_geo, now) -> list[dict]`** — toggle-gated orchestrator that reads the RAW prior `existing_agent.geo`/`existing_agent.lastSeen` (never the debounced `locationConfirmed`), evaluates both detectors, dedups, and returns a list of alert payload dicts (`alert_type`/`severity`/`title`/`description`/`metadata`) for 47-03's heartbeat wiring to persist. Performs no DB alert writes and no connection mutation itself.

## Task Execution

1. **Task 1 (RED)** — `backend/tests/test_geo_security_service.py` written first with 24 hermetic tests covering every required behavior (impossible_travel_positive/below_speed, vpn_suppression x2, vpn_none_handling x2, first_checkin x2, elapsed_floor x2, clock_skew x2, geo_fence_violation/clean x6, config_resolution x4, dedup_cooldown x2). Confirmed RED: all 24 failed on `ModuleNotFoundError`/`AttributeError` before any implementation existed. Commit `a7321a9`.
2. **Task 2 (GREEN, partial)** — implemented `evaluate_impossible_travel`, `evaluate_geo_fence`, `get_geo_security_settings`. Ran the plan's exact `-k` filter (`impossible_travel or vpn or first_checkin or elapsed or clock or geo_fence or config_resolution`) — 22/22 passed; the 2 dedup tests remained correctly RED (function didn't exist yet). Commit `6bc6d59`.
3. **Task 3 (GREEN, full)** — implemented `dedup_and_maybe_alert` and `run_geo_security_detectors`. Full suite: 24/24 passed. Structural verification: `grep -c "persist_security_alert" geo_security_service.py` → 0 (no import, no call — confirmed by rewording two docstring mentions that would otherwise have false-positived the grep, since the code itself never referenced the name); `grep -n "_haversine_km"` confirms the import from `ueba_service` (never re-copied); module is 278 lines (well under the 500-line cap). Commit `f649ec7`.

## Verification

- `backend/venv/bin/python -m pytest backend/tests/test_geo_security_service.py -q` → **24 passed**.
- Full backend suite (excluding `test_graphql.py`, a pre-existing unrelated `strawberry`/`pydantic` import incompatibility): **1408 passed, 6 failed, 35 skipped**. The 6 failures reproduce identically with `backend/tests/test_geo_security_service.py` excluded from the run (verified directly), confirming all 6 are pre-existing and unrelated to this plan:
  - 3 already-known baseline fails (per project memory: e2e golden-path evidence, rust heartbeat parity, agentic `tool_choice`).
  - 3 in `test_support_admin_to_user.py` — an order-dependent flake that passes in isolation (`pytest tests/test_support_admin_to_user.py -q` → 3 passed) and reproduces identically without any of this plan's files present, matching the same class of pre-existing test-order pollution noted in STATE.md for `test_auth_mfa.py` in an earlier session.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reworded 2 docstring passages to avoid tripping the plan's own literal-string grep verification**
- **Found during:** Task 3 verification (`grep -c "persist_security_alert" backend/geo_security_service.py` returned 4, not the required 0).
- **Issue:** Explanatory docstring prose (module docstring + two function docstrings) mentioned `ueba_service.persist_security_alert`/`persist_security_alert` by name to explain *why* the module never imports or calls it — technically correct in intent, but the plan's `<verification>` grep is a literal string count with no code-vs-comment distinction.
- **Fix:** Reworded the three docstring passages to say "the alert fan-out" / "the alert-persistence alias" instead of spelling out the literal function name, preserving the exact same meaning without changing any executable code.
- **Files modified:** `backend/geo_security_service.py` (docstrings only, no logic change).
- **Commit:** `f649ec7` (included in the Task 3 commit, verified before committing).

No other deviations — plan executed as written; no architectural changes, no new packages, no missing critical functionality found.

## Self-Check: PASSED

- `backend/geo_security_service.py` — FOUND (278 lines).
- `backend/tests/test_geo_security_service.py` — FOUND.
- Commit `a7321a9` — FOUND in `git log --oneline`.
- Commit `6bc6d59` — FOUND in `git log --oneline`.
- Commit `f649ec7` — FOUND in `git log --oneline`.
