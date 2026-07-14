# UAT Report: Phase 28 — Governance Document Management

## Summary
Validation of versioned document management, e-signature, and dashboard.
**Completed 2026-07-14 by driving the running app** (uvicorn backend + Vite frontend + headless Chromium): full lifecycle exercised end-to-end — create → submit-for-approval → approve → publish → sign → export signed PDF, plus dashboard click-through.

## Test Cases

| ID | Description | Result | Notes |
|----|-------------|--------|-------|
| 1 | Create Document | **Passed** | Via API and via dashboard UI form. Required fix: router was never registered (see below). |
| 2 | Sign Document | **Passed** | Server-derived signer identity/IP/UA captured; consent=false correctly rejected (400); publish correctly blocked before approval (400). |
| 3 | Export Signed PDF | **Passed** | Real 1-page PDF generated and downloadable from /static/reports. Required fix: broken REPORTS_DIR import (500). |
| 4 | Dashboard Navigation | **Passed** | "Governance Documents" reachable under Governance & Compliance; lifecycle actions render per document status. Required fix: nav wiring was missing entirely. |

## Defects found and fixed during UAT (commit 368f01d9)

1. **`governance_document_endpoints` never registered in `router_registry.py`** — every Phase 28 route 404'd in the real app while the 9-test suite passed (tests build their own FastAPI app).
2. **`POST /api/approvals/{id}/decide` always 401** — read `current_user.email`, but `TokenData` carries the JWT sub in `username`. Blocked approval → publish → sign for every real user (not just governance).
3. **`export-signed-pdf` ImportError** — imported nonexistent `REPORTS_DIR` from `compliance_reporting_service`; 500 on every export.
4. **Dashboard unreachable** — `GovernanceDocumentsDashboard.tsx` existed but was wired into none of App.tsx/Sidebar.tsx/types.ts (28-03's promised wiring never done).

## Evidence
- Screenshots: scratchpad `shots/02-governance-dashboard.png`, `03-governance-created.png` (session-local).
- API captures in UAT session log: publish blocked pre-approval (400 "not approved (status: pending)"), sign consent guard (400), signed PDF `doc-*_v1_signed.pdf` verified as `PDF document, version 1.4`.
