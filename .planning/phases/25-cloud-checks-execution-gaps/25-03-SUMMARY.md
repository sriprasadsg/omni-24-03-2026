---
phase: 25-cloud-checks-execution-gaps
plan: 03
subsystem: security
tags: [iac, container-scanning, trivy, react, typescript, compliance-integrity]

requires:
  - phase: 25-cloud-checks-execution-gaps
    provides: "shared backend/tests/test_iac_scanner.py file (25-02 added CloudFormation tests; sequenced to avoid merge conflict, not a functional dependency)"
provides:
  - "Explicit simulated boolean field on both container scan result paths (real Trivy and fallback)"
  - "SIMULATED badge surfaced in 3 UI locations so fabricated CVE data is never mistaken for real Trivy evidence"
affects: [container-scanning, compliance-dashboard, iac-container-dashboard]

tech-stack:
  added: []
  patterns:
    - "Additive machine-readable flag (simulated: true/false) instead of fail-closed behavior change, preserving existing fallback-data tests"
    - "Reuse of existing yellow/AlertTriangle visual language for all new badge sites (no new color scheme introduced)"

key-files:
  created: []
  modified:
    - backend/container_scanner_service.py
    - backend/tests/test_iac_scanner.py
    - components/IacContainerDashboard.tsx

key-decisions:
  - "simulated field added purely additively — scan_image() control flow and dispatch logic untouched, so both existing container tests (test_container_scan_image, test_container_vuln_severity_counts) pass unmodified (Pitfall 4, no fail-closed regression)"
  - "New test_container_simulated_flag inserted directly after test_container_scan_image for locality, not appended at end of file"
  - "History-row 'sim' tag styled to mirror the existing IaC provider-tag pattern (px-1.5 py-0.5 rounded background chip) rather than inventing a new tag style"

requirements-completed: [CHK-03]

coverage:
  - id: D1
    description: "container_scanner_service.py returns explicit simulated: true (fallback) / simulated: false (real Trivy) on both result paths"
    requirement: "CHK-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_iac_scanner.py#test_container_simulated_flag"
        status: pass
      - kind: unit
        ref: "backend/tests/test_iac_scanner.py#test_container_scan_image"
        status: pass
      - kind: unit
        ref: "backend/tests/test_iac_scanner.py#test_container_vuln_severity_counts"
        status: pass
    human_judgment: false
  - id: D2
    description: "SIMULATED badge rendered on Vulnerability Summary panel, Vulnerabilities table header, and Scan-History rows in IacContainerDashboard.tsx; no badge when simulated is falsy/undefined"
    requirement: "CHK-03"
    verification:
      - kind: unit
        ref: "npm run build (tsc type-check of widened ContainerScanResponse interface + JSX)"
        status: pass
    human_judgment: true
    rationale: "Visual placement/prominence of the badge across 3 render sites requires a human to view the rendered dashboard to confirm it reads as unmissable — this is the plan's own end-of-phase human-check item, not unit-testable."

duration: 6min
completed: 2026-07-06
status: complete
---

# Phase 25 Plan 03: Container Scan Simulated-Data Labeling Summary

**Container scan results now carry an explicit `simulated` boolean, and the dashboard renders an unmissable SIMULATED badge on the summary panel, vulnerabilities table, and scan-history rows so fabricated CVE-2024-000x data can never be mistaken for a real Trivy scan.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-06T12:55:00Z
- **Completed:** 2026-07-06T12:56:32Z
- **Tasks:** 2 completed
- **Files modified:** 3

## Accomplishments
- Added `simulated: True`/`simulated: False` to the two container-scan result dicts (`_simulated_results()` and `_parse_trivy_output()`) in `backend/container_scanner_service.py`, purely additive — no change to `scan_image()`'s control flow or fallback dispatch.
- Added `test_container_simulated_flag` in `backend/tests/test_iac_scanner.py`, confirming the fallback path still returns non-empty data (`total > 0`) while labeled `simulated: True` — proves no fail-closed regression.
- Widened the `ContainerScanResponse` TypeScript interface with `simulated?: boolean` and added a SIMULATED badge at 3 render sites in `components/IacContainerDashboard.tsx`: the Vulnerability Summary panel (next to the image name), the Vulnerabilities table header (chip beside the findings count), and each simulated Scan-History row (a "sim" tag mirroring the existing IaC provider-tag style).
- Full `backend/tests/test_iac_scanner.py` suite (15 tests, including all 25-02 CloudFormation tests) passes green; `npm run build` succeeds with no type errors.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add explicit `simulated` field to both container-result paths + assert it (backend)** - `2ffe690` (feat)
2. **Task 2: Surface a SIMULATED badge in three UI sites (frontend)** - `b00481b` (feat)

**Plan metadata:** committed alongside this SUMMARY (see final commit below).

_Note: no TDD tasks in this plan — both tasks are `type="auto"` without `tdd="true"`._

## Files Created/Modified
- `backend/container_scanner_service.py` - `_parse_trivy_output()` now returns `simulated: False`; `_simulated_results()` now returns `simulated: True`, alongside existing `trivy` boolean
- `backend/tests/test_iac_scanner.py` - new `test_container_simulated_flag` inserted after `test_container_scan_image`; existing container tests left unmodified
- `components/IacContainerDashboard.tsx` - `ContainerScanResponse` interface widened with `simulated?: boolean`; SIMULATED badge added at 3 render sites (summary panel, vulns table header, scan-history rows)

## Decisions Made
- Purely additive fix (labeling, not fail-closed) per RESEARCH.md Pattern 4 — `scan_image()` control flow untouched so both pre-existing container tests keep passing unmodified.
- New assertion test placed immediately after `test_container_scan_image` for locality/readability rather than appended at file end.
- Badge styling reuses the existing yellow-50/yellow-900 + `AlertTriangle` visual language already established by the note banner in the same component — no new color introduced.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
CHK-03 closed. Phase 25 (Cloud Checks Execution Gaps) now has all 3 plans complete (CHK-01, CHK-02, CHK-03). Ready for phase-level verification / end-of-phase human-check of the 3 badge sites (summary panel, vulnerabilities table, scan-history rows) per this plan's `<verify><human-check>` item, and any remaining phase-level UAT.

---
*Phase: 25-cloud-checks-execution-gaps*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: backend/container_scanner_service.py
- FOUND: backend/tests/test_iac_scanner.py
- FOUND: components/IacContainerDashboard.tsx
- FOUND: .planning/phases/25-cloud-checks-execution-gaps/25-03-SUMMARY.md
- FOUND commit: 2ffe690
- FOUND commit: b00481b
