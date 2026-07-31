# Phase 36 Plan 36-01: Analysis and Design Doc Summary

**Plan:** 36-01
**Subsystem:** Authorization
**Status:** complete

## Key Decisions

1. **ReBAC Engine Selection:** Chose **OpenFGA** over SpiceDB for its superior Python client maturity (`openfga-client-py`), active development ecosystem, and flexible deployment models.
2. **Architecture:** Adopted a **sidecar pattern** to isolate policy decisions from business logic, ensuring scalability and consistency across the platform.
3. **Migration Strategy:** Gradual rollout starting with `ComplianceControl` as a pilot resource, maintaining dual-read capability for zero-downtime transition.

## Tech Stack

- **Added:** OpenFGA
- **Patterns:** Zanzibar (Relationship-Based Access Control)

## Key Files

| File | Action | Description |
|------|--------|-------------|
| `backend/36-DESIGN.md` | Created | Research, decision matrix, and architecture specification for ReBAC migration. |

## Deviations from Plan

None - plan executed as written.

## Self-Check: PASSED
- [x] DESIGN.md exists and contains all required sections.
- [x] Research OpenFGA vs SpiceDB documented.
- [x] Recommendation and Architecture specified.
- [x] Changes committed to git.
