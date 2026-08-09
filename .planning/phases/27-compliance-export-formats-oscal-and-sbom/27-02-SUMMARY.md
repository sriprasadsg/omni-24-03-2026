---
phase: 27-compliance-export-formats-oscal-and-sbom
plan: 02
subsystem: api
tags: [cyclonedx, sbom, fastapi, trivy, container-scanning]
summary_type: execution
status: completed
requirements: [EXP-02]

requires:
  - phase: 24-iac-container-security
    provides: container_scanner_service scan-result documents (scan_id, image, trivy, simulated, vulns[])
provides:
  - GET /api/container/results/{scan_id}/sbom — CycloneDX 1.6 SBOM export for container scans
  - _to_cyclonedx builder with (pkg_name, installed_version) bom-ref dedup
  - "Export SBOM" download button on IacContainerDashboard
affects: [compliance-export, audit-evidence, trust-center]

tech-stack:
  added: []
  patterns: [hand-rolled CycloneDX via stdlib uuid — no cyclonedx-python-lib dependency]

key-files:
  created:
    - backend/tests/test_container_sbom_export.py
  modified:
    - backend/container_scanner_endpoints.py
    - components/IacContainerDashboard.tsx

key-decisions:
  - "Simulated (non-Trivy) scans are exported with metadata.properties omniagent:simulated='true' rather than blocked (resolved decision #2)"
  - "Tenant isolation via explicit {scan_id, tenantId} filter on raw db._db.container_scan_results; wrong-tenant and nonexistent scan_id both return identical 404 (T-27-03)"

patterns-established:
  - "CycloneDX component dedup: one component per (pkg_name, installed_version); vulnerabilities link via affects[].ref to the deduped bom-ref"
---

# Plan 27-02 Summary — CycloneDX SBOM Export (EXP-02)

**Note:** This plan was executed in the same session as 27-01 (see 27-01-SUMMARY.md, which records `plans_executed: [27-01, 27-02]`), but the per-plan summary file was never written, leaving the phase counted as incomplete. This summary reconciles the record; implementation was re-verified on 2026-07-13.

## What was built

- `_to_cyclonedx(scan_result)` builder + `GET /results/{scan_id}/sbom` route in `backend/container_scanner_endpoints.py` (94 lines, well under 500). Route copies the module's existing auth convention: `Depends(rbac_service.has_permission("view:dashboard"))` + `get_tenant_id()`.
- `backend/tests/test_container_sbom_export.py` — 4 tests covering CycloneDX 1.6 structure, bom-ref dedup + vuln→component linkage, simulated flag, and tenant 404.
- "Export SBOM" button in the Vulnerabilities header of `components/IacContainerDashboard.tsx` (481 lines) using the existing `authHeaders()` + blob-download idiom; downloads `sbom-{scanId}.json`.

## Verification (re-run 2026-07-13)

- `backend/venv/bin/python -m pytest backend/tests/test_container_sbom_export.py -x` — **4 passed**.
- `backend/sbom_endpoints.py`, `db.sboms`, `db.software_components` untouched (naming-trap guard held).
- No new dependencies added.
- UAT: `27-UAT.md` — **PASS**, all 6 acceptance items met.
