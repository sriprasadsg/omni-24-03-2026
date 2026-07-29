---
phase: 47-agent-scoped-geo-security-detectors
plan: 04
subsystem: api
tags: [fastapi, pydantic, mongodb, system_settings, admin-gate, iso-3166]

requires:
  - phase: 47-agent-scoped-geo-security-detectors (plan 02)
    provides: geo_security_service.get_geo_security_settings (tenant -> global -> default resolution) and the detector config shape (impossible_travel_enabled, geo_fence_enabled, allowed_country_codes)
provides:
  - Admin-gated GET/PATCH /api/settings/geo-security config surface
  - Pydantic-boundary ISO 3166 alpha-2 validation for allowed_country_codes
  - Router registration in router_registry.py
affects: [47-06 (Security settings panel frontend consumes this API)]

tech-stack:
  added: []
  patterns:
    - "Admin-gated GET/PATCH toggle endpoint pair cloned from agent_location_history_endpoints.py (tenant vs global $exists upsert branches)"
    - "Pydantic field_validator normalizes+validates a list field at the API boundary before it ever reaches storage"

key-files:
  created:
    - backend/geo_security_endpoints.py
    - backend/tests/test_geo_security_endpoints.py
  modified:
    - backend/router_registry.py

key-decisions:
  - "PATCH re-reads via get_geo_security_settings after the upsert and returns that resolved dict, rather than echoing the raw request body, so the response always reflects actual persisted+resolved state"
  - "allowed_country_codes validation lives in a Pydantic field_validator on GeoSecuritySettingsUpdate (uppercase-normalize, reject non-2-letter/non-alpha) rather than deferring to geo_security_service, since this is the API input boundary (D-03/T-47-04-T)"

patterns-established:
  - "New admin-settings surfaces clone agent_location_history_endpoints.py's _SETTINGS_ADMIN_ROLES/_require_admin/tenant-vs-global upsert shape verbatim rather than re-deriving it"

requirements-completed: [GSEC-02, GSEC-03]

coverage:
  - id: D1
    description: "GET /api/settings/geo-security returns tenant-resolved detector settings"
    requirement: "GSEC-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_geo_security_endpoints.py#TestGetReturnsDefaults::test_get_returns_hardcoded_defaults_when_no_doc_stored"
        status: pass
    human_judgment: false
  - id: D2
    description: "PATCH /api/settings/geo-security persists a tenant-scoped system_settings doc (type geo_security_detectors)"
    requirement: "GSEC-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_geo_security_endpoints.py#TestPatchPersists::test_patch_persists_tenant_scoped_system_settings_doc"
        status: pass
    human_judgment: false
  - id: D3
    description: "Non-admin PATCH is rejected with 403 (admin gate, D-06)"
    verification:
      - kind: unit
        ref: "backend/tests/test_geo_security_endpoints.py#TestAdminGate::test_admin_gate_non_admin_patch_forbidden"
        status: pass
    human_judgment: false
  - id: D4
    description: "allowed_country_codes rejects malformed input (non-ISO-3166-alpha-2) and normalizes lowercase to uppercase"
    requirement: "GSEC-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_geo_security_endpoints.py#TestValidationRejectsBadCountry::test_patch_rejects_three_letter_country_code"
        status: pass
      - kind: unit
        ref: "backend/tests/test_geo_security_endpoints.py#TestValidationNormalizesCase::test_patch_normalizes_lowercase_codes_to_uppercase"
        status: pass
    human_judgment: false
  - id: D5
    description: "Router registered in router_registry.py so the routes resolve in the running app"
    verification:
      - kind: unit
        ref: "grep -n geo_security_endpoints backend/router_registry.py"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-29
status: complete
---

# Phase 47 Plan 04: Geo-Security Settings Endpoints Summary

**Admin-gated GET/PATCH `/api/settings/geo-security` cloning the proven `agent_location_history_endpoints.py` toggle pattern, with Pydantic-boundary ISO 3166 alpha-2 validation on the allowed-country allowlist**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-29T13:34:25Z
- **Tasks:** 2
- **Files modified:** 3 (1 created: `geo_security_endpoints.py`; 1 created: test file; 1 modified: `router_registry.py`)

## Accomplishments
- `backend/geo_security_endpoints.py`: admin-gated `GET`/`PATCH /api/settings/geo-security`, cloning `_SETTINGS_ADMIN_ROLES`/`_require_admin` and the tenant-vs-global `system_settings` upsert branches verbatim from `agent_location_history_endpoints.py`
- `GeoSecuritySettingsUpdate` Pydantic model validates `allowed_country_codes` as ISO 3166 alpha-2 at the API boundary (uppercase-normalizes valid 2-letter codes, raises `ValueError` — surfaced as 422 — on anything else)
- Router registered in `router_registry.py` immediately after `agent_location_history_endpoints`
- 5 endpoint tests covering admin-gate, default resolution, tenant-scoped persistence, and both validation paths (rejection + normalization)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing endpoint tests (admin gate, validation, tenant scope)** - `9134bbe` (test)
2. **Task 2: Implement geo_security_endpoints.py and register the router** - `9b48750` (feat)

**Plan metadata:** (this commit)

_Note: Task 2's commit also includes a one-line test-mock fix (see Deviations) since it surfaced only once the real implementation exercised the read-back path._

## Files Created/Modified
- `backend/geo_security_endpoints.py` - New admin-gated GET/PATCH settings endpoints; `GeoSecuritySettingsUpdate` validation model
- `backend/router_registry.py` - Added `_load(app, "geo_security_endpoints", "router")` after the location-history line
- `backend/tests/test_geo_security_endpoints.py` - 5 tests: admin_gate, get_returns_defaults, patch_persists, validation_rejects_bad_country, validation_normalizes_case

## Decisions Made
- PATCH returns the freshly-resolved settings dict (via `get_geo_security_settings`) rather than echoing the request body — this guarantees the response always reflects what would actually be read back on a subsequent GET (tenant/global/default resolution included), not just what the client happened to send.
- Country-code validation lives in a Pydantic `field_validator` on the request body model (API boundary), separate from `geo_security_service.evaluate_geo_fence`'s own defensive normalization at the detector level — two independent layers, each appropriate to its boundary (T-47-04-T).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a test mock-setup gap in `TestValidationNormalizesCase`**
- **Found during:** Task 2 (running the endpoint tests against the real implementation)
- **Issue:** The Task 1 test for case-normalization only wired `system_settings.update_one`'s side effect to capture the "written" state, but left `find_one` on the default `AsyncMock(return_value=None)`. Since the implemented PATCH handler returns `get_geo_security_settings(...)` (a fresh read-back, per the decision above) rather than echoing the request body, the test's assertion on the PATCH response saw hardcoded defaults (`allowed_country_codes: []`) instead of the normalized `["US", "GB"]` — a test bug, not an implementation bug, but one that only surfaced once Task 2's real read-back-on-write behavior existed.
- **Fix:** Added a `find_one` side effect (mirroring the existing pattern in `TestPatchPersists`) that returns the accumulated `state` dict, so the mock genuinely reflects what was persisted.
- **Files modified:** `backend/tests/test_geo_security_endpoints.py`
- **Verification:** All 5 tests pass; `pytest backend/tests/test_geo_security_endpoints.py -q` green.
- **Committed in:** `9b48750` (Task 2 commit — the test fix was necessary to exercise the real Task 2 code, so it's included in the same commit rather than amending the already-pushed Task 1 test commit).

---

**Total deviations:** 1 auto-fixed (1 bug in test scaffolding)
**Impact on plan:** No scope creep — the fix only corrected a test's own mock wiring so it actually verifies the behavior it claims to.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `GET`/`PATCH /api/settings/geo-security` is live and registered; Plan 47-06's Security settings panel can call it directly.
- Full backend suite re-run after this plan: 5/5 new tests pass; 1422 passed / 34 skipped / 8 failed overall, all 8 failures confirmed pre-existing and order-dependent (reproduce identically in isolation, unrelated to any file this plan touched) — `test_webhook_logic.py::test_jira_intent_parsing`/`test_zoho_intent_parsing`, `tests/test_agentic_ai.py::test_run_calls_anthropic_with_tool_choice_any`, `tests/test_e2e_integration.py::test_golden_path_evidence_to_remediation`, `tests/test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls`, and 3 tests in `tests/test_support_admin_to_user.py` (all `RuntimeError: no current event loop` — asyncio fixture/order issue unrelated to this plan). Excluded from the run for known pre-existing collection errors unrelated to this plan: `test_ai_service_config.py`, `test_network_endpoint.py`, `test_sbom_api.py`, `tests/test_graphql.py` (strawberry/pydantic version mismatch), `backend/tests/test_rebac.py` (openfga_sdk collection issue per prior sessions).

---
*Phase: 47-agent-scoped-geo-security-detectors*
*Completed: 2026-07-29*

## Self-Check: PASSED

- FOUND: backend/geo_security_endpoints.py
- FOUND: backend/tests/test_geo_security_endpoints.py
- FOUND: .planning/phases/47-agent-scoped-geo-security-detectors/47-04-SUMMARY.md
- FOUND commit: 9134bbe (test)
- FOUND commit: 9b48750 (feat)
- FOUND commit: 96eee69 (docs: summary)
