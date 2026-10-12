---
phase: "75"
slug: "permission-resolver-single-source-of-truth"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-12"
---

# Phase 75 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Client → `/api/auth/login`, `/me`, MFA verify, signup | Pre- and post-authentication session mint; `/login` runs with no tenant ContextVar | Credentials in; effective permission list out (authorization data) |
| Request → role store (`db._db.roles`) | Raw-handle reads that bypass the tenant-isolation wrapper | Role documents of the caller's own tenant plus the `all`/`platform` sentinels |
| Tenant admin / itam_admin → user CRUD, LDAP/SAML mapping routes | Role assignment and account management inside a tenant | Target role, password, status, tenant, mapping role |
| Tenant user → `/api/bundles/tenant/{id}/*` | `tenants` collection is exempt from tenant isolation | Feature bundles / enabledFeatures (billing tier) |
| Browser sessionStorage | Cached API lists that outlive a sign-in within a tab | Role list and other tenant data |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-75-01 | Elevation of Privilege | delivery vs enforcement divergence | high | mitigate | One resolver (`rbac_service.effective_permissions`) behind `/login`, `/me`, `verify_permission`, `RBACService`; parity tests | closed |
| T-75-02 | Information Disclosure | `_role_docs` raw-handle read | high | mitigate | Reads keyed `{name, tenantId}` for the caller's own tenant and the `all`/`platform` sentinels only; cross-tenant test | closed |
| T-75-03 | Elevation of Privilege | role-store outage | medium | mitigate | `verify_permission` fails closed (`rbac_utils.py` except → deny); session paths degrade to table defaults only | closed |
| T-75-04 | Denial of Service | login for a role with no permissions | low | mitigate | D-19: login 200 with `[]` plus a warning naming the role; tested | closed |
| T-75-05 | Elevation of Privilege | table contents | high | mitigate | `manage:tenants` and the six D-03 catalogues absent from every non-super set; golden/invariant tests in `test_rbac_defaults.py` | closed |
| T-75-06 | Tampering | seed upsert | high | mitigate | Raw-handle `update_one` filtered on `{name, tenantId}`; `test_role_seeding.py` proves tenant same-name docs untouched | closed |
| T-75-07 | Elevation of Privilege | stale shared documents | medium | mitigate | Every boot rewrites shared documents from the table; tested | closed |
| T-75-08 | Elevation of Privilege | per-user permissions array at signup | low | mitigate | D-07: signup no longer writes it; nothing reads it; tested | closed |
| T-75-09 | Information Disclosure | MFA verify response | low | accept | Returns only the caller's own permission list (same as `/me`) | closed |
| T-75-10 | Information Disclosure | `GET /api/roles` tenant documents | high | mitigate | Raw read filtered on the caller's own `tenantId`; cross-tenant test | closed |
| T-75-11 | Information Disclosure | Super Admin entry in role list | low | mitigate | Listed only when `is_super_admin(caller.role)`; tested both ways | closed |
| T-75-12 | Elevation of Privilege | role list access | medium | mitigate | `_require_role_list_access` (manage:users OR manage:rbac); 403 for viewer/user/itam_viewer | closed |
| T-75-13 | Information Disclosure | cached data in sessionStorage | low | mitigate | `clearSessionCaches()` on logout/expiry clears every `omni_cache_*` key (extended by review fix WR-08); 403 drops the cached copy | closed |
| T-75-14 | Elevation of Privilege | frontend permission fallback | medium | mitigate | `derivePermissionState` reads only `currentUser.permissions`; empty = no access; vitest | closed |
| T-75-15 | Tampering | PUT/PATCH/DELETE `/api/bundles/tenant/{id}/assign` | high | mitigate | `Depends(require_super_admin)` on all three routes; tenant-doc `manage:tenants` case tested | closed |
| T-75-16 | Elevation of Privilege | user create/update role field | critical | mitigate | `assert_can_assign_role` subset ceiling; 100-case matrix; account-side ceiling `assert_can_manage_account` added by review fix CR-01 | closed |
| T-75-17 | Elevation of Privilege | self role change | high | mitigate | D-20 rule 2: 403 when a caller's own role would change; tested | closed |
| T-75-18 | Elevation of Privilege | `*` inside a tenant role document | high | mitigate | Super-admin tier decided by `_normalize_role` only; resolver also ignores `*`/super-only strings in documents (review fix WR-01) | closed |
| T-75-19 | Elevation of Privilege | role-store outage during assignment | medium | mitigate | Resolver errors → 503, assignment refused (fail closed); tested | closed |
| T-75-20 | Elevation of Privilege | LDAP/SAML mapping writes | critical | mitigate | `assert_can_assign_role` before `upsert_mapping` on both routes; mapping deletes also checked (review fix WR-04) | closed |
| T-75-21 | Elevation of Privilege | mapping application at sign-in | critical | mitigate | `sync_user` / `provision_user` refuse any super-admin-tier role and keep the existing/default role; tested | closed |
| T-75-22 | Tampering | one-off role-writing scripts | medium | mitigate | D-14: five scripts moved with `git mv` to `archive/backend-rbac-oneoffs/` with `ARCHIVED.md`; absent from `backend/` | closed |
| T-75-23 | Tampering | second permission table reintroduced | medium | mitigate | AST drift guard `test_no_second_permission_table` with scanner self-tests | closed |
| T-75-SC | Tampering | npm/pip installs | low | accept | No package installed or added in any plan | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-75-01 | T-75-09 | MFA verify returns the caller's own permission list, identical to what `/me` returns to the same session — no new disclosure | plan-time disposition (75-02-PLAN) | 2026-10-12 |
| AR-75-02 | T-75-SC | No dependency was installed or added in Phase 75; no supply-chain surface to audit | plan-time disposition (75-01..05-PLAN) | 2026-10-12 |

**Related residuals outside the threat register (tracked, non-blocking):** code-review findings WR-04 (apply-time re-check of tenant-level mapping roles written before the ceiling existed — needs a mapping-schema change) and WR-06 (product decision on `isEditable` for shared role documents) remain `open` in `75-REVIEW-DISPOSITION.md`; the WR-05 residual login-vs-revoke race is documented in `75-REVIEW-FIX.md`. `GET /api/bundles/tenant/{id}/features` cross-tenant read was closed by review fix WR-02.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-12 | 24 | 24 | 0 | /gsd-secure-phase orchestrator (L1 grep-depth; register authored at plan time; ASVS 1 — auditor skipped per short-circuit rule) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-12
