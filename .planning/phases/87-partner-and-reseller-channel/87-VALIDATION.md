---
phase: "87"
slug: "partner-and-reseller-channel"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-02"
---

# Phase 87 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Seeded from 87-RESEARCH.md "Validation Architecture"; the planner replaces each 87-TBD with real task ids.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Backend: pytest + pytest-asyncio. Frontend: vitest 5 + @testing-library/react (jsdom) |
| **Config file** | `pytest.ini`, `backend/tests/conftest.py`, vitest in `package.json` scripts |
| **Quick run command** | `MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=mongodb://127.0.0.1:27998 MONGO_URI=mongodb://127.0.0.1:27998 backend/venv/bin/python -m pytest backend/tests/test_partner_pool.py -x -q -p no:cacheprovider` |
| **Full suite command** | `npx vitest run src/__tests__`, `npm run build`, and the full backend suite alone on the private mongod (`backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` with the three Mongo variables and temp `TICKET_ATTACHMENT_DIR`/`FILE_SHARE_DIR`) |
| **Estimated runtime** | Quick run under 60 s; full backend suite about 33 minutes, alone on the VM |

**Database rule:** the `mongo_db` fixture defaults to the LIVE mongod on 27017. Every database test runs on a private mongod: `GLIBC_TUNABLES=glibc.pthread.rseq=1 /usr/bin/mongod --dbpath <tmp> --port 27998 --bind_ip 127.0.0.1 --wiredTigerCacheSizeGB 0.25 --fork --logpath <tmp>/mongod.log --pidfilepath <tmp>/mongod.pid`, with `MONGO_TEST_URL`, `MONGODB_URL` and `MONGO_URI` all set.

---

## Sampling Rate

- **After every task commit:** the task's new test file plus `backend/tests/test_rbac_defaults.py` (87-01 excepted: its new roles and catalogues trip the pinned counts until 87-15, the only wave-2 plan, moves them)
- **After every plan wave:** all `backend/tests/test_partner_*.py`, `test_catalogue_route_parity.py`, `test_catalogue_manifest.py`, `test_route_auth_baseline.py`, `test_tenant_feature_switches.py`, `test_licensing.py`, `test_tenant_license_api.py` on the private mongod; `npx vitest run src/__tests__`; `npm run build`
- **Before `/gsd-verify-work`:** full backend suite alone; compare failures by name with the 2026-11-02 baseline (5,711 passed; 4 known failures: test_audit_export::test_legacy_download_allows_owner, test_e2e_integration::test_cross_tenant_report_download_owner_allowed, test_catalogue_route_parity::test_ledger_ratchets, test_catalogue_manifest::test_sidebar_and_app_agree_with_manifest)
- **Max feedback latency:** 60 seconds for a quick run

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 87-01-02 | 87-01 | 1 | PART-01/02/03/05/08 | T-87-01, T-87-02, T-87-03 | Tracer: appoint, create a customer from the pool, overview with only the D-01 keys, guarded routes | real-Mongo end to end | `pytest backend/tests/test_partner_tracer.py` | ✅ | ✅ green |
| 87-15-01 | 87-15 | 2 | PART-01 | — | AppView, Permission and Tenant unions and sidebar icons know `partners` and `partnerPortal`; nav count 192 | vitest | `npx vitest run src/__tests__/catalogueAccess.test.ts src/__tests__/viewAccess.test.ts src/__tests__/SidebarFailClosed.test.tsx` | ✅ | ✅ green |
| 87-15-02 | 87-15 | 2 | PART-05 | T-87-44, T-87-45 | Pinned counts moved deliberately; GOLDEN pins the partner roles to their own permissions; partner roles left out of TENANT_PERMS by role key | contract | `pytest backend/tests/test_rbac_defaults.py backend/tests/test_catalogue_manifest.py backend/tests/test_catalogue_route_parity.py backend/tests/test_sidebar_screen_switches.py` | ✅ | ✅ green (only the 2 pre-phase baseline failures) |
| 87-02-01, 87-02-02 | 87-02 | 3 | PART-05 | T-87-04, T-87-05, T-87-06 | Partner roles fail `can_read_all_tenants` and `has_platform_permission`, are in no super or platform role set, hold only the partner permissions; MFA for partner admins only; partner roles only in partner organizations | unit + real-Mongo | `pytest backend/tests/test_partner_roles.py backend/tests/test_custom_role_mfa.py` | ✅ | ✅ green |
| 87-03-01, 87-03-02 | 87-03 | 3 | PART-03, PART-07 | T-87-07, T-87-08, T-87-09 | 20 concurrent allotments never exceed the pool; compare-and-swap on one customer; lower only to seats used; pool shrink refused with the handed-out count; moves claim the new pool; migration 029 leaves existing organizations without `partnerId` | real-Mongo integration | `pytest backend/tests/test_partner_pool.py` | ✅ | ✅ green |
| 87-04-01, 87-04-02 | 87-04 | 3 | PART-01 | T-87-10, T-87-11, T-87-12 | Suspend: an existing access token gets 403 on its next request, refresh and login are refused, customers and seats untouched; reinstate restores | integration | `pytest backend/tests/test_partner_suspension.py` | ✅ | ✅ green |
| 87-05-01 | 87-05 | 3 | PART-05 | T-87-13, T-87-14 | Route walk with a partner token: every mounted route outside the partner allowlist and self-service prefixes is refused; a viewer's write is refused | contract | `pytest backend/tests/test_partner_route_walk.py` | ✅ | ✅ green |
| 87-05-02 | 87-05 | 3 | Catalogue | — | Partner routers carry their manifest guards | contract | `pytest backend/tests/test_catalogue_slice_partners.py` | ✅ | ✅ green |
| 87-06-01, 87-06-02 | 87-06 | 3 | PART-02 | T-87-16 .. T-87-19 | Invites: 7-day single-use link, no token in any response, global email clash refused, public status route | real-Mongo integration | `pytest backend/tests/test_partner_invites.py` | ✅ | ✅ green |
| 87-07-01 .. 87-07-03 | 87-07 | 3 | PART-01, PART-05, PART-06 | T-87-20, T-87-21 | Portal hidden from non-partner roles; suspended session ends on the sign-in page; picker limited to the ceiling | vitest | `npx vitest run src/__tests__/partnerAccess.test.ts src/__tests__/PartnerScreenPicker.test.tsx` | ✅ | ✅ green |
| 87-08-01 .. 87-08-03 | 87-08 | 4 | PART-01, PART-03, PART-07 | T-87-22 .. T-87-25 | Appoint with first admin, pool floor, ceiling validation, suspend locks the partner only, audited moves with the free count | real-Mongo integration | `pytest backend/tests/test_partner_platform.py backend/tests/test_partner_move.py` | ✅ | ✅ green |
| 87-09-01 | 87-09 | 4 | PART-02, PART-04 | T-87-29, T-87-30 | Creating a customer draws seats and invites its admin; no token or registration key; expired pool refuses creation and hand-out | real-Mongo integration | `pytest backend/tests/test_partner_customers.py` | ✅ | ✅ green |
| 87-09-02 | 87-09 | 4 | PART-06 | T-87-27 | Customer screens within the ceiling; start screens allowed; unknown strings and `all` refused; parents required; existing screens kept (D-19) | real-Mongo integration | `pytest backend/tests/test_partner_ceiling.py` | ✅ | ✅ green |
| 87-09-03 | 87-09 | 4 | PART-05, PART-08 | T-87-26, T-87-28 | Two partners: neither sees the other's customers, direct customers or partner orgs; keys equal the D-01 allowlist; foreign id 404; usage totals match the counters | real-Mongo integration | `pytest backend/tests/test_partner_isolation.py backend/tests/test_partner_usage.py` | ✅ | ✅ green |
| 87-10-01 .. 87-10-03 | 87-10 | 4 | PART-03, PART-04, PART-07 | T-87-31 .. T-87-34 | Every writer of `license.maxAgents` is pool-aware; drift test forbids new writers; a partner customer's new agent is held `license_expired` after pool expiry; running agents unaffected | real-Mongo + structural | `pytest backend/tests/test_partner_license_writers.py backend/tests/test_partner_expiry.py` | ✅ | ✅ green |
| 87-11-01 .. 87-11-03 | 87-11 | 4 | PART-01, PART-07 | T-87-35, T-87-36 | Partners screen, appoint/edit form, suspend/reinstate and move dialogs in every UI-SPEC state | vitest | `npx vitest run src/__tests__/PartnersDashboard.test.tsx src/__tests__/PartnerAdminModals.test.tsx` | ✅ | ✅ green |
| 87-12-01 .. 87-12-03 | 87-12 | 4 | PART-05, PART-08 | T-87-37 .. T-87-39 | Portal renders and exports only the D-01 fields; CSV formula-guarded; viewer has no controls | vitest | `npx vitest run src/__tests__/PartnerPortal.test.tsx src/__tests__/PartnerPortalModals.test.tsx` | ✅ | ✅ green |
| 87-13-01, 87-13-02 | 87-13 | 4 | PART-02 | T-87-40, T-87-41 | Accept invite: token removed from the address bar, every state, sign-in once, MFA by the existing flow | vitest | `npx vitest run src/__tests__/AcceptInvitePage.test.tsx` | ✅ | ✅ green |
| 87-14-01 .. 87-14-03 | 87-14 | 5 | all | T-87-42, T-87-43 | Partner shell calls only partner routes; one sidebar entry; phase gates against the baseline | vitest + gates | `npx vitest run src/__tests__`; `npm run build`; partner and parity pytest set (87-14 Task 3) | ✅ | ✅ green (pytest set: only the 2 pre-phase baseline failures) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] Run (without editing) `test_catalogue_manifest.py`, `test_catalogue_slice_*`, `test_tenant_feature_switches.py`, `test_custom_role_mfa.py` and `test_rbac_defaults.py` to learn the pinned counts the two new catalogues and roles will trip
- [x] Partner fixtures (two partners, customers, one direct customer, users of each role, tokens) — built inside each `test_partner_*.py` file rather than a shared `backend/tests/_partner_fixtures.py`
- [x] Every test file marked ❌ W0 above, written before the code that satisfies it
- [x] The private mongod recipe above in every database test command

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Invite email delivery and first sign-in of an invited customer admin and partner admin | PART-01, PART-02 | SMTP is not configured on this VM; delivery and the link's host need a real mail setup | Configure SMTP and `FRONTEND_URL`, invite a test admin, open the link, set a password, enrol MFA |
| Browser pass of the Partners screen, Partner portal (admin and viewer) and Accept-invite page | PART-01, PART-02, PART-05, PART-08 | Needs a published UI | Light and dark at 640, 1024 and 1280 px; a partner user sees only the portal |
| A real retailer trial: 2+ partners with 100 and 1,000 seats, customers enrolling real agents | PART-03, PART-05 | Needs real agents and a published UI | Appoint partners, create customers, install agents up to the allotment, confirm the next is held |
| Live isolation on the running app | PART-01, PART-05 | The route walk and isolation tests call route functions and the test app, not the deployed backend. Socket.IO still connects for any signed-in user (A-87-A5) | After the restart, use a partner token on customer pages and APIs (all refused). Confirm Socket.IO delivers nothing of customers to a partner session. Suspend a partner and confirm its users are signed out while its customers' agents keep reporting |
| Full backend suite against the baseline | all | About 33 minutes alone on the 2-vCPU VM; not run during execution | Run `backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` on the private mongod with the three Mongo variables and temporary TICKET_ATTACHMENT_DIR and FILE_SHARE_DIR. The failures must be exactly the four baseline names above |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-11-03 (validate-phase audit after execution)

## Validation Audit 2026-11-03

| Metric | Count |
|---|---|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
