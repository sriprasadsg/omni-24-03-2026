---
phase: "87"
slug: "partner-and-reseller-channel"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
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

- **After every task commit:** the task's new test file plus `backend/tests/test_rbac_defaults.py`
- **After every plan wave:** all `backend/tests/test_partner_*.py`, `test_catalogue_route_parity.py`, `test_catalogue_manifest.py`, `test_route_auth_baseline.py`, `test_tenant_feature_switches.py`, `test_licensing.py`, `test_tenant_license_api.py` on the private mongod; `npx vitest run src/__tests__`; `npm run build`
- **Before `/gsd-verify-work`:** full backend suite alone; compare failures by name with the 2026-11-02 baseline (5,711 passed; 4 known failures: test_audit_export::test_legacy_download_allows_owner, test_e2e_integration::test_cross_tenant_report_download_owner_allowed, test_catalogue_route_parity::test_ledger_ratchets, test_catalogue_manifest::test_sidebar_and_app_agree_with_manifest)
- **Max feedback latency:** 60 seconds for a quick run

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 87-TBD | TBD | TBD | PART-03 | TBD | 20 concurrent allotments never exceed the pool; compare-and-swap on one customer; lower only to seats used; pool shrink refused with the handed-out count | real-Mongo integration | `pytest backend/tests/test_partner_pool.py -x` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | PART-03 | TBD | Every writer of `license.maxAgents` is pool-aware (tenant license PATCH, pending-agent raise, tenant creation); drift test forbids new writers | unit + structural | `pytest backend/tests/test_partner_license_writers.py -x` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | PART-04 | TBD | Expired pool refuses customer creation and seat hand-out; a partner customer's new agent is held `license_expired`; running agents unaffected | real-Mongo integration | `pytest backend/tests/test_partner_expiry.py -x` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | PART-05 | TBD | Two partners: neither sees the other's customers, direct customers or partner orgs; response keys equal the D-01 allowlist exactly; a foreign customer id is 404 | real-Mongo integration | `pytest backend/tests/test_partner_isolation.py -x` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | PART-05 | TBD | Partner roles fail `can_read_all_tenants` and `has_platform_permission`, are in no super or platform role set, hold only the partner permissions; a viewer's write is refused | unit | `pytest backend/tests/test_partner_roles.py -x` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | PART-05 | TBD | Route walk with a partner token: every mounted route outside the partner allowlist and self-service prefixes denies | contract | `pytest backend/tests/test_partner_route_walk.py -x` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | PART-01 | TBD | Suspend: an existing access token gets 403 on its next request, refresh and login are refused, customers and seats untouched; reinstate restores | real-Mongo integration | `pytest backend/tests/test_partner_suspension.py -x` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | PART-02 | TBD | Creating a customer draws seats; the invite has a 7-day expiry; the response carries no token, link or registration key; a global email clash is refused; accepting requires MFA enrolment for admins | real-Mongo integration | `pytest backend/tests/test_partner_customers.py -x` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | PART-06 | TBD | Customer screens must be a subset of the ceiling; start screens allowed; unknown strings and `all` refused; parents required; existing screens kept when the ceiling shrinks (D-19) | unit | `pytest backend/tests/test_partner_ceiling.py -x` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | PART-07 | TBD | Move returns the allotment and claims the new pool or answers 409 with the free count (D-18); audit entry chained; organizations that existed before migration 029 have no `partnerId` | real-Mongo integration | `pytest backend/tests/test_partner_move.py -x` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | PART-08 | TBD | Overview totals equal pool size, handed out and free; per-customer counts match the seat counters; CSV export guarded against formula injection | integration + vitest | `pytest backend/tests/test_partner_usage.py -x`; `npx vitest run src/__tests__/<partner portal test>` | ❌ W0 | ⬜ pending |
| 87-TBD | TBD | TBD | Catalogue | — | New `partners` and `partnerPortal` catalogues mounted, guarded and in parity; pinned counts updated deliberately | contract | `pytest backend/tests/test_catalogue_route_parity.py backend/tests/test_catalogue_manifest.py backend/tests/test_route_auth_baseline.py -x` | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Run (without editing) `test_catalogue_manifest.py`, `test_catalogue_slice_*`, `test_tenant_feature_switches.py`, `test_custom_role_mfa.py` and `test_rbac_defaults.py` to learn the pinned counts the two new catalogues and roles will trip
- [ ] `backend/tests/_partner_fixtures.py` — two partners, three customers each, one direct customer, users of each role, tokens
- [ ] Every test file marked ❌ W0 above, written before the code that satisfies it
- [ ] The private mongod recipe above in every database test command

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Invite email delivery and first sign-in of an invited customer admin and partner admin | PART-01, PART-02 | SMTP is not configured on this VM; delivery and the link's host need a real mail setup | Configure SMTP and `FRONTEND_URL`, invite a test admin, open the link, set a password, enrol MFA |
| Browser pass of the Partners screen, Partner portal (admin and viewer) and Accept-invite page | PART-01, PART-02, PART-05, PART-08 | Needs a published UI | Light and dark at 640, 1024 and 1280 px; a partner user sees only the portal |
| A real retailer trial: 2+ partners with 100 and 1,000 seats, customers enrolling real agents | PART-03, PART-05 | Needs real agents and a published UI | Appoint partners, create customers, install agents up to the allotment, confirm the next is held |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
