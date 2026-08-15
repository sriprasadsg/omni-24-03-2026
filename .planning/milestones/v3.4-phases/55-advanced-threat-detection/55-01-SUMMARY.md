---
phase: 55-advanced-threat-detection
plan: 01
subsystem: security
tags: [siem, correlation, fastapi, motor, mongodb, tenant-isolation]

# Dependency graph
requires:
  - phase: 54-integration-operator-ui
    provides: bounded-read/normalize/merge pattern for native findings (native_security_ops_endpoints.get_findings)
  - phase: 51-vuln-engine
    provides: security_scan_results/vulnerabilities/fim_events native finding collections
  - phase: 53-autonomous-remediation
    provides: remediation_audit collection + set_tenant_id/reset_tenant_id tenant-scoping pattern
provides:
  - "SiemEngine.correlate_native_findings(tenant_id) — normalizes 4 native v3.4 finding collections into the existing SIEM event shape and runs them through the existing rule-evaluation loop"
  - "POST /api/threat-intel/correlate-native — authenticated, tenant-scoped trigger route for native-finding correlation"
  - "First-ever direct test coverage for siem_engine.py (backend/tests/test_siem_engine.py)"
affects: [55-02-predictive-anomaly-detection, 55-03-automated-containment, 55-04-soc-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Extend-not-rebuild correlation: normalize new finding sources into the SAME event dict shape an existing engine consumes, then reuse its existing rule-evaluation/case-creation loop unchanged (D-01)"
    - "Bounded per-collection correlation input (.to_list(length=200)) — never an unbounded .find({}) scan"
    - "set_tenant_id(tenant_id)/reset_tenant_id(_tctx) in a try/finally around every new correlation read"

key-files:
  created:
    - backend/tests/test_siem_engine.py
    - .planning/phases/55-advanced-threat-detection/deferred-items.md
  modified:
    - backend/siem_engine.py
    - backend/threat_intel_endpoints.py

key-decisions:
  - "correlate_native_findings() is a new method ON SiemEngine (not a standalone module/class) so existing siem_rules apply to native findings automatically — the strongest reading of D-01 (RESEARCH.md Open Question 2, Option a)"
  - "The companion trigger route lives in threat_intel_endpoints.py, not siem_endpoints.py (already 736 lines, over the 500-line cap), per D-01's 'add a companion enrichment path for native findings'"
  - "Route reuses the file's existing manage:security permission gate (matching enrich_security_event, the closest existing analog — a POST handler that triggers processing over security events) rather than introducing a new permission string"

requirements-completed: [INT-04]

coverage:
  - id: D1
    description: "SiemEngine.correlate_native_findings(tenant_id) reads the 4 native v3.4 collections bounded/tenant-scoped, normalizes them into the existing event shape, and reuses _evaluate_rules/_match_rule/_trigger_alert to create a security_cases doc on a matching rule"
    requirement: "INT-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_siem_engine.py::TestCorrelateNativeFindings::test_matching_rule_creates_exactly_one_security_case"
        status: pass
      - kind: unit
        ref: "backend/tests/test_siem_engine.py::TestCorrelateNativeFindings::test_reuses_evaluate_rules_not_a_parallel_loop"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every native-collection correlation read is bounded (.to_list(length<=200)) — never an unbounded scan"
    requirement: "INT-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_siem_engine.py::TestBoundedReadRegression::test_every_native_collection_read_caps_to_list_at_200"
        status: pass
    human_judgment: false
  - id: D3
    description: "Correlation reads are tenant-scoped — a tenant B finding is never evaluated into a tenant A security_cases document"
    requirement: "INT-04"
    verification:
      - kind: unit
        ref: "backend/tests/test_siem_engine.py::TestCrossTenantIsolation::test_tenant_b_finding_not_correlated_into_tenant_a_case"
        status: pass
    human_judgment: false
  - id: D4
    description: "POST /api/threat-intel/correlate-native — authenticated companion trigger route resolving tenant via the existing _get_tenant(user) helper, calling correlate_native_findings"
    requirement: "INT-04"
    verification:
      - kind: unit
        ref: "grep -n \"correlate-native\" backend/threat_intel_endpoints.py"
        status: pass
    human_judgment: true
    rationale: "No live TestClient HTTP-level test was added for this route — the module transitively imports backend/virustotal_client.py, which has a pre-existing, unrelated broken import (NameError: BaseCapability undefined, logged in deferred-items.md) that prevents standalone import of threat_intel_endpoints.py outside the existing test suite's stub-module workaround. The route's own logic (tenant resolution -> correlate_native_findings() -> return summary) is a 6-line thin handler with no new logic beyond what D1-D3's direct tests already cover at the SiemEngine level; a human should confirm the route is reachable once virustotal_client.py's pre-existing bug is separately fixed."

duration: 10min
completed: 2026-08-03
status: complete
---

# Phase 55 Plan 01: Threat-Intel Correlation (INT-04) Summary

**SiemEngine.correlate_native_findings() extends the existing SIEM rule-evaluation loop to ingest native v3.4 findings (scans/vulns/FIM/remediation history), bounded and tenant-scoped, with zero parallel correlation path — plus the first direct test coverage siem_engine.py has ever had.**

## Performance

- **Duration:** ~10 min active execution (across 2 tasks; a tracer checkpoint paused between Task 1 and Task 2 for human confirmation)
- **Started:** 2026-08-03T13:36:00Z (session start)
- **Completed:** 2026-08-03T13:59:13Z (last task commit `e7ec5d1`)
- **Tasks:** 2/2
- **Files modified:** 2 (`backend/siem_engine.py`, `backend/threat_intel_endpoints.py`); 1 new (`backend/tests/test_siem_engine.py`)

## Accomplishments
- `SiemEngine.correlate_native_findings(self, tenant_id)` — bounded (`.to_list(length=200)`), tenant-scoped (`set_tenant_id`/`reset_tenant_id`) reads of `security_scan_results`, `vulnerabilities`, `fim_events`, `remediation_audit`; normalizes each doc into the same event shape `_normalize_log()` produces; calls the **existing** `self._evaluate_rules()` — a tenant's existing `siem_rules` now apply to native findings automatically, with no rule redefinition and no parallel correlation loop (D-01).
- `POST /api/threat-intel/correlate-native` — thin, authenticated (`manage:security` permission), tenant-scoped (`_get_tenant(current_user)`) trigger route in `threat_intel_endpoints.py` that delegates entirely to `SiemEngine.correlate_native_findings()`.
- `backend/tests/test_siem_engine.py` — the first-ever direct test file for `siem_engine.py` (7 tests): matching-rule → exactly one `security_cases` insert, no-match → no insert, empty-findings short-circuit, a reuse-not-reimplement guard on `_evaluate_rules`, a bounded-read regression test (cap ≤ 200 on all 4 collections), and a cross-tenant isolation test.

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end native-finding correlation — one path only** - `15545ce` (feat) — `correlate_native_findings()` + `_normalize_native_finding()` + 5 initial tests. Preceded by a tracer checkpoint (per `type="tracer"`) that paused for human confirmation before Task 2, since `workflow.auto_advance`/`_auto_chain_active` were both `false`. User approved and instructed to proceed.
2. **Task 2: Companion correlation-trigger route (INT-04) + bounded-read regression assertions** - `e7ec5d1` (feat) — `POST /api/threat-intel/correlate-native` route + 2 additional regression tests (bounded-read cap, cross-tenant isolation).

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `backend/siem_engine.py` - new `correlate_native_findings()`/`_normalize_native_finding()` methods on `SiemEngine`; new `NATIVE_FINDING_READ_LIMIT = 200` module constant; `tenant_context` import
- `backend/threat_intel_endpoints.py` - new `POST /api/threat-intel/correlate-native` route (318 lines total, under the 500-line cap); `siem_engine.get_siem_engine` import
- `backend/tests/test_siem_engine.py` - new file, 7 tests across 4 test classes (`TestCorrelateNativeFindings`, `TestBoundedReadRegression`, `TestCrossTenantIsolation`)
- `.planning/phases/55-advanced-threat-detection/deferred-items.md` - new file, logs the pre-existing `virustotal_client.py` import bug and the re-baselined full-suite pass/fail count

## Decisions Made
- `correlate_native_findings()` is a method **on** `SiemEngine`, not a standalone function/class — RESEARCH.md's Open Question 2, Option (a); makes existing `siem_rules` apply to native findings "for free."
- The companion route was added to `threat_intel_endpoints.py` per D-01's explicit guidance, not `siem_endpoints.py` (already 736 lines, over the 500-line CLAUDE.md cap).
- Reused the `manage:security` permission (already used by `enrich_security_event`, the closest existing analog) rather than inventing a new permission string — no new auth surface (ASVS V2 note in RESEARCH.md).
- `_normalize_native_finding()` derives `category`/`action` per-source from each native collection's own field vocabulary (severity/verdict for scans and vulns, `change_type` for FIM, `stage` for remediation audit) rather than a single generic mapping — matches how each collection's actual documents are shaped (verified via `agent_security_scan_endpoints.py`, `agent_security_endpoints.py`, `remediation_audit_service.py`).

## Deviations from Plan

### Auto-fixed Issues

None required — Rules 1-3 were not triggered; the plan's own acceptance criteria (bounded reads, tenant scoping, `_evaluate_rules` reuse) were achievable directly as specified.

### Out-of-scope discovery (logged, not fixed)

**1. [Scope boundary] Pre-existing broken import in `backend/virustotal_client.py`**
- **Found during:** Task 2, while sanity-checking `import threat_intel_endpoints`
- **Issue:** `virustotal_client.py` line 7 references an undefined `BaseCapability` base class (`NameError` at import time). Confirmed pre-existing via `git diff --stat virustotal_client.py` (zero changes this session) and `git log` (last touched by an unrelated prior commit).
- **Why not fixed:** Not in this plan's file list (`backend/siem_engine.py`, `backend/threat_intel_endpoints.py`, `backend/tests/test_siem_engine.py` only) — out of scope per the executor's scope-boundary rule. The existing test suite already works around it (`test_fim_events_rich.py` stubs the module before import); `router_registry.py` loads `threat_intel_endpoints` as non-required, so app startup and the passing test suite are both unaffected.
- **Logged:** `.planning/phases/55-advanced-threat-detection/deferred-items.md` and the broken-windows ledger (`gsd-tools windows append`, kind=deviation, phase=55).

---

**Total deviations:** 0 auto-fixed; 1 out-of-scope discovery logged (not fixed).
**Impact on plan:** None — INT-04's full scope was delivered without needing any Rule 1-3 auto-fix. The logged item is a pre-existing, unrelated bug that does not block this plan's acceptance criteria (all of which are verified via direct `SiemEngine` tests, not a live HTTP call through `threat_intel_endpoints.py`'s full import chain).

## Issues Encountered
- Initial docstring wording in `correlate_native_findings()` contained the literal substring `db._db` (in the sense of "never db._db") which tripped the plan's own `grep -c 'db\._db'` acceptance check (looking for zero occurrences as a scope-fence guard against unwrapping the tenant-isolated handle). Reworded to avoid the literal substring while preserving the same meaning — confirmed `grep -v '^#' backend/siem_engine.py | grep -c 'db\._db'` now returns `0`.
- Re-baselined the full backend suite at the end of the plan per RESEARCH.md's per-wave verification step: `cd backend && venv/bin/python -m pytest -q` (with 4 pre-existing, environment-broken collection modules excluded — `test_graphql.py` strawberry/pydantic version mismatch, `test_ai_service_config.py`, `test_network_endpoint.py`/`test_sbom_api.py` live-network dependencies) → **1525 passed / 34 skipped / 5 failed**, all 5 failures confirmed pre-existing and unrelated to this plan's 2 modified files (details in `deferred-items.md`).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- INT-04 is fully delivered: native findings correlate into `security_cases` through the existing rule engine, bounded and tenant-scoped, reachable via an authenticated trigger route, with direct test coverage.
- Plans 55-02 (predictive anomaly detection) and 55-03 (automated containment) build on `autonomous_remediation_service.remediate()` — unaffected by this plan's changes (no shared files).
- Plan 55-04 (SOC integration/OCSF push) may eventually want a webhook hook off `SiemEngine._trigger_alert()` (the natural COMM-01 integration point per RESEARCH.md's architecture diagram) — not built this plan, correctly out of INT-04's scope.
- The `virustotal_client.py` pre-existing bug (deferred-items.md item 1) should be fixed independently before any future work needs to import `threat_intel_endpoints.py` standalone or add a live `TestClient` test against it.

---
*Phase: 55-advanced-threat-detection*
*Completed: 2026-08-03*

## Self-Check: PASSED

- FOUND: backend/siem_engine.py
- FOUND: backend/threat_intel_endpoints.py
- FOUND: backend/tests/test_siem_engine.py
- FOUND: .planning/phases/55-advanced-threat-detection/deferred-items.md
- FOUND commit: 15545ce
- FOUND commit: e7ec5d1
