---
phase: 87-partner-and-reseller-channel
verified: 2026-11-03T20:15:00Z
status: gaps_found
score: 4/5 roadmap success criteria verified (SC4 failed in part)
covered_files:
  - ".planning/phases/87-partner-and-reseller-channel/87-01-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-01-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-02-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-02-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-03-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-03-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-04-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-04-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-05-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-05-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-06-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-06-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-07-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-07-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-08-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-08-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-09-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-09-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-10-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-10-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-11-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-11-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-12-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-12-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-13-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-13-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-14-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-14-SUMMARY.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-15-PLAN.md"
  - ".planning/phases/87-partner-and-reseller-channel/87-15-SUMMARY.md"
  - "backend/license_rules.py"
  - "backend/migrations/029_partner_channel.py"
  - "backend/partner_middleware.py"
  - "backend/partner_platform_service.py"
  - "backend/partner_pool.py"
  - "backend/partner_portal_service.py"
  - "backend/stream_processing_endpoints.py"
  - "backend/tenant_middleware.py"
covered_digest: "v3:sha256:09b0031abc83ad71189cc9d5a1548b58b37ae8f47afa76728f5c0dec930a2a1c"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "SC4 / PART-05: Partner admins and viewers reach only their own customers' seats and usage through every route (the edge allowlist is the second wall behind the catalogue guards)"
    status: failed
    reason: "PartnerScopeMiddleware reads the role through tenant_middleware._bearer_role, which accepts only the exact prefix 'Bearer '. FastAPI's OAuth2PasswordBearer (get_current_user) accepts any scheme case and strips the parameter. Verifier re-ran the audit probe: 'bearer <t>', 'BEARER <t>', 'Bearer  <t>' (two spaces) and 'Bearer <t> ' (trailing space) all reach the app with middleware_status=200 while FastAPI would accept the token; only the exact 'Bearer <t>' is refused with 403. TenantMiddleware has the same parser, so the tenant context is also left unset on those requests (the DB wrapper then fails closed, which limits what a tenant-wrapped route returns, but routes on the raw handle or an exempt collection such as tenants are not limited by it). The route-walk test and the mounted-middleware test only send the exact 'Bearer ' spelling, so they miss it."
    artifacts:
      - path: "backend/tenant_middleware.py"
        issue: "_bearer_role (lines 101-111) matches auth.startswith('Bearer ') and decodes auth[7:]; shared by PartnerScopeMiddleware, PlatformReadOnlyMiddleware and ScreenSwitchMiddleware"
      - path: "backend/partner_middleware.py"
        issue: "line 62 trusts _bearer_role; no role means no refusal"
    missing:
      - "One shared header parser that partitions on the first space, compares the scheme case-insensitively and strips the parameter, used by _bearer_role and the other hand-written parsers (audit_middleware.py:69, export_controls.py:46, tenant_middleware.py:177-182)"
      - "Scheme-spelling variants (bearer, BEARER, double space, trailing space) in the mounted-middleware test and the route walk"
      - "Enumerate routes protected only by get_current_user that read raw-handle or tenant-exempt data, and check nginx passes the header unchanged; then re-run /gsd-secure-phase 87 to close T-87-13"
  - truth: "SC4: no partner sees any customer's security data"
    status: failed
    reason: "WebSocket /api/stream/live (backend/stream_processing_endpoints.py:66-110) accepts any active JWT, a partner's included (PartnerScopeMiddleware handles HTTP scopes only; the handler checks no role and no tenant). It subscribes the client to the global 'system_stats', 'logs' and 'security_events' broker topics with no tenant filter. log_endpoints.py:69 publishes tenant-tagged log rows to 'logs' and ueba_alert_persistence_service.py:42 publishes UEBA alerts. A partner token can therefore receive customers' log and security events. The leak exists for every tenant today (not new in Phase 87), but the phase accepted risk T-87-15 on the premise that delivery is per tenant, and that premise is false for this route, and the roadmap criterion is stated absolutely."
    artifacts:
      - path: "backend/stream_processing_endpoints.py"
        issue: "websocket_endpoint verifies the token only; no role refusal for partner roles and no tenant filter on the three topics"
      - path: "backend/partner_middleware.py"
        issue: "docstring documents the exclusion of websocket scopes as an assumption (A-87-A5) that the code contradicts"
    missing:
      - "Refuse partner roles in the /live handshake (close 4403), or filter events by the token's tenant"
      - "A test that a partner token cannot subscribe to /api/stream/live"
      - "Live Socket.IO isolation check from the validation Manual-Only list"
deferred: []
human_verification:
  - test: "Full backend suite on a private mongod, compared by name against the 2026-11-02 baseline"
    expected: "Failures are exactly the four baseline names (test_audit_export::test_legacy_download_allows_owner, test_e2e_integration::test_cross_tenant_report_download_owner_allowed, test_catalogue_route_parity::test_ledger_ratchets, test_catalogue_manifest::test_sidebar_and_app_agree_with_manifest)"
    why_human: "About 33 minutes alone on the VM; not run by the phase or by this verification"
  - test: "Live end-to-end partner flow after a backend restart and UI publish (migration 029 not yet run live)"
    expected: "Appoint a partner, partner admin creates a customer from the pool, invitee signs in and meets MFA set-up, suspend locks the partner out while the customers' agents keep reporting"
    why_human: "Nothing is published, the backend has not been restarted, SMTP is not configured on this VM"
  - test: "Browser pass of the Partners screen, Partner portal (admin and viewer) and Accept-invite page, light and dark at 640, 1024 and 1280 px"
    expected: "Matches 87-UI-SPEC; 87-UI-REVIEW scored 17/24 from code only"
    why_human: "Visual and responsive behaviour, needs a published UI"
  - test: "Live isolation: partner token against customer pages and APIs, Socket.IO, and the real retailer trial (2+ partners, 100 and 1,000 seats, real agents)"
    expected: "Every customer route refused, nothing of customers delivered over Socket.IO or /api/stream/live, the agent past the allotment is held"
    why_human: "Needs the deployed backend and real agents"
---

# Phase 87: Partner and Reseller Channel Verification Report

**Phase Goal:** The platform can sell through partners the way a vendor appoints dealers: a Super Admin appoints partner organizations and gives each a pool of agent seats, a partner creates and manages its own customer organizations and assigns seats to each from its pool, a partner admin sees only that partner's customers, and usage rolls up per partner.
**Verified:** 2026-11-03T20:15:00Z
**Status:** gaps_found
**Re-verification:** No, initial verification

## Goal Achievement

The seat-pool mechanics, partner and customer management, suspension, moves, usage roll-up and the partner UI are present, wired and covered by passing tests. The goal clause "a partner admin sees only that partner's customers" is not fully achieved: the edge wall that is meant to enforce "through every route" has a demonstrated bypass, and a partner token can subscribe to the global security stream. Both are recorded as gaps.

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Super Admin appoints a partner with pool, expiry and screen ceiling from a Partners screen, sees pool used and free, and can suspend a partner (users locked out, customers keep running) | VERIFIED | `partner_platform_service.py`, `partner_platform_endpoints.py`, `PartnersDashboard`; `test_partner_platform.py`, `test_partner_suspension.py` (suspension is a per-request check in the token verifier, login and refresh; customers untouched, byte-for-byte test); vitest PartnersDashboard and PartnerAdminModals green |
| 2 | Partner admin creates a customer with seats from the pool and invites its first admin, who runs it like a direct customer; screens only within the ceiling | VERIFIED | `partner_portal_service.create_customer` (pool claim, `build_tenant_doc`, invite, rollback on failure), ceiling validation; `test_partner_customers.py`, `test_partner_ceiling.py`, `test_partner_invites.py` pass. Real e-mail delivery and first sign-in not exercised (SMTP unset), listed under human verification |
| 3 | Seats never exceed the pool under concurrency; lower only to seats used; pool cannot shrink below handed out; after pool expiry no customer created and no seat handed out | VERIFIED | `partner_pool.claim` is one conditional `$expr` update; `change_allotment` compare-and-set plus used-floor in the same update; `set_pool_size` conditional on `partner.allocated`; `pool_expired` gates create and raise; `license_rules.hold_reason` holds new agents after pool expiry. `test_partner_pool.py` (20 concurrent claims), `test_partner_expiry.py`, `test_partner_license_writers.py` pass |
| 4 | Partner admins and viewers reach only their own customers' seats and usage through every route; two-partner test shows no partner sees another partner's customers or any customer's security data | FAILED | Two-partner isolation holds on the portal API (`test_partner_isolation.py`, 9 pass; every lookup filters `{id, partnerId: token partner}`; rows rebuilt from the D-01 allowlist). But the edge allowlist is bypassed by header spelling (gap 1) and `/api/stream/live` serves global security events to a partner token (gap 2) |
| 5 | Super Admin moves a customer between partners or to direct with seats returned and audited; pre-existing organizations stay direct; per-customer usage list with CSV export | VERIFIED | `partner_pool.move_customer` (claims target first, compare-and-set, releases old pool, audit in `partner_platform_service`); migration 029 creates indexes only, no backfill, so existing tenants keep no `partnerId`; `test_partner_move.py` pass; CSV via `toCsv`/`downloadCsv` with formula guard, PartnerPortal vitest green |

**Score:** 4/5 roadmap truths verified; 0 behavior-unverified.

### Requirements Coverage

All eight IDs (PART-01 to PART-08) are claimed by plan frontmatter (87-14 claims all eight) and each maps to Phase 87 in REQUIREMENTS.md. No orphaned requirements.

| Requirement | Source Plans | Status | Evidence |
|-------------|-------------|--------|----------|
| PART-01 appoint, pool, suspend/reinstate | 01, 02, 04, 06, 07, 08, 11, 14, 15 | SATISFIED | Platform service, suspension chokepoint, Partners screen; tests green. Live suspension flow is a human check |
| PART-02 partner creates customer and invites first admin | 01, 06, 09, 10, 12, 13, 14 | SATISFIED | `create_customer`, invite flow, AcceptInvitePage. Review WR-04 (invite lower-cases the address, login matches case-sensitively) can lock out an invitee who types a different case |
| PART-03 seats never exceed pool, atomic | 01, 03, 08, 10, 11, 14 | SATISFIED | Atomic claim and compare-and-set verified in code and by 26 pool tests. Review WR-05 (0-seat move into a suspended partner) and WR-06 (transient over-claim) are open warnings |
| PART-04 expiry after pool expiry | 03, 09, 10, 12, 14 | SATISFIED | `pool_expired` and `hold_reason`; `test_partner_expiry.py` |
| PART-05 only own customers, only seats and usage, through every route; no tenant or platform permission | 01, 02, 05, 07, 09, 12, 14, 15 | BLOCKED | Roles fenced and portal isolation verified, but "through every route" fails (gaps 1 and 2) |
| PART-06 screens within the ceiling | 08, 09, 12, 14 | SATISFIED | Server-side `validate_ceiling` and `_final_screens`; `test_partner_ceiling.py` |
| PART-07 only Super Admin moves; audited; existing stay direct | 03, 08, 10, 11, 14 | SATISFIED | `move_customer`, audit, migration 029 no backfill; `test_partner_move.py` |
| PART-08 usage roll-up and CSV | 01, 09, 12, 14 | SATISFIED | `overview`, `customer_rows`; `test_partner_usage.py`, PartnerPortal vitest |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app_middleware.py` | `PartnerScopeMiddleware` | `app.add_middleware` (line 304) | WIRED | Present, but its role parse is bypassable (gap 1) |
| `partner_endpoints` | `partner_portal_service` / `partner_pool` | direct calls | WIRED | Real queries, no static returns |
| licence PATCH and approve-and-raise | `partner_pool.change_allotment` | `pending_agents.py:398-410`, licensing | WIRED | Drift test forbids other writers of `license.maxAgents` |
| `license_rules.hold_reason` | partner pool expiry | `fresh.partnerId` lookup | WIRED | Returns `license_expired` after pool expiry |
| `verify_token_async` | partner status | per-request check | WIRED | Suspension test passes |
| shell (App.tsx, Header, Sidebar, FeaturesContext) | partner views | `isPartnerRoleName` | WIRED | `PartnerShell.test.tsx` passes (App.tsx judged as committed) |
| `/api/stream/live` | partner role refusal | none | NOT_WIRED | No role or tenant check (gap 2) |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| Partner portal customers table | `customers` | `partner_store.customer_rows` on `tenants` filtered by `partnerId`, rebuilt from CUSTOMER_FIELDS | Yes | FLOWING |
| Partners screen pool bars | `allocated`, `poolSize` | `partner_platform_service` list over `tenants` | Yes | FLOWING |
| CSV export | rows | same overview rows | Yes | FLOWING |

### Behavioral Spot-Checks (run by the verifier on a private mongod, port 27998, removed afterwards)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Pool, isolation, route walk, usage, expiry, licence writers | pytest `test_partner_pool`, `_isolation`, `_route_walk`, `_usage`, `_expiry`, `_license_writers` | 79 passed | PASS |
| Suspension, platform, move, customers, ceiling, invites, roles, tracer | pytest the eight matching files | 154 passed | PASS |
| Partner frontend | vitest PartnerPortal, partnerAccess, AcceptInvitePage, PartnersDashboard, PartnerShell | 127 passed | PASS |
| Edge wall under scheme spellings | audit probe `audit87/probe_bearer.py` (no DB) | exact 'Bearer' refused 403; 'bearer', 'BEARER', two spaces, trailing space all reach the app (200) while FastAPI accepts the token | FAIL (gap 1) |

Orchestrator gates, not re-run: `npm run build` exit 0; vitest `src/__tests__` 84 files, 1179 tests pass; 87-14 backend gate 451 passed, 2 failed (both on the pre-phase baseline).

### Probe Execution

SKIPPED: the phase declares no probe scripts (no `scripts/*/tests/probe-*.sh`).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/tenant_middleware.py` | 101-111 | Hand-written bearer parser stricter than the auth dependency | Blocker | Gap 1 |
| `backend/stream_processing_endpoints.py` | 66-110 | Global topic subscription, no tenant or role check | Blocker | Gap 2 |
| (phase files) | n/a | TBD, FIXME, XXX markers; `dangerouslySetInnerHTML` | None found | Clean |

Open review warnings (87-REVIEW.md, 0 critical, 11 warning, 10 info; none dispositioned): WR-01 partner roles listed to tenant admins via `GET /api/roles`; WR-04 invite e-mail case versus login; WR-05 0-seat move into a suspended partner; WR-06 transient over-claim; WR-02/03/07 through WR-11 as listed. These are warnings, not blockers of the goal, but WR-01 conflicts with the D-04 intent and WR-04 can break first sign-in for PART-02.

### Human Verification Required

See the `human_verification` frontmatter: full backend suite against baseline, live end-to-end flow, browser pass, live isolation including Socket.IO and the retailer trial. None of these can be run before a restart and a UI publish, and the user owns those.

### Gaps Summary

Two gaps, both on PART-05 / success criterion 4, and both in the "through every route" half of the isolation claim:

1. **T-87-13 (high, open):** the edge allowlist is skipped by an Authorization header spelled `bearer`, `BEARER`, with two spaces or a trailing space. Independently reproduced. The catalogue guards still refuse partners on guarded surfaces and the DB wrapper fails closed with no tenant context, so this is a second-wall failure and not a proven customer-data leak; routes on the raw handle or a tenant-exempt collection were not enumerated. Fix with one shared RFC-style header parser, add spelling variants to the tests, then re-run `/gsd-secure-phase 87`.
2. **`/api/stream/live`:** a partner token can subscribe to global log and security-event topics that carry tenant-tagged events. Pre-existing for every tenant, but the roadmap says a partner sees no customer's security data, and the accept-risk reasoning (T-87-15) is contradicted by the code.

Everything else in the goal (pools, atomic seats, expiry, suspension, moves, usage, CSV, partner UI) is verified by code and passing tests. Close the two gaps with `/gsd-plan-phase 87 --gaps`, then re-verify. The open review warnings (notably WR-01 and WR-04) are worth folding into that gap round.

---

_Verified: 2026-11-03T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
