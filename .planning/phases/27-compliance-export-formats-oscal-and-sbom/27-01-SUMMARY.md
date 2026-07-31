---
phase: 27-compliance-export-formats-oscal-and-sbom
summary_type: execution
status: completed
plans_executed:
  - 27-01
  - 27-02
waves_executed: 1
artifacts_produced:
  - backend/oscal_endpoints.py
  - backend/tests/test_oscal_export.py
  - backend/router_registry.py
  - components/ApiExtensionsDashboard.tsx
  - backend/container_scanner_endpoints.py
  - backend/tests/test_container_sbom_export.py
  - components/IacContainerDashboard.tsx
verification_status:
  all_backend_tests_passed: false # Due to an unrelated error outside phase scope.
  oscal_tests_passed: true
  sbom_tests_passed: true
---

# Phase 27 Execution Summary

All plans for Phase 27 (Compliance Export Formats - OSCAL and SBOM) have been executed.

## Key Outcomes:
- **OSCAL Export:**
  - `backend/oscal_endpoints.py` created with a read-only OSCAL v1.1.2 assessment-results export endpoint.
  - Corresponding tests in `backend/tests/test_oscal_export.py` pass.
  - Router for OSCAL endpoint registered in `backend/router_registry.py`.
  - "Export OSCAL" button added to `components/ApiExtensionsDashboard.tsx`.
- **SBOM Export:**
  - CycloneDX 1.6 SBOM export route (`/api/container/results/{scan_id}/sbom`) added to `backend/container_scanner_endpoints.py`.
  - Corresponding tests in `backend/tests/test_container_sbom_export.py` pass.
  - "Export SBOM" button added to `components/IacContainerDashboard.tsx`.

## Verification:
- All new unit tests for OSCAL and SBOM export functionality (`test_oscal_export.py`, `test_container_sbom_export.py`) passed successfully.
- A full backend test run identified an existing `AttributeError` in `backend/tests/test_cloud_findings_ingest.py::test_scan_account_m365_dispatch` which is outside the scope of Phase 27. This existing error did not prevent the successful completion and verification of Phase 27's tasks.
