---
phase: 87-partner-and-reseller-channel
verified: 2026-11-04T08:05:00Z
status: human_needed
score: 5/5 roadmap success criteria verified
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
  - "backend/audit_middleware.py"
  - "backend/authentication_endpoints.py"
  - "backend/export_controls.py"
  - "backend/partner_invites.py"
  - "backend/partner_middleware.py"
  - "backend/partner_platform_service.py"
  - "backend/partner_pool.py"
  - "backend/partner_portal_service.py"
  - "backend/role_endpoints.py"
  - "backend/stream_processing_endpoints.py"
  - "backend/tenant_middleware.py"
covered_digest: "v3:sha256:81d3f69c007346b34ae47941106416ef1a70f498adf8724590d71bf945fa8ef7"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "SC4 / PART-05: edge walls bypassed by Authorization scheme spelling (T-87-13), fixed 2ae92b5d2"
    - "SC4: /api/stream/live served global logs and security_events to partner tokens, fixed e693da59e"
  gaps_remaining: []
  regressions: []
gaps: []
deferred: []
human_verification:
  - test: "Full backend suite on a private mongod, compared by name against the baseline"
    expected: "Failures are exactly the four known names (test_audit_export::test_legacy_download_allows_owner, test_e2e_integration::test_cross_tenant_report_download_owner_allowed, test_catalogue_route_parity::test_ledger_ratchets, test_catalogue_manifest::test_sidebar_and_app_agree_with_manifest)"
    why_human: "About 33 minutes alone on the VM; this verification ran the 600-odd phase, auth, roles and catalogue tests only (the two catalogue baseline failures reproduced, nothing new)"
  - test: "Live end-to-end partner flow after a backend restart and UI publish (migration 029 not yet run live)"
    expected: "Appoint a partner, partner admin creates a customer from the pool, invitee signs in and meets MFA set-up, suspend locks the partner out while the customers' agents keep reporting"
    why_human: "Nothing is published, the backend has not been restarted, SMTP is not configured on this VM; 87-UAT.md is at test 2 of the run and awaits the user"
  - test: "Browser pass of the Partners screen, Partner portal (admin and viewer) and Accept-invite page, light and dark at 640, 1024 and 1280 px"
    expected: "Matches 87-UI-SPEC; 87-UI-REVIEW scored 17/24 from code only"
    why_human: "Visual and responsive behaviour, needs a published UI"
  - test: "Live isolation: partner token against customer pages and APIs, Socket.IO (assumption A-87-A5), and the real retailer trial (2+ partners, 100 and 1,000 seats, real agents)"
    expected: "Every customer route refused, nothing of customers delivered over Socket.IO, the agent past the allotment is held"
    why_human: "Needs the deployed backend and real agents; Socket.IO has no partner emitters by assumption and was not checked live"
---

# Phase 87: Partner and Reseller Channel Verification Report

**Phase Goal:** The platform can sell through partners the way a vendor appoints dealers: a Super Admin appoints partner organizations and gives each a pool of agent seats, a partner creates and manages its own customer organizations and assigns seats to each from its pool, a partner admin sees only that partner's customers, and usage rolls up per partner.
**Verified:** 2026-11-04T08:05:00Z
**Status:** human_needed
**Re-verification:** Yes, after gap closure (previous report 2026-11-03T20:15Z, gaps_found 4/5)

## Goal Achievement

Both gaps recorded against success criterion 4 are closed in the code and by tests the verifier ran. Success criteria 1, 2, 3 and 5 were verified in the previous report and re-checked here by running their test files (no regression). What remains is live verification that cannot be done before a backend restart and a UI publish.

### Gap re-check

**Gap 1, T-87-13 (bearer spelling bypass): CLOSED.**
- `backend/tenant_middleware.py:102-109` defines `bearer_token()` over FastAPI's own `get_authorization_scheme_param` (scheme compared case-insensitively, parameter stripped). Used by `_bearer_role` (line 112, feeds the partner, platform read-only and screen-switch walls), `TenantMiddleware` (line 184), `audit_middleware.actor_of` (line 64) and `export_controls` (line 42).
- Independent probe by the verifier (a partner_admin JWT through `PartnerScopeMiddleware` on `GET /api/tenants`): `Bearer`, `bearer`, `BEARER`, `Bearer  ` (two spaces), `Bearer <t> ` (trailing space) and `BeArEr   <t>  ` all return 403. No header returns 200. The previous report showed four of these reaching the app.
- Regression test `test_partner_route_walk.py` now carries `_SPELLINGS` (bearer, BEARER, bEaReR, two spaces, trailing space); the file passes (19 tests).
- Remaining hand-written `startswith("Bearer ")` parsers (`agent_auth.py:74`, `agent_registry_endpoints.py:53`, `deployment_result_endpoints.py:32`, `tunnel_endpoints.py:228`) are agent-token or secondary-token paths, not edge walls; a differently spelled header on them falls to "no token" and the partner wall itself already parses it. Not a gap.

**Gap 2, `/api/stream/live`: CLOSED.**
- `backend/stream_processing_endpoints.py:79-110`: the handshake verifies the token, then `is_partner_role(...)` closes with 4403 before `accept()`. Delivery goes through `_live_event_allowed`: platform staff (`can_read_all_tenants`) get everything; everyone else gets `system_stats` (platform-wide window counts) and only `logs` / `security_events` events tagged with their own tenant; untagged ones are platform data and withheld.
- Tests `test_live_feed_refuses_partner_roles`, `test_live_feed_sends_a_tenant_only_its_own_logs_and_security_events`, `test_live_feed_sends_platform_staff_every_event` in `test_tenant_boundary_hardening.py` pass (32 passed in that file).
- `87-SECURITY.md` was re-audited (fbe4a522c): `threats_open: 0`, T-87-13 closed. T-87-15 (Socket.IO, accepted) still rests on assumption A-87-A5 and remains a live check.

**Review warnings WR-01 to WR-05 (a1a845740): fixed and tested.** WR-01 `role_endpoints.py:135` skips platform and partner roles for non-owners; WR-02 `name_unavailable` 409 at `partner_platform_service.py:70,95,135,156` and `partner_portal_service.py:106,117`; WR-03/WR-04/WR-05 covered by new cases in `test_partner_invites.py`, `test_login_me_permissions.py`, `test_partner_move.py`, `test_partner_customers.py` (all pass). Nav pins read 192 (`test_closure_delivery.py` passes). WR-06 to WR-11 and IN-01 to IN-10 remain open in `87-REVIEW-DISPOSITION.md`; they are warnings and info, none contradicts a success criterion.

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Super Admin appoints a partner with pool, expiry and screen ceiling from a Partners screen, sees pool used and free, can suspend (users locked out, customers keep running) | VERIFIED | `test_partner_platform.py`, `test_partner_suspension.py` pass; vitest PartnersDashboard green |
| 2 | Partner admin creates a customer with seats from the pool and invites its first admin; screens only within the ceiling | VERIFIED | `test_partner_customers.py`, `test_partner_ceiling.py`, `test_partner_invites.py` pass (incl. new WR-03/WR-04 cases). Real e-mail and first sign-in are a human item |
| 3 | Seats never exceed the pool under concurrency; lower only to seats used; pool cannot shrink below handed out; after pool expiry no customer and no seat | VERIFIED | `test_partner_pool.py`, `test_partner_expiry.py`, `test_partner_license_writers.py` pass |
| 4 | Partner admins and viewers reach only their own customers' seats and usage through every route; two partners see none of each other's customers nor any customer's security data | VERIFIED | Portal isolation (`test_partner_isolation.py`); edge allowlist now immune to scheme spelling (probe above, route walk 19 pass); live feed refuses partners and tenant-filters events (3 tests). Socket.IO is by assumption and listed for a live check |
| 5 | Super Admin moves a customer between partners or to direct, seats returned and audited; pre-existing organizations stay direct; per-customer usage list with CSV | VERIFIED | `test_partner_move.py` (incl. new WR-05 case), `test_partner_usage.py`; migration 029 creates indexes only |

**Score:** 5/5 truths verified; 0 behavior-unverified.

### Requirements Coverage

All eight IDs PART-01 to PART-08 appear in plan frontmatter (87-14 claims all) and in REQUIREMENTS.md for Phase 87; no orphans. REQUIREMENTS.md still shows them as "Gaps Found" in its traceability table; the orchestrator should move them to complete once the human items are accepted or on its own rule.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| PART-01 appoint, pool, suspend/reinstate | SATISFIED | platform service, suspension per-request check; tests green. Live flow is a human item |
| PART-02 partner creates customer, invites first admin | SATISFIED | `create_customer`, invite flow; login now case-insensitive (WR-04) so invitee case no longer locks out |
| PART-03 seats never exceed pool, atomic | SATISFIED | 26 pool tests; WR-05 closed; WR-06 (transient over-claim) open as a warning |
| PART-04 expiry | SATISFIED | `test_partner_expiry.py` |
| PART-05 only own customers, only seats and usage, every route | SATISFIED | gaps 1 and 2 closed (above) |
| PART-06 screens within ceiling | SATISFIED | `test_partner_ceiling.py` |
| PART-07 only Super Admin moves; audited; existing stay direct | SATISFIED | `test_partner_move.py` |
| PART-08 usage roll-up and CSV | SATISFIED | `test_partner_usage.py`, PartnerPortal vitest |

### Key Link Verification

| From | To | Status | Details |
|------|----|--------|---------|
| `app_middleware.py` | `PartnerScopeMiddleware` | WIRED | now reads the header via shared `bearer_token()` |
| `tenant_middleware` / `audit_middleware` / `export_controls` | `bearer_token()` | WIRED | grep shows all three import it |
| `/api/stream/live` | partner role refusal and per-tenant filter | WIRED | closes 4403; `_live_event_allowed` applied in every client callback |
| `partner_endpoints` to `partner_portal_service` / `partner_pool` | real queries | WIRED | unchanged from previous report |
| shell to partner views | `isPartnerRoleName` | WIRED | `PartnerShell.test.tsx` passes |

### Data-Flow Trace (Level 4)

Unchanged and FLOWING: portal customers table, Partners screen pool bars and CSV all read real `tenants` queries filtered by `partnerId`. The live feed filter now operates on the real broker event `tenantId` field.

### Behavioral Spot-Checks (private mongod 127.0.0.1:27998, live database untouched)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 87 backend, roles, platform roles, tenant boundary, middleware cleanup | pytest `test_partner_*`, `test_catalogue_slice_partners`, `test_roles_endpoint`, `test_platform_roles`, `test_tenant_boundary_hardening`, `test_tenant_middleware_context_cleanup` | 406 passed | PASS |
| Review-fix and neighbours | pytest `test_login_me_permissions`, `test_closure_delivery`, `test_catalogue_manifest`, `test_catalogue_route_parity`, `test_route_auth_baseline`, `test_auth_mfa` | 190 passed, 2 failed (`test_sidebar_and_app_agree_with_manifest`, `test_ledger_ratchets`: both on the accepted baseline list) | PASS |
| Partner frontend | vitest PartnerPortal, partnerAccess, AcceptInvitePage, PartnersDashboard, PartnerShell | 6 files, 174 tests passed | PASS |
| Edge wall under scheme spellings | verifier probe (JWT through `PartnerScopeMiddleware`, GET /api/tenants) | seven spellings: all 403; no header 200 | PASS |

### Probe Execution

SKIPPED: the phase declares no probe scripts.

### Anti-Patterns Found

No TBD, FIXME or XXX markers or stubs found in the files changed for the gap fixes (`tenant_middleware.py`, `stream_processing_endpoints.py`, `partner_*.py`). The earlier two blockers are removed.

### Human Verification Required

See the `human_verification` frontmatter: the full backend suite by name against the baseline, the live partner flow after restart and publish (87-UAT.md is in progress), the browser pass, and live isolation including Socket.IO and the retailer trial.

### Gaps Summary

No open gaps. Status is `human_needed` solely because live checks need a backend restart, a UI publish, SMTP and real agents, all owned by the user. Open review items WR-06 to WR-11 and IN-01 to IN-10 are tracked in `87-REVIEW-DISPOSITION.md` and do not block any success criterion.

---

_Verified: 2026-11-04T08:05:00Z_
_Verifier: Claude (gsd-verifier)_
