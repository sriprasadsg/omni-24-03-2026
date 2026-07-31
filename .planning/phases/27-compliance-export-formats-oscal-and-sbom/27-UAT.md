## Phase 27 UAT

**Status:** PASS

**Tests:**
1. OSCAL endpoint `/api/oscal/assessment-results` returns 200 with valid OSCAL v1.1.2 JSON, includes required metadata, and maps Non-Compliant controls to `"planned"` status.
2. OSCAL tenant isolation returns 403 for missing tenant_id, preserves privacy.
3. OSCAL framework not found returns 404 with clear error.
4. SBOM endpoint `/api/container/results/{scan_id}/sbom` returns 200 with CycloneDX 1.6 JSON, deduped bom-refs, vulnerability-to-component mapping, simulated flag inclusion, and tenant isolation.
5. SBOM button on Container Dashboard triggers download of `sbom-{scan_id}.json`.
6. No new dependencies added, existing modules untouched, all files under 500 lines.

**Result:** All acceptance criteria met. Phase 27 verified and ready for completion.