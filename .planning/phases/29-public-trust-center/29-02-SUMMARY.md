---
phase: 29-public-trust-center
plan: 02
subsystem: api
tags: [trust-center, public-route, tenant-isolation, rate-limit, nda, custom-domain, fastapi, slowapi]

# Dependency graph
requires:
  - phase: 29-public-trust-center (plan 01)
    provides: "Async, Mongo-backed trust_service.py (trust_profiles/trust_access_requests) and trust_slug/trust_domain on db.tenants"
provides:
  - "Genuinely public (no get_current_user), rate-limited GET /api/public/trust/{slug} — private-URL-stripped trust profile"
  - "Genuinely public, rate-limited POST /api/public/trust/{slug}/requests — NDA-consented access-request submission with server-derived metadata"
  - "_resolve_tenant_from_request — Host-header (trust_domain) resolution with slug fallback, identical 404 for both no-match cases (TRUST-03 wiring)"
  - "_public_view — server-side filter reducing private_documents to name-only stubs"
  - "trust_endpoints.public_router — new no-prefix APIRouter registered separately in router_registry.py so paths are exactly /api/public/trust/..."
affects: [29-03-custom-domain-resolution, 29-04-frontend-trustcenter-admin-view]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Public-route tenant resolution: exempt db.tenants lookup (Host header trust_domain, then slug fallback) → set_tenant_id() → tenant-scoped service call — cloned from agent_registry_endpoints.register_agent, per 29-RESEARCH.md Pattern 2"
    - "Two APIRouters in one endpoints file: an authenticated `router` (existing prefix) and a genuinely public `public_router` (no prefix, no auth) registered as a second router_registry.py entry against the same module"
    - "Server-derived-only metadata on public write endpoints: ip_address/user_agent/requested_at always taken from request.client/request.headers/server clock, never from the request body, even when the body sends conflicting values"

key-files:
  created: []
  modified:
    - backend/trust_endpoints.py
    - backend/tests/test_trust_center.py
    - backend/router_registry.py

key-decisions:
  - "Added a second APIRouter (public_router, no prefix) in trust_endpoints.py rather than reusing the existing prefixed `router`, because the plan requires the public paths to be exactly /api/public/trust/... with zero auth — mixing that into the /api/trust-center-prefixed, admin-only router would require per-route prefix overrides and risk an accidental auth-dependency leak onto the public path. Registered as a second router_registry.py `_load(app, \"trust_endpoints\", \"public_router\")` line, immediately after the existing admin-router registration."
  - "Discovered (and worked around) that @limiter.limit(...) binds a route's static rate-limit string to the specific Limiter instance that decorated it (rate_limiter.limiter, the process-wide singleton), not to whatever is later assigned to app.state.limiter in a test app. Task 3's rate-limit tests therefore wire app.state.limiter to the real shared rate_limiter.limiter (matching backend/app.py's actual production wiring) and reset its in-memory storage via an autouse pytest fixture before/after every test in the file, so the deliberate 31-request/6-request over-limit hammering never leaks hit counts into the public_get/public_post/custom_domain tests (or vice versa) when the file runs as a whole."
  - "AccessRequestCreate is a plain Pydantic model (not reusing the admin RequestCreate) so unexpected/forged body fields (ip_address, user_agent, requested_at) are silently dropped by FastAPI's request-body validation before the handler ever sees them — the forged-metadata test asserts the persisted record's values differ from the forged input and match the real request/server-derived values instead."

patterns-established:
  - "Any future genuinely-public (no get_current_user) route added to an existing authenticated *_endpoints.py file should follow this exact shape: a second, no-prefix APIRouter alongside the existing authenticated router, registered as its own router_registry.py `_load(..., \"public_router\")` line — keeps the admin router's prefix and auth model completely untouched while making the public surface explicit and easy to audit (grep for `public_router` finds every genuinely public route in the codebase)."

requirements-completed: [TRUST-02, TRUST-03]

# Metrics
duration: 18min
completed: 2026-07-14
status: complete
---

# Phase 29 Plan 02: Public Trust Center Route + NDA Access Request Summary

**Two genuinely public, rate-limited FastAPI routes (`GET`/`POST /api/public/trust/{slug}`) cloning `agent_registry_endpoints.register_agent`'s tenant-resolution shape, serving a private-URL-stripped trust profile and accepting NDA-consented access requests with un-forgeable server-derived metadata, plus Host-header custom-domain resolution for TRUST-03.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-14T00:14:33Z (immediately following 29-01)
- **Completed:** 2026-07-14T00:32:00Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- `backend/trust_endpoints.py` now exposes a second, no-prefix `public_router` carrying `GET /api/public/trust/{slug}` and `POST /api/public/trust/{slug}/requests` — neither route depends on `get_current_user`, both are decorated with `@limiter.limit(...)` and correctly carry the `response: Response` parameter slowapi requires (verified via real end-to-end `TestClient` HTTP calls, not import checks — `grep -c "response: Response" backend/trust_endpoints.py` returns 2).
- `_resolve_tenant_from_request(db, request, slug)` resolves the tenant by Host header (`trust_domain`) first, falling back to path-slug (`trust_slug`) lookup — both against the tenant-isolation-EXEMPT `db.tenants` collection — and raises an identical `HTTPException(404, "Not found")` for either no-match case (no existence-leak via distinct messages). `set_tenant_id(tenant["id"])` is called immediately after resolution and before any tenant-scoped `trust_service` call, in both routes.
- `_public_view(profile)` strips `private_documents` down to `{"name": ...}` stubs — no `url` key ever reaches an unauthenticated caller — while `public_documents` pass through untouched with their real URLs.
- `AccessRequestCreate` (requester_email/company/reason/consent, length-capped) backs `create_public_access_request`: rejects `consent=false`/absent with `400 "Explicit NDA-acceptance consent is required"` before any DB write; on success, builds a record whose `ip_address`/`user_agent`/`requested_at` are taken exclusively from `request.client.host`/`request.headers`/the server clock (forged body values for these same field names are silently dropped by Pydantic before the handler runs).
- `router_registry.py` registers the new `public_router` as a second `_load(app, "trust_endpoints", "public_router")` call right after the existing admin-router registration, so both are wired into the real app without touching the admin router's prefix or auth model.
- `backend/tests/test_trust_center.py` grew from 6 to 17 tests: `TestPublicTrustGet`, `TestPublicDocFilter`, `TestCustomDomainResolution`, `TestPublicAccessRequestPost`, `TestPublicRateLimit` — all passing, all exercised via real `TestClient` HTTP calls (the class of bug this plan's `response: Response` pitfall warns about is invisible to anything less).
- `TestPublicRateLimit` proves the GET's `30/minute` window 429s on request 31 and the POST's tighter `5/minute` window 429s on request 6 — strictly sooner — using the actual shared `rate_limiter.limiter` singleton (the same object every route in this codebase is decorated with), with an autouse fixture resetting its in-memory storage before/after every test in the file for isolation.

## Task Commits

Each task was committed atomically:

1. **Task 1: Host-header/slug resolver, public-view filter, and public GET route** - `1ee31791` (feat)
2. **Task 2: Public NDA access-request POST with consent + server-derived metadata** - `1bcc8361` (feat)
3. **Task 3: Rate-limit enforcement tests through a limiter-wired TestClient app** - `fac0c4e9` (test)

_No TDD RED/GREEN split commits — each task's tests and implementation landed together in a single commit per task, matching how 29-01's Task 2/3 commits were structured (tests were written and verified passing before each commit, not split into a separate failing-test commit)._

## Files Created/Modified
- `backend/trust_endpoints.py` - Added `public_router` (no-prefix `APIRouter`), `_resolve_tenant_from_request`, `_public_view`, `AccessRequestCreate`, `get_public_trust_profile`, `create_public_access_request`. Existing admin `router` and its 5 routes untouched. 187 lines total (well under the 500-line CLAUDE.md limit).
- `backend/tests/test_trust_center.py` - Added `TestPublicTrustGet`, `TestPublicDocFilter`, `TestCustomDomainResolution`, `TestPublicAccessRequestPost`, `TestPublicRateLimit` (11 new tests, 17 total), plus `_public_app`/`_public_app_with_limiter`/`_tenants_col_for_slug` helpers and an autouse rate-limit-storage-reset fixture.
- `backend/router_registry.py` - Added one new `_load(app, "trust_endpoints", "public_router")` line immediately after the existing `trust_endpoints` (admin `router`) registration.

## Decisions Made
- Built the public routes on a second `APIRouter` (`public_router`, no prefix, no auth) inside the same `trust_endpoints.py` file rather than a new module — keeps tenant-resolution helpers (`_resolve_tenant_from_request`, `_public_view`) colocated with both the admin and public routes that will eventually share more logic (29-03), while `router_registry.py`'s `public_router` naming makes every genuinely-public route in this codebase easy to `grep` for.
- Rate-limit tests wire `app.state.limiter` to the real, process-wide `rate_limiter.limiter` singleton (not a throwaway `Limiter()` instance) because slowapi's `@limiter.limit(...)` decorator binds a route's static limit string to the specific instance that decorated it at import time — a fresh, unrelated `Limiter()` assigned to `app.state.limiter` would never see those registered limits and the test would silently pass without actually enforcing anything. This was discovered when the first version of the rate-limit test (using a fresh `Limiter()`) caused shared-storage bleed into unrelated tests later in the same file, root-caused by reading `slowapi`'s `Limiter.__limit_decorator`/`_check_request_limit` source directly.
- Kept `AccessRequestCreate` as a narrow, purpose-built Pydantic model (distinct from the existing admin `RequestCreate`) so FastAPI's request validation is the first line of defense against forged `ip_address`/`user_agent`/`requested_at` fields in the body — they simply aren't part of the schema, so Pydantic drops them before the handler runs, rather than relying on the handler to remember to ignore them.

## Deviations from Plan

None — plan executed exactly as written. All three tasks matched their `<action>`/`<verify>`/`<acceptance_criteria>` blocks. The one implementation detail not spelled out in the plan (slowapi's per-instance limit-registration behavior, and the resulting need for an autouse storage-reset fixture) was investigated and resolved within Task 3's own scope — it did not require deviating from Task 1/2's already-committed route code, only from the plan's suggested "fresh `Limiter()`" test wiring, which was itself description rather than a hard requirement (the plan's actual acceptance criteria — `-k rate_limit` passes, both over-limit requests return 429 not 500, POST trips before GET — are all met).

## Issues Encountered
- The first draft of `TestPublicRateLimit` used a fresh, unrelated `Limiter()` bound to `app.state.limiter` (matching a surface reading of the `test_auth_mfa.py`/`test_passkey_auth.py` precedent). Running the full `test_trust_center.py` file (not just `-k rate_limit`) then failed a later, unrelated `public_get` test with an unexpected `429` — root-caused to `@limiter.limit(...)` registering static route limits onto the specific `Limiter` instance that decorated the function (the real, shared `rate_limiter.limiter` singleton, since that's what `trust_endpoints.py` imports), not onto whatever `app.state.limiter` happens to reference at request time. Fixed by wiring `app.state.limiter` to the real shared limiter in the rate-limit test app (matching what `backend/app.py`/`app_middleware.py` actually do in production) and adding a module-scoped autouse pytest fixture that resets `rate_limiter.limiter._storage` before and after every test in the file, eliminating cross-test bleed while still exercising the real production enforcement path.

## User Setup Required

None - no external service configuration required. No new packages introduced (confirmed by 29-RESEARCH.md's Package Legitimacy Audit: none; `slowapi`, `fastapi`, `motor` are all already-installed dependencies).

## Next Phase Readiness
- `_resolve_tenant_from_request` already implements the full Host-header-first, slug-fallback resolution TRUST-03 needs — plan 29-03 (if scoped separately) can build directly on this helper rather than re-implementing it; `trust_domain` read/write via the admin routes was already delivered in 29-01.
- `public_router` and its two routes are registered end-to-end in `router_registry.py` and confirmed reachable via real `TestClient` calls — ready for 29-04's frontend work (the standalone static public trust page, per 29-RESEARCH.md's recommended architecture) to `fetch()` against `GET /api/public/trust/{slug}` and `POST /api/public/trust/{slug}/requests` directly.
- The pre-existing, order-dependent `test_auth_mfa.py` flakiness noted in 29-01-SUMMARY.md (10/21 `TestMFAVerifyLogin` tests failing only when run as part of the full suite) did NOT reproduce in this plan's full-suite run (936 passed, 22 skipped, zero failures) — appears to be non-deterministic/order-sensitive rather than a fixed regression; still out of scope for this plan and not investigated further here.
- No blockers.

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data sources introduced by this plan — both new routes are fully wired to `trust_service`'s real, DB-backed `get_profile`/`create_request` helpers landed in 29-01.

## Threat Flags

None beyond what this plan's own `<threat_model>` already registers and closes (T-29-01, T-29-02, T-29-03, T-29-04, T-29-05 all closed this plan; T-29-06 remains `accept`/`open` per the plan's explicit DNS/TLS scope boundary, unchanged). No new network endpoints, auth paths, or trust-boundary-crossing surface beyond the two routes and the one resolver helper the plan specifies.

---
*Phase: 29-public-trust-center*
*Completed: 2026-07-14*

## Self-Check: PASSED

- FOUND: backend/trust_endpoints.py
- FOUND: backend/tests/test_trust_center.py
- FOUND: backend/router_registry.py
- FOUND: .planning/phases/29-public-trust-center/29-02-SUMMARY.md
- FOUND commit: 1ee31791 (Task 1: public GET route)
- FOUND commit: 1bcc8361 (Task 2: public POST route)
- FOUND commit: fac0c4e9 (Task 3: rate-limit tests)
- FOUND commit: b61d062d (SUMMARY commit)
