---
phase: 25-cloud-checks-execution-gaps
plan: 01
subsystem: api
tags: [cloud-security, fastapi, mcp, provider-allowlist, pytest]

# Dependency graph
requires:
  - phase: 20-multi-account-cloud-scanning
    provides: cloud_accounts registration/scan endpoints and cloud_accounts_service
  - phase: 17-cloud-checks-expansion
    provides: CLOUD_CHECKS catalogue including K8S_CHECKS (20) and DO_CHECKS (10), left unreachable
  - phase: 22-api-extensions-mcp-ocsf-cli-do
    provides: MCP run_cloud_check tool endpoint
provides:
  - "run_checks() evaluates kubernetes (20 checks) and digitalocean (10 checks) end-to-end"
  - "k8s/DO account registration via POST /api/cloud-accounts"
  - "Coverage denominator (_RUNNABLE_CHECKS_COUNT) includes all 5 providers"
affects: [26-vendor-and-risk-data-completeness, 32-cloud-and-saas-provider-expansion]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Widen provider-allowlist tuples/sets directly at each of the 4 gate call sites rather than introducing a shared constants module (Tier-1 fix, per RESEARCH.md Don't Hand-Roll)"]

key-files:
  created: []
  modified:
    - backend/cloud_checks_service.py
    - backend/cloud_checks_endpoints.py
    - backend/cloud_account_endpoints.py
    - backend/mcp_server_endpoints.py
    - backend/tests/test_cloud_checks_expansion.py
    - backend/tests/test_cloud_accounts.py

key-decisions:
  - "RUNNABLE_PROVIDERS widened to 5-tuple (aws, azure, gcp, kubernetes, digitalocean); _RUNNABLE_CHECKS_COUNT left as a list-comprehension over CLOUD_CHECKS so it recomputes for free at import time (no hardcoded count)"
  - "All four provider gates (cloud_checks_service.RUNNABLE_PROVIDERS, cloud_checks_endpoints inline tuple, cloud_account_endpoints._VALID_PROVIDERS, mcp_server_endpoints inline tuple) widened in a single lockstep commit so no gate accepts a provider another rejects"
  - "No shared constants module introduced — each of the 4 literals edited directly per RESEARCH.md Pattern 1 (Tier-1 fix, out of scope to refactor)"

patterns-established:
  - "TDD RED/GREEN pair per plan: Task 1 authored 5 failing tests against the still-narrow gates, Task 2 widened all 4 gates and turned them green in one commit"

requirements-completed: [CHK-01]

coverage:
  - id: D1
    description: "run_checks() evaluates kubernetes and digitalocean checks and returns ran > 0 (not an error dict) for registered accounts of those providers"
    requirement: "CHK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_cloud_checks_expansion.py#test_run_checks_evaluates_kubernetes"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cloud_checks_expansion.py#test_run_checks_evaluates_digitalocean"
        status: pass
    human_judgment: false
  - id: D2
    description: "A cloud account with provider=kubernetes or provider=digitalocean can be registered via POST /api/cloud-accounts and returns 200"
    requirement: "CHK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_cloud_accounts.py#test_register_kubernetes_account"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cloud_accounts.py#test_register_digitalocean_account"
        status: pass
    human_judgment: false
  - id: D3
    description: "Coverage denominator (_RUNNABLE_CHECKS_COUNT) includes k8s + DO checks so coverage neither exceeds 100% nor is unreachable at 100%"
    requirement: "CHK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_cloud_checks_expansion.py#test_coverage_denominator_includes_new_providers"
        status: pass
    human_judgment: false
  - id: D4
    description: "Tenant isolation on run_checks()/scan_account() unchanged — existing test_tenant_isolation and test_scan_sets_status still pass"
    requirement: "CHK-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_cloud_accounts.py#test_tenant_isolation"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cloud_accounts.py#test_scan_sets_status"
        status: pass
    human_judgment: false

# Metrics
duration: 12min
completed: 2026-07-06
status: complete
---

# Phase 25 Plan 01: Widen Provider-Allowlist Gates for Kubernetes/DigitalOcean Cloud Checks Summary

**Widened four independent provider-allowlist gates (run_checks, direct-run endpoint, account registration, MCP tool) in lockstep so the already-catalogued 20 Kubernetes and 10 DigitalOcean checks are actually reachable end-to-end, closing CHK-01.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-06T12:36:00Z (approx, from session start)
- **Completed:** 2026-07-06T12:40:35Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- `run_checks()` now evaluates kubernetes (20 checks) and digitalocean (10 checks) instead of returning `{"error": "provider must be one of (...)"}`.
- Kubernetes and DigitalOcean cloud accounts can be registered via `POST /api/cloud-accounts` (200, previously 400).
- `POST /api/cloud-checks/run` and the MCP `run_cloud_check` tool both accept kubernetes/digitalocean without a 400.
- Coverage denominator (`_RUNNABLE_CHECKS_COUNT`) now equals `len(CLOUD_CHECKS)` (all 5 providers), eliminating the unreachable/impossible-100%-coverage drift the RESEARCH.md flagged.
- Filled the previously 0-line `test_cloud_checks_expansion.py` stub (a pre-existing Phase 17 coverage gap) with 3 tests; added 2 registration tests to `test_cloud_accounts.py`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author Wave 0 CHK-01 tests (RED)** - `a7e4f45` (test)
2. **Task 2: Widen all four provider-allowlist gates in lockstep (GREEN)** - `4da6d86` (feat)

**Plan metadata:** (this commit, added below)

_TDD-shaped plan: RED commit followed by GREEN commit, no REFACTOR step needed (edits were minimal literal changes)._

## Files Created/Modified
- `backend/tests/test_cloud_checks_expansion.py` - Filled 0-line stub with 3 tests exercising `run_checks()` directly against a mocked DB (kubernetes/digitalocean evaluation + coverage denominator invariant)
- `backend/tests/test_cloud_accounts.py` - Added `test_register_kubernetes_account` and `test_register_digitalocean_account`, mirroring the existing `test_register_gcp_account` pattern
- `backend/cloud_checks_service.py` - `RUNNABLE_PROVIDERS` widened from 3 to 5 providers; comment above the tuple updated to no longer claim k8s/DO are excluded; `_RUNNABLE_CHECKS_COUNT` computation left unchanged in shape (recomputes automatically)
- `backend/cloud_checks_endpoints.py` - Direct-run provider gate and its HTTPException detail string widened to the 5-provider set
- `backend/cloud_account_endpoints.py` - `_VALID_PROVIDERS` set widened to 5 providers (error message derives from `sorted(_VALID_PROVIDERS)`, no separate string edit needed)
- `backend/mcp_server_endpoints.py` - MCP `run_cloud_check` tool-schema description and provider validation gate (plus detail string) widened to the 5-provider set

## Decisions Made
- `RUNNABLE_PROVIDERS` widened to `("aws", "azure", "gcp", "kubernetes", "digitalocean")`; `_RUNNABLE_CHECKS_COUNT` kept as a comprehension over `CLOUD_CHECKS` (no hardcoded count) per RESEARCH.md Pitfall 2.
- All four gates widened in a single commit (Task 2) rather than incrementally, per RESEARCH.md Pattern 1 and the phase decision recorded in planning context — leaving Gate 1 (registration) narrower than Gate 4 (execution) would leave the multi-account UI flow still broken.
- No shared constants module introduced (RESEARCH.md "Don't Hand-Roll" — out of scope for this Tier-1 fix); each of the 4 literals edited directly.

## Deviations from Plan

None - plan executed exactly as written. No Rule 1/2/3/4 deviations were needed; the fix was a literal, mechanical widening of 4 allowlists exactly as scoped.

## Issues Encountered

None. Both `venv/bin/python` (backend venv) resolution and the RED→GREEN verification loop worked as expected on first pass; the full backend suite (`tests/`, 770 passed, 22 skipped) shows zero regressions across all four edited gate files, including `test_tenant_isolation` and `test_scan_sets_status`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

CHK-01 is closed: kubernetes and digitalocean checks are reachable through every trigger path (registration → scan, direct run, MCP tool). No blockers for 25-02 or 25-03. The 5-provider set is now consistent across all 4 gate files, which any future provider addition (e.g., Phase 32 Cloud/SaaS Provider Expansion) should extend in the same lockstep pattern documented here.

---
*Phase: 25-cloud-checks-execution-gaps*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: backend/tests/test_cloud_checks_expansion.py
- FOUND: backend/tests/test_cloud_accounts.py
- FOUND: backend/cloud_checks_service.py
- FOUND: .planning/phases/25-cloud-checks-execution-gaps/25-01-SUMMARY.md
- FOUND commit: a7e4f45 (test)
- FOUND commit: 4da6d86 (feat)
