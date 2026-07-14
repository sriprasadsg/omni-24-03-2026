# UAT Report: Phase 29 — Public Trust Center

## Overview
Validation of the public trust center, including backend API, public-facing routes, and frontend integration.
**Executed 2026-07-14 against the running app.** Result: **the phase's planned implementation is not in the tree** — UAT confirms the 29-UAT-SUMMARY.md finding and extends it: not just the test file, the *feature* is missing.

## Test Cases

| ID | Description | Result | Notes |
|----|-------------|--------|-------|
| 1 | Public Profile Read (Slug) | **Failed — not implemented** | No `/trust/{slug}` route exists (404). Unauthenticated `GET /api/trust-center/profile` returns 401 — every trust route still requires `get_current_user`. |
| 2 | Public Profile Read (Custom Domain) | **Failed — not implemented** | No Host-header resolution, no `trust_domain`/`trust_slug` fields anywhere in backend. |
| 3 | Private Document Access (NDA gate) | **Failed — not implemented** | No NDA consent flow; `private_documents` only exist as hardcoded seed data in the in-memory singleton. |
| 4 | Access Request Submission | **Passed with caveats** | Works, but authenticated-only (an external visitor cannot reach it) and stored in-memory — lost on restart. |
| 5 | Admin Request Management | **Passed with caveats** | Approve/deny works; deny correctly clears `approved_at`/`approved_by` (fix in 5f78f43e). Same in-memory caveat. |
| 6 | Rate Limiting | **Failed — not implemented** | The rate limits were planned for the public routes, which don't exist. |

## Root cause

`trust_service.py` is still the pre-Phase-29 in-memory singleton (88 lines, hardcoded profile) and `trust_endpoints.py` still requires auth on every route. Plans 29-01/29-02/29-04 (DB-backed `trust_profiles`/`trust_access_requests`, public GET/POST routes with tenant resolution, `trust-page.html` + `GET /trust/{slug}`) produced SUMMARY files but **no code was ever committed** — `git log --all` shows no trust-center implementation commits. The frontend half-exists: `TrustPage.tsx` embeds `/trust/{slug}` in an iframe and reads a `trust_slug` field the backend never returns, so it permanently renders "No trust page slug found".

Same failure class as Phase 30-01's phantom RAG tenant isolation (found 2026-07-13): phase artifacts claiming uncommitted work.

## Disposition

Phase 29 must be **re-executed** (plans 29-01, 29-02, 29-04; 29-03's admin-frontend scope needs re-verification too). TRUST-01/02/03 are all unmet. Roadmap status corrected from "Complete" to "Not implemented — re-execution required".
