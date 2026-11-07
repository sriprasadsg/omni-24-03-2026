---
phase: 87-partner-and-reseller-channel
verified: 2026-11-07T15:20:00Z
status: passed
score: 5/5 must-haves verified
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
  - "backend/auth_password_reset_endpoints.py"
  - "backend/authentication_endpoints.py"
  - "backend/authentication_service.py"
  - "backend/migrations/029_partner_channel.py"
  - "backend/partner_endpoints.py"
  - "backend/partner_invites.py"
  - "backend/partner_middleware.py"
  - "backend/partner_platform_endpoints.py"
  - "backend/partner_platform_service.py"
  - "backend/partner_pool.py"
  - "backend/partner_portal_service.py"
  - "backend/partner_status.py"
  - "backend/partner_store.py"
  - "backend/role_endpoints.py"
  - "backend/stream_processing_endpoints.py"
  - "backend/tenant_middleware.py"
  - "components/AcceptInvitePage.tsx"
  - "components/PartnerPortal.tsx"
  - "components/PartnersDashboard.tsx"
  - "services/partnerApi.ts"
covered_digest: "v3:sha256:70dfb556a5f6094f24eabd4ed8545b373b0cc51d8bfaa3c7e676646bee3bdb55"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/5 at HEAD f86bcc397 (5/5 on the working tree)
  gaps_closed:
    - "Invite e-mail (PART-02 / SC2): partner_invites imported _resolve_smtp_config, which was uncommitted; committed in 422af6095 (PLATFORM_TENANT_ID + the resolver, 41 lines)"
  gaps_remaining: []
  regressions: []
  history:
    - "2026-11-04 08:05Z human_needed 5/5 (after T-87-13 and live-feed gap closure)"
    - "2026-11-07 14:45Z gaps_found 4/5 at HEAD f86bcc397 (invite mail depended on uncommitted resolver)"
    - "2026-11-07 15:20Z passed 5/5 at HEAD 422af6095"
gaps: []
deferred: []
human_verification: []

---

# Phase 87: Partner and Reseller Channel Verification Report

**Phase Goal:** The platform can sell through partners the way a vendor appoints dealers: a Super Admin appoints partner organizations and gives each a pool of agent seats, a partner creates and manages its own customer organizations and assigns seats to each from its pool, a partner admin sees only that partner's customers, and usage rolls up per partner.
**Verified:** 2026-11-07T15:20:00Z
**Status:** passed
**Re-verification:** Yes. Previous report 2026-11-04 (human_needed 5/5) was stale: the audit and fix rounds, the partner UI QA fixes, migration 030 and Phase 84 changed covered files.

## How this was judged

Committed HEAD (422af6095; the earlier run of this report was at f86bcc397, and the only change between the two is the 41-line resolver commit) is the subject. The working tree carries about 2,377 uncommitted entries of the user's work, so the verifier extracted `git archive HEAD` (backend, shared, front-end sources) into a scratch directory and ran Phase 87's backend tests there against the private mongod (127.0.0.1:27998), in addition to the working tree runs. Every Phase 87 backend file (`partner_*.py`, `tenant_middleware.py`, `stream_processing_endpoints.py`, `audit_middleware.py`, `role_endpoints.py`, migration 029) and every Phase 87 front-end component is identical between HEAD and the working tree. The only place where the two differ for this phase is the invite-mail dependency below.

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Super Admin appoints a partner with pool, expiry and screen ceiling from a Partners screen, sees every pool used and free, can suspend (users locked out, customers keep running) | VERIFIED | HEAD run: `test_partner_platform.py`, `test_partner_suspension.py` (14), `test_partner_expiry.py` green. Suspension chokepoint is in the token verifier (`authentication_service.py:411-412`, `partner_status.refuse_if_suspended`) and in login (`authentication_endpoints.py:236-240`) and refresh (`:507`). Vitest PartnersDashboard green. UAT 3, 4, 13 pass |
| 2 | Partner admin creates a customer with seats from the pool and invites its first admin, who runs it like a direct customer; screens only within the ceiling | VERIFIED | Customer creation, pool claim and ceiling verified (`test_partner_customers.py`, `test_partner_ceiling.py` green). The invite is created (user, single-use seven-day token, hashed storage) and the e-mail path now resolves: `auth_password_reset_endpoints.py` at HEAD defines `PLATFORM_TENANT_ID` (line 43) and `_resolve_smtp_config` (line 46), which `partner_invites.py:93` imports. `test_partner_invites.py` 24/24 on a clean HEAD snapshot |
| 3 | Seats never exceed the pool under concurrency; lower only to seats used; pool cannot shrink below handed out; after expiry no customer and no seat | VERIFIED | `partner_pool.claim` is one `update_one` with `$expr: allocated + n <= poolSize` and `$inc` (no read-modify-write); increases claim first, decreases write the customer first, so a crash can only leak seats. `test_partner_pool.py` (28) and `test_partner_expiry.py` (6) green at HEAD. UAT 11 pass |
| 4 | Partner admins and viewers reach only their own customers' seats and usage through every route; two partners see no one else's customers nor any customer's security data | VERIFIED | `PartnerScopeMiddleware` is mounted in HEAD `app_middleware.py` (lines 212, 218) and allowlists `/api/partner`, `/api/auth|mfa|passkey/` and `GET /api/platform/features` only; scheme parsing goes through the shared `bearer_token()` (`tenant_middleware.py:102`). Portal queries are all keyed by `{"id": customer_id, "partnerId": partner_id}` (`partner_portal_service.py:37,138,174,198`). `/api/stream/live` closes 4403 for partner roles and filters events per tenant (`stream_processing_endpoints.py:70-110`). `test_partner_route_walk.py` (19), `test_partner_isolation.py` (9), `test_tenant_boundary_hardening.py` green at HEAD. UAT 10, 12, 13 pass (user accepted Socket.IO isolation live) |
| 5 | Super Admin moves a customer between partners or to direct, seats returned and audited; pre-existing orgs stay direct; per-customer usage list with CSV | VERIFIED | `test_partner_move.py` (15), `test_partner_usage.py` green at HEAD; migration 029 creates indexes only; vitest PartnerPortal green |

**Score:** 5 of 5 verified at committed HEAD; 0 behavior-unverified.

### Requirements Coverage

All eight IDs PART-01..PART-08 are claimed by plan frontmatter (87-14 claims all) and mapped to Phase 87 in REQUIREMENTS.md (lines 88-95, traceability 250-257); no orphans. The traceability table still reads "Pending" for all eight; that is a bookkeeping item for the orchestrator once the gap is closed.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| PART-01 appoint, pool, suspend/reinstate | SATISFIED | tests above; suspension at token verifier, login, refresh |
| PART-02 partner creates customer, invites first admin by e-mail | SATISFIED | creation, invite record and e-mail resolver all committed (422af6095); 24 invite tests pass at HEAD |
| PART-03 seats never exceed pool, atomic | SATISFIED | `partner_pool.claim` (atomic `$expr` update); 28 pool tests |
| PART-04 expiry | SATISFIED | `test_partner_expiry.py` |
| PART-05 only own customers, seats and usage, every route | SATISFIED | edge allowlist, portal scoping, live-feed filter; route walk |
| PART-06 screens within ceiling | SATISFIED | `test_partner_ceiling.py` |
| PART-07 only Super Admin moves; audited; existing stay direct | SATISFIED | `test_partner_move.py` |
| PART-08 usage roll-up and CSV | SATISFIED | `test_partner_usage.py`, PartnerPortal vitest |

### Required Artifacts and Key Links

All partner backend modules, migration 029, router registration (`router_registry.py:128-129`), `PartnerScopeMiddleware` mount and front-end components exist at HEAD, are substantive (1,816 lines across the nine `partner_*.py` modules plus tenant middleware) and are wired (route walk and component tests exercise them end to end). Data flow is real: portal and Partners screen read `tenants` queries keyed by `partnerId`; no static returns found. The previously broken link `partner_invites.send_invite_email` to `auth_password_reset_endpoints._resolve_smtp_config` is now defined at HEAD (422af6095).

### Behavioral Spot-Checks (private mongod 127.0.0.1:27998; live database untouched)

| Behavior | Command (abridged) | Result | Status |
|----------|--------------------|--------|--------|
| Pool, route walk, isolation, suspension, expiry, move on HEAD snapshot | pytest `test_partner_pool/route_walk/isolation/suspension/expiry/move` | 91 passed | PASS |
| Rest of Phase 87 plus neighbours on HEAD snapshot (f86bcc397; invite failures since fixed) | pytest `test_partner_ceiling/customers/invites/license_writers/platform/roles/tracer/usage`, `test_catalogue_slice_partners`, `test_tenant_boundary_hardening`, `test_tenant_middleware_context_cleanup`, `test_rbac_defaults`, `test_closure_delivery` | 272 passed, 4 failed: 3 are the invite-mail gap; 1 (`test_rbac_defaults::test_role_writing_scripts_are_archived`) is a snapshot artefact (the `archive/` directory was not extracted), not a finding | 3 FAIL (gap), 1 n/a |
| Re-run on fresh HEAD 422af6095 snapshot | pytest `test_partner_invites`, `test_partner_route_walk` | 43 passed | PASS |
| Catalogue, session revocation and invites on the working tree | pytest `test_catalogue_manifest`, `test_catalogue_route_parity`, `test_session_revocation`, `test_partner_invites` | 123 passed | PASS |
| Partner and shell front end on the working tree | vitest Partner*, partnerAccess, AcceptInvitePage, SidebarFailClosed, catalogueAccess, viewAccess | 11 files, 332 passed | PASS |
| Orchestrator gates (HEAD code, not re-run) | full vitest 1,606; Phase 87 22 backend files 465; Autonomous Ops/patch 1,531 | all green per orchestrator | taken as given |

Nav-count pins: the old "190" pins are now `192` in `catalogueAccess.test.ts:49`, `test_catalogue_manifest.py:161` and `test_closure_delivery.py:214`; all pass, and grep finds no `.skip`, `.todo` or `xit` in the Phase 87 test files. Resolved, not skipped.

### Probe Execution

SKIPPED: the phase declares no probe scripts.

### Anti-Patterns Found

No TBD, FIXME or XXX markers in the Phase 87 backend files. One blanket `except Exception` in `partner_invites.send_invite_email` turned the earlier missing import into a silent "not sent" result. Info only: the import now resolves, and the tests that cover the mail path would catch a recurrence.

### Facts the orchestrator asked to check

- **`backend/export_controls.py`**: the file is untracked (`??`), has never been committed, and HEAD's `app_middleware.py` does not import it. It is not part of Phase 87 at HEAD (the 2026-11-04 report listing it as covered was wrong, and it is dropped from `covered_files` here). The working-tree version already parses the header through the shared `bearer_token()` and passes agent and unauthenticated callers through, so it neither weakens nor strengthens the partner wall (partner tokens are refused earlier by `PartnerScopeMiddleware` for every non-portal route). It changes nothing in this verdict.
- **Other working-tree differences touching Phase 87 files**: `authentication_service.py` / `authentication_endpoints.py` carry an uncommitted `mfa_exempt` claim (set only from a server-written account flag) that lets an exempt account skip admin MFA. No partner account is exempt by design and no API sets the flag, so the partner-MFA rule (D-02 / PART-02) is unchanged; `test_partner_roles.py` and `test_custom_role_mfa.py` pass either way. Worth a conscious look if a partner admin is ever given that flag.
- **Review/security**: `87-SECURITY.md` is `verified`, `threats_open: 0`; `87-REVIEW-DISPOSITION.md` lists WR-01..WR-11 as fixed. UAT is 95/95 with no skipped, blocked or pending tests. No new human item is raised: the five user-accepted tests (5, 10, 11, 12, 13) are not re-raised.

### Human Verification Required

None. (UAT 5, the invite e-mail, passed on the live system, which runs the working tree; the gap is about what is committed, not about live behavior.)

### Gaps Summary

No open gaps. The single gap from the 14:45Z run (the committed invite-mail code importing `_resolve_smtp_config`, which lived only in uncommitted working-tree code) is closed by commit 422af6095, which adds only `PLATFORM_TENANT_ID` and the resolver (41 lines) to `backend/auth_password_reset_endpoints.py`. Confirmed by reading HEAD's file and by running `test_partner_invites.py` plus `test_partner_route_walk.py` on a fresh `git archive HEAD` snapshot (backend, shared, pytest.ini) against the private mongod 127.0.0.1:27998: 43 passed (24 invites, 19 route walk). `git diff f86bcc397 HEAD --stat` shows that one 41-line addition is the only change since the earlier run, so every other result in this report still holds. The user's password-reset mail and FRONTEND_URL edits in the same file remain uncommitted; they do not affect any Phase 87 truth (the resolver is self-contained). No new human items; UAT is 95/95.

---

_Verified: 2026-11-07T14:45:00Z_
_Verifier: Claude (gsd-verifier)_
