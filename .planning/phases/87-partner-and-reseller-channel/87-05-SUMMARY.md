---
phase: 87-partner-and-reseller-channel
plan: 05
subsystem: api
tags: [fastapi, asgi-middleware, rbac, multi-tenant, catalogue-guard]

requires:
  - phase: 87-01
    provides: partner roles, partner_endpoints and partner_platform_endpoints routers, catalogue_mounts_partners
  - phase: 87-04
    provides: partner suspension (token verifier refusal)
provides:
  - partner_request_refusal and PartnerScopeMiddleware (the edge allowlist for partner tokens)
  - route-walk proof over every mounted route plus a real-app guard probe
  - manifest and mount parity test for the partners and partnerPortal catalogues
affects: [87-10, 87-15]

actuals:
  tokens: 9400
  tasks: 2
  commits: 3
plan_head_before: 91d51072174224da5c700b9929f618bfb2bc9023
plan_head_after: af5e15a381720ad3257780d51b469bcb1e6798c8

tech-stack:
  added: []
  patterns:
    - "Edge allowlist as a pure function (role, method, path) plus a pure ASGI wrapper, proven over run_real_app_walk()"
    - "Second wall mounted beside PlatformReadOnlyMiddleware, inside Audit and Tenant middleware"

key-files:
  created:
    - backend/partner_middleware.py
    - backend/tests/test_partner_route_walk.py
    - backend/tests/test_catalogue_slice_partners.py
  modified:
    - backend/app_middleware.py

key-decisions:
  - "Partner role detection reuses rbac_defaults.is_partner_role, so every spelling (Partner Admin, partner admin, PARTNER_ADMIN) is walled"
  - "The refusal body matches PlatformReadOnlyMiddleware exactly: {error, status_code: 403}"
  - "Only the three import/mount lines of app_middleware.py were committed; the user-side hunk in that file (gzip, page-size cap, export controls) is still uncommitted"

requirements-completed: [PART-05]

coverage:
  - id: D1
    description: "A partner_admin is refused every mounted /api route except /api/partner, /api/auth, /api/mfa, /api/passkey and GET/HEAD /api/platform/features"
    requirement: PART-05
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_route_walk.py#test_a_partner_admin_is_refused_every_route_but_the_portal_and_its_own_security"
        status: pass
    human_judgment: false
  - id: D2
    description: "A partner_viewer is refused every write under /api/partner and keeps its own sign-in, MFA and passkey writes"
    requirement: PART-05
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_route_walk.py#test_a_partner_viewer_cannot_write_under_the_portal_but_keeps_its_own_security_writes"
        status: pass
    human_judgment: false
  - id: D3
    description: "Through the mounted middleware a partner token gets 403 JSON on tenants and MSSP, passes on its portal; Super Admin, other roles and no token are untouched"
    requirement: PART-05
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_route_walk.py#test_mounted_middleware_walls_a_partner_token_and_leaves_everyone_else_alone"
        status: pass
    human_judgment: false
  - id: D4
    description: "With no middleware, the real catalogue guards answer 403 to both partner roles on tenants, MSSP, assets, agents, users and the Partners screen"
    requirement: PART-05
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_route_walk.py#test_the_catalogue_guards_alone_refuse_both_partner_roles_on_the_customer_surfaces"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every route of partner_platform_endpoints and partner_endpoints carries its manifest guard (read and write strings equal) and is owned by partners or partnerPortal"
    requirement: PART-05
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_partners.py#test_every_super_admin_partner_route_carries_the_partners_guard"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_partners.py#test_every_partner_portal_route_carries_the_partner_portal_guard"
        status: pass
    human_judgment: false
  - id: D6
    description: "Websocket and Socket.IO delivery gives a partner socket nothing of a customer (assumption A-87-A5)"
    requirement: PART-05
    verification: []
    human_judgment: true
    rationale: "The middleware covers HTTP only. websocket_manager.py was not read in full and no live socket check was run; the plan flags this for a live check before shipping."

duration: 25min
completed: 2026-11-02
status: complete
---

# Phase 87 Plan 05: Partner Second Wall Summary

**A pure ASGI allowlist in front of every route: a partner token reaches only `/api/partner`, its own `/api/auth`, `/api/mfa`, `/api/passkey` and `GET`/`HEAD /api/platform/features`, a partner viewer never writes, proven over the whole mounted route table rather than a sample.**

## Performance

- **Duration:** about 25 min (interrupted once by a usage limit and resumed)
- **Tasks:** 2
- **Files:** 4 (3 created, 1 modified by 3 lines)

## Accomplishments

- `partner_request_refusal(role, method, path)`: one constant allowlist for every partner and customer (D-02), viewer read-only under the portal (D-04), non-partner roles and non-`/api/` paths never touched.
- `PartnerScopeMiddleware` mounted next to `PlatformReadOnlyMiddleware` (inside Audit and Tenant, so refusals are audited), same 403 JSON shape.
- `test_partner_route_walk.py` walks `run_real_app_walk()` (over 1,000 routes) and asserts the allowed set is exactly the four prefixes plus the shell read; it also checks spelling variants, non-HTTP scopes, the mounted middleware on a tiny app, and a real-app probe showing the catalogue guards alone already answer 403 to both partner roles on the six customer surfaces.
- `test_catalogue_slice_partners.py` pins both routers to the manifest guards and iterates the walk, so routes added by later plans are covered automatically.

## Task Commits

1. **Task 1 RED:** `0692232e8` (test) - 4 of 15 tests failing on the planned assertions
2. **Task 1 GREEN:** `9a69ad09a` (feat) - middleware module and the mount lines
3. **Task 2:** `af5e15a38` (test) - catalogue slice test (a test-only task, passes on first run by design)

## TDD Gate Compliance

- RED: `0692232e8`. The permissive skeleton (never committed) made the four allowlist, viewer, spelling and mounted-middleware tests fail on assertions about the planned behaviour (a viewer POST to `/api/partner/customers` returned None instead of the viewer refusal; GET `/api/tenants` returned 200 instead of 403). `gsd check tdd-red-evidence` on the JUnit report returned `RED_EVIDENCE_OK` (15 run, 4 failed, target test failed). Semantic assessment: the target tests executed and failed for the intended reason, not for an import or fixture fault.
- GREEN: `9a69ad09a`, 24 passed across `test_partner_route_walk.py` and `test_platform_role_routes.py`.
- REFACTOR: none needed.

## Deviations from Plan

None - plan executed exactly as written. The import line for `PartnerScopeMiddleware` is a separate `from partner_middleware import ...` line rather than an addition to the existing tenant_middleware import, which keeps the commit to the plan's own lines in a file that carries a large user-side hunk.

## Issues Encountered

- `test_catalogue_route_parity.py::test_ledger_ratchets` fails, as the orchestrator's known baseline says it does (stale ledger entries unrelated to the partner modules). All other tests in the Task 2 command pass: 72 passed, 1 baseline failure.

## Verification

- `pytest tests/test_partner_route_walk.py tests/test_platform_role_routes.py`: 24 passed.
- `pytest tests/test_catalogue_slice_partners.py tests/test_catalogue_route_parity.py tests/test_route_auth_baseline.py`: 72 passed, 1 baseline failure (`test_ledger_ratchets`).
- Acceptance greps: `PartnerScopeMiddleware` in `app_middleware.py` 2, `def partner_request_refusal` 1, 3 test functions in the slice test.
- No private mongod was started (neither test file needs MongoDB); port 27998 untouched, live mongod untouched, backend not restarted.

## Known Stubs

None.

## Threat Flags

None. T-87-13 and T-87-14 are mitigated by the allowlist and viewer refusal. T-87-15 (websocket and Socket.IO) stays accepted and open: A-87-A5 still needs a live check before shipping.

## User Setup Required

None. The running backend only picks up the middleware on its next restart, which is the user's.

## Next Phase Readiness

Ready for the remaining wave 3 plans. 87-15 owns the pinned drift counts.

---
*Phase: 87-partner-and-reseller-channel*
*Completed: 2026-11-02*

## Self-Check: PASSED

- Created files present: partner_middleware.py, tests/test_partner_route_walk.py, tests/test_catalogue_slice_partners.py
- Commits `0692232e8`, `9a69ad09a`, `af5e15a38` are ancestors of HEAD
