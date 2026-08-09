---
phase: 29-public-trust-center
plan: 04
subsystem: web
tags: [trust-center, public-page, static-html, vanilla-js, fileresponse, fastapi]

# Dependency graph
requires:
  - phase: 29-public-trust-center (plan 02)
    provides: "Genuinely public GET /api/public/trust/{slug} (private-URL-stripped) and POST /api/public/trust/{slug}/requests (NDA-consented, server-derived metadata)"
provides:
  - "GET /trust/{slug} — unauthenticated FileResponse route in app.py serving the standalone public trust page"
  - "backend/static/trust-page.html — self-contained HTML/CSS/vanilla-JS public trust page (Surface A)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Public browser-facing FileResponse route cloned from the /.well-known/security.txt precedent: unauthenticated, no /api prefix, path param unused server-side (consumed client-side by the page's own JS via window.location)"

key-files:
  created:
    - backend/static/trust-page.html
  modified:
    - backend/app.py

key-decisions:
  - "The verify command in 29-04-PLAN.md (`app.app.routes`) no longer matches the real module shape — app.py wraps the FastAPI app in socketio.ASGIApp and reassigns the module-level `app` name to that wrapper (`_fastapi_app` holds the original FastAPI instance), a pre-existing pattern from an earlier phase's socketio integration, unrelated to this plan. Verified the route registration against `app._fastapi_app.routes` and via a real TestClient GET request instead, since the plan's literal verify command would raise `AttributeError: 'ASGIApp' object has no attribute 'routes'` regardless of whether the route exists. Not treated as a plan deviation requiring a fix — the route itself is correctly registered on the FastAPI app object per the plan's `<action>` instructions; only the *verification command text* in the plan predates the socketio wrap."

requirements-completed: [TRUST-02]

# Metrics
duration: 12min
completed: 2026-07-14
status: complete
---

# Phase 29 Plan 04: Public Trust Page (Standalone HTML) + Serving Route Summary

**Standalone, dependency-free `backend/static/trust-page.html` (vanilla JS, no build step) plus the unauthenticated `GET /trust/{slug}` FileResponse route in `app.py`, cloned from the `/.well-known/security.txt` precedent — closes the last gap in TRUST-02 by giving external visitors a real unauthenticated page that consumes the 29-02 public API.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-14T00:50:00Z
- **Completed:** 2026-07-14T01:02:00Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `backend/app.py` gained `GET /trust/{slug}` (`include_in_schema=False`), returning `FileResponse(static/trust-page.html, media_type="text/html")` — no `Depends(get_current_user)`, no `/api` prefix, placed immediately after the existing `security_txt()` route it clones. Verified registered on the real FastAPI app instance and confirmed a live `TestClient` `GET /trust/some-slug` returns `200 text/html` containing the page content.
- `backend/static/trust-page.html` (468 lines, under the 500-line CLAUDE.md limit) is a single self-contained document: inline hand-written CSS using the UI-SPEC Surface A tokens (14/16/20/32px type scale, 400/600 weights, `#f8fafc`/`#ffffff`/`#00a8cc`/`#dc2626`/`#15803d` color tokens, Outfit font via Google Fonts `<link>` with the `Inter, system-ui, -apple-system, sans-serif` fallback) and inline vanilla JS (zero dependencies, no bundler references).
- On load, the page parses the slug from `window.location.pathname` and `fetch()`s `/api/public/trust/{slug}`. On success it renders: header (company name as 32px display, description, contact email, "Publicly Visible" indicator), the compliance-framework badge row (green-50/green-700 pills, section omitted entirely when the array is empty), the Public Documents list (each with a working download `<a href>`), and the Restricted Documents list (name-only rows + "NDA Required" label + "Request Access" button that reveals the request form) — the restricted-doc rendering path never reads or constructs a `url`/`href` from a private document (confirmed by the plan's negative grep).
- The "Request Document Access" form (full name, email, company, reason, required consent checkbox with the exact UI-SPEC consent copy) validates email format and consent client-side before `fetch(POST)`-ing to `/api/public/trust/{slug}/requests` with `{requester_email, company, reason, consent: true}`; on success the form is replaced with the exact "Request received. {company_name} will review your request..." copy; a 429 response shows the rate-limit banner copy, other failures show the network-error banner copy (with `{contact_email}` interpolated).
- Unknown-slug/404 state renders the exact "Trust page not found." heading/body copy; empty-public-docs state renders the exact "No public documents yet." heading/body copy with `{contact_email}` interpolated.
- All required structural/copy checks from the plan's `<verify>` block pass verbatim: `/api/public/trust/`, "Request Document Access", "Submit Request", "Trust page not found.", "Request received.", "private_documents" all present; the negative grep for `private[_A-Za-z]*\.url`/`privateDoc[A-Za-z]*\.url` finds no match (the one `doc.url` reference in the file is inside the `publicDocs.forEach` loop, which is expected — public documents carry real URLs).
- `backend/tests/test_trust_center.py` still 17/17 green; full backend suite **940 passed / 22 skipped / 0 failed** (24.10s) — no regression against the prior 936-passed baseline (delta accounted for by other already-committed work in the tree, unrelated to this plan).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the GET /trust/{slug} FileResponse serving route in app.py** - `795aa444` (feat)
2. **Task 2: Build the standalone public trust page (trust-page.html)** - `b6b82a15` (feat)

## Files Created/Modified
- `backend/app.py` - Added `public_trust_page(slug: str)` — `@app.get("/trust/{slug}", include_in_schema=False)` returning `FileResponse(... "trust-page.html" ..., media_type="text/html")`, placed after the `security_txt()` route it clones. No auth dependency, no `/api` prefix.
- `backend/static/trust-page.html` (new) - Standalone HTML/CSS/vanilla-JS public trust page: header, framework badges, public/restricted document lists, NDA access-request form, and all empty/error/success states per the UI-SPEC Copywriting Contract. 468 lines.

## Decisions Made
- Verified the route registration against `app._fastapi_app.routes` (and a live `TestClient` request) rather than the plan's literal `app.app.routes` verify command, because `app.py`'s pre-existing socketio integration (unrelated to this plan) reassigns the module-level `app` name to a `socketio.ASGIApp` wrapper that has no `.routes` attribute. The route itself was added exactly per the plan's `<action>` block on the real FastAPI app object — only the verify command text in the plan predates that wrap.
- Slug parsing on the client reads `window.location.pathname` (splitting on `/` and taking the second segment) rather than a regex, matching the simplicity bar set by "no build step, no framework" — kept intentionally minimal since the route is always `/trust/{slug}`.
- Used `encodeURIComponent(slug)` when building both the GET and POST fetch URLs as a defensive measure against slugs containing reserved URL characters, even though `_resolve_tenant_from_request` on the backend does an exact-match lookup — this doesn't change the request contract, just makes the client robust to slugs with special characters.

## Deviations from Plan

None requiring the Rule 1-4 auto-fix process — plan executed exactly as written for both tasks. The one adjustment (verifying route registration via `_fastapi_app.routes` / TestClient instead of the plan's literal `app.app.routes` snippet) was a verification-command correction, not a change to the implementation; the route itself matches the plan's `<action>` block precisely.

## Issues Encountered
- The plan's Task 1 `<verify>` automated command (`app.app.routes`) fails with `AttributeError: 'ASGIApp' object has no attribute 'routes'` because `app.py` (from an earlier, unrelated phase) wraps the FastAPI app in `socketio.ASGIApp` and reassigns `app` to that wrapper near the end of the file, while keeping the original FastAPI instance available as `_fastapi_app`. Resolved by verifying against `app._fastapi_app.routes` and a real `TestClient(app._fastapi_app)` GET request instead — both confirm the route is correctly registered and serves the page. No code change was needed; this was purely a stale verify-command artifact from before the socketio wrap existed.

## User Setup Required

None - no external service configuration required. No new packages introduced (the page's only external reference is the Google Fonts CDN `<link>` for the Outfit font, per the UI-SPEC's explicit allowance).

## Next Phase Readiness
- TRUST-02 is now fully complete end-to-end: the public API (29-02) and the public page that consumes it (this plan) are both live and tested.
- Manual/UAT verification remains outstanding per 29-VALIDATION.md's Manual-Only gate: start the app, open `/trust/{slug}` for a seeded tenant with no Authorization header in a real browser, confirm the page renders public data, restricted docs show no download URL, and the Request Access form submits successfully end-to-end (client + server). This automated execution confirmed the route and page via `TestClient`, not a live browser session.
- With 29-01/29-02/29-03/29-04 all executed, Phase 29 (Public Trust Center) has no remaining plan-level scope — TRUST-01/02/03 are all functionally complete across backend and frontend.
- No blockers.

## Known Stubs

None. The page is fully wired to the real 29-02 public API endpoints (no mock/hardcoded data); the "Trust Analytics" quick-stats panel's pre-existing hardcoded values noted in 29-03-SUMMARY.md are in the admin UI (`TrustCenter.tsx`), out of scope for this plan's static public page.

## Threat Flags

None beyond what this plan's own `<threat_model>` already registers and closes (T-29-03 restricted-document URL leak — closed via the negative grep and the code review confirming the private-doc render path never touches `.url`; T-29-02 existence-leak via 404 — closed, generic copy used for all not-found cases; T-29-08 abuse/DoS on the request form — closed via transfer, client-side validation only, authoritative rate limiting remains server-side per 29-02; T-29-SC third-party font CDN — closed via accept, no other external references). No new network endpoints, auth paths, or trust-boundary-crossing surface beyond the one FileResponse route and the static page's two `fetch()` calls to the already-reviewed 29-02 public API.

---
*Phase: 29-public-trust-center*
*Completed: 2026-07-14*

## Self-Check: PASSED

- FOUND: backend/app.py
- FOUND: backend/static/trust-page.html
- FOUND: .planning/phases/29-public-trust-center/29-04-SUMMARY.md
- FOUND commit: 795aa444 (Task 1: GET /trust/{slug} route)
- FOUND commit: b6b82a15 (Task 2: trust-page.html)
