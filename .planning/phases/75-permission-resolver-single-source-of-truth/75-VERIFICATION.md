---
phase: 75-permission-resolver-single-source-of-truth
verified: 2026-10-12T23:30:00Z
status: human_needed
score: 4/4 roadmap success criteria verified (code level); 2 live-only checks pending
covered_files:
  - .planning/phases/75-permission-resolver-single-source-of-truth/75-01-PLAN.md
  - .planning/phases/75-permission-resolver-single-source-of-truth/75-01-SUMMARY.md
  - .planning/phases/75-permission-resolver-single-source-of-truth/75-02-PLAN.md
  - .planning/phases/75-permission-resolver-single-source-of-truth/75-02-SUMMARY.md
  - .planning/phases/75-permission-resolver-single-source-of-truth/75-03-PLAN.md
  - .planning/phases/75-permission-resolver-single-source-of-truth/75-03-SUMMARY.md
  - .planning/phases/75-permission-resolver-single-source-of-truth/75-04-PLAN.md
  - .planning/phases/75-permission-resolver-single-source-of-truth/75-04-SUMMARY.md
  - .planning/phases/75-permission-resolver-single-source-of-truth/75-05-PLAN.md
  - .planning/phases/75-permission-resolver-single-source-of-truth/75-05-SUMMARY.md
  - backend/app_startup.py
  - backend/authentication_endpoints.py
  - backend/bundle_endpoints.py
  - backend/mfa_endpoints.py
  - backend/rbac_defaults.py
  - backend/rbac_service.py
  - backend/rbac_utils.py
  - backend/role_assignment.py
  - backend/role_endpoints.py
  - backend/user_endpoints.py
  - utils/permissions.ts
covered_digest: "v3:sha256:a5cabcd83cbab18c94ebb2f7e75ab0ba5ff1a6ce26b8c4d34c5933f75896104f"
behavior_unverified: 0
overrides_applied: 0
re_verification: false
human_verification:
  - test: "Restart the backend (user-owned), then inspect the live `roles` collection in omni_platform."
    expected: "11 shared documents: itam_admin, itam_user, itam_viewer, admin, Tenant Admin, analyst, security_analyst, incident_responder, user, viewer at tenantId 'all', and Super Admin at tenantId 'platform' with permissions ['*']; tenant-scoped same-named documents untouched."
    why_human: "Seeding runs on startup only. Services were deliberately not restarted and the live DB was not written, so this was proven only against the throwaway test DB."
  - test: "After the restart and UI redeploy, log in through the deployed UI as a user holding each of itam_admin, itam_user and itam_viewer."
    expected: "Login response and /me carry the same non-empty permission list; the sidebar shows only catalogues in that list intersected with the tenant's enabledFeatures; an itam_admin sees Settings > Roles listing the ITAM roles, an itam_viewer gets no role list (403 handled without breaking the data load)."
    why_human: "Needs the live deployment, a real browser session and real tenant enabledFeatures. Not verifiable from the repository."
  - test: "Policy confirmation for the review fixes marked 'requires human verification' in 75-REVIEW-FIX.md (CR-01 account-side ceiling; WR-01 resolver ignores '*'/super-admin-only strings in non-super role documents; WR-04/WR-06 partial fixes)."
    expected: "The owner accepts: equal-role accounts are manageable but higher ones are not; role documents are union-only; WR-04's apply-time re-validation (mappings written before the ceiling can still yield a tenant-level role at sign-in) and WR-06's isEditable semantics are deferred."
    why_human: "These are policy decisions, not code defects; tests pass but the intended policy needs a person."
---

# Phase 75: Permission Resolver & Single Source of Truth Verification Report

**Phase Goal:** Every user, including those on the ITAM roles, receives a complete, server-evaluated permission set at login from one defaults table, so the rest of the milestone can rely on a single answer to "what may this user do".
**Verified:** 2026-10-12
**Status:** human_needed (code-level goal achieved; live-only checks outstanding)
**Re-verification:** No, initial verification (codebase as it stands after the CR-01 / WR-01..08 fixes)

## Goal Achievement

### Observable Truths (ROADMAP success criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A user on itam_admin / itam_user / itam_viewer gets a non-empty permission list from both /login and /me | VERIFIED | `authentication_endpoints.py:225` (/login) and `:268` (/me) both call `session_permissions`. Independent run of `effective_permissions` against an empty role store: itam_admin 8, itam_user 5, itam_viewer 4 permissions. None holds `view:dashboard` (D-09); all keep `view:assets`. `test_login_me_permissions.py` passes. |
| 2 | /login and /me return the same effective set because both call one resolver; a test proves agreement | VERIFIED | Same function on both paths; resolver returns defaults first, then document extras, de-duplicated, so order is stable. `test_login_me_permissions.py` and `test_effective_permissions.py` pass (part of 348 passed). Signup (`:376`) and MFA verify (`mfa_endpoints.py:226`) also use it. |
| 3 | Exactly one defaults table; DEFAULT_PERMISSIONS / default_roles divergence gone; drift test fails on a second copy; control:remote_access stays distinct from view:remote_access | VERIFIED | `grep DEFAULT_PERMISSIONS backend/*.py` returns nothing. `rbac_service.default_roles` is derived from `rbac_defaults` (12 keys). `rbac_utils.verify_permission` delegates to `effective_permissions`. `test_no_second_permission_table` (AST scan of backend/*.py, with synthetic-offender tests) passes. tenant_admin holds both `control:remote_access` and `view:remote_access`; `implied_closure({'manage:remote_access'})` adds only view/request, never `control:`. |
| 4 | The three ITAM role documents exist after startup seeding and appear in an admin's role list; pre-existing custom roles resolve with no migration | VERIFIED (code and test DB); live part is a human item | `app_startup.py:319-334` loops `seed_role_documents()` (11 docs) through the raw handle with a `{name, tenantId}` filter and upsert. `role_endpoints.py` returns every `BUILTIN_ROLES` entry via `effective_permissions`, gated by manage:users or manage:rbac (`_require_role_list_access`). `test_role_seeding.py`, `test_roles_endpoint.py`, `test_custom_role_unchanged*` pass. |

### Plan-level truths and prohibitions (spot checks beyond the roadmap)

| Truth | Status | Evidence |
|-------|--------|----------|
| admin and Tenant Admin resolve to the same 127-permission set; no manage:tenants; no D-03 catalogues | VERIFIED | Run: both 127; intersection with `SUPER_ADMIN_ONLY_PERMISSIONS` is empty. |
| Super-admin variants resolve to `["*"]` | VERIFIED | Run: "Super Admin" and "platform-admin" each give a single-element list. |
| Empty/unknown role resolves to `[]` | VERIFIED | Run: "" and "bogus" give 0. |
| Role documents cannot inject `*` or super-admin-only strings (WR-01) | VERIFIED | `effective_permissions` filters `banned`; tests added. |
| Tenant isolation of role reads | VERIFIED | `_role_docs` queries only the caller's tenantId, "all" and "platform". Seed filter is `{name, tenantId}`. |
| Fail closed: verify_permission denies on role-store error; session_permissions degrades to defaults only | VERIFIED | `rbac_utils.py` returns False on exception; `session_permissions` falls back to `defaults_for`. |
| Bundle assignment PUT/PATCH/DELETE super-admin only (D-06) | VERIFIED | `Depends(require_super_admin)` at `bundle_endpoints.py:142,192,240`; covered by tests. |
| Role-assignment ceiling in user CRUD, plus account-side ceiling (CR-01) | VERIFIED | `assert_can_assign_role` / `assert_can_manage_account` called in create/update/delete in `user_endpoints.py`; ceiling matrix tests pass (33+ cases). |
| LDAP/SAML mapping ceiling at write time; super-admin tier refused at apply time | VERIFIED | `ldap_endpoints.py:177,199`, `sso_endpoints.py:377,399`; validators use `builtin_role_keys()`. |
| Frontend fails closed on empty permission list; no role-list fallback; cache cleared on logout/403 | VERIFIED | `utils/permissions.ts` `derivePermissionState` reads only `currentUser.permissions`; `App.tsx:1189` uses it; `Promise.allSettled` at `App.tsx:695`; `apiService.ts` `clearSessionCaches` removes every `omni_cache_*`, and a 403 drops the cached copy. Vitest permissions suite: 23 passed. |
| Five one-off role scripts archived with history, four others retained | VERIFIED | `archive/backend-rbac-oneoffs/` holds the five plus ARCHIVED.md; absent from `backend/`; fix_rbac.py, fix_all_rbac.py, unlock_enterprise_features.py, diagnose_rbac.py still in `backend/`. |

**Score:** 4/4 roadmap criteria verified at code and test level; the live-DB and live-UI confirmations are routed to human verification.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| ACC-01 | 75-01..05 (all declare it) | /login and /me return a server-evaluated effective set from one resolver, no empty list | SATISFIED | Truths 1 and 2 above. |
| ACC-02 | 75-01..05 (all declare it) | Drifted defaults collapsed into one source; itam_* role documents seeded | SATISFIED in code; live seeding pending restart | Truths 3 and 4 above. |

No orphaned requirements: REQUIREMENTS.md maps only ACC-01 and ACC-02 to Phase 75, and both are claimed by every plan.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 75 backend tests | `backend/venv/bin/python -m pytest tests/test_login_me_permissions.py test_effective_permissions.py test_rbac_defaults.py test_role_seeding.py test_roles_endpoint.py test_role_assignment_ceiling.py test_rbac.py -q` | 348 passed | PASS |
| Frontend permissions suite | `npx vitest run src/__tests__/permissions.test.ts` | 23 passed | PASS |
| Resolver output per role (own script, empty role store) | `effective_permissions` for ITAM, admin, viewer, super-admin, empty and unknown roles | 8 / 5 / 4 / 127 / 8 / 1 / 0 / 0, matches plan | PASS |
| Full suites (orchestrator regression gate, not re-run) | backend 3276 passed / 47 skipped / 0 failed; vitest 209 passed | Reported by caller | Accepted as stated |

### Anti-Patterns Found

Debt-marker scan (TBD/FIXME/XXX) over the phase's core files: none. No stubs or hardcoded empty data in the resolver, role list or permission derivation. `backend/tests/test_find_role_doc.py` has an uncommitted import-splitting change unrelated to the phase.

### Open review items (not blockers for the phase goal)

| Item | Severity | Note |
|------|----------|------|
| WR-04 (partial) | Warning | Mappings written before the ceiling existed can still yield a tenant-level role at apply time; only the super-admin tier is re-checked. Needs a mapping-schema change; deferred. The phase goal and the D-22 super-admin truth are met. |
| WR-06 (partial) | Warning | Spelling matching fixed; whether `isEditable` should affect shared documents is a product decision. |
| IN-01..IN-05 | Info | Dead `Permission` enum / `require_role`, import ordering, `session_permissions` swallowing errors by design (D-19-style degrade), archived `reset_db_fresh.py` still runnable, `can_assign_role` has no production caller. |

### Human Verification Required

1. **Live role-document seeding.** After the user restarts the backend, confirm 11 shared role documents exist in `omni_platform` and tenant-scoped same-named documents are untouched. Why human: seeding runs only at startup; no restart or live DB write was permitted.
2. **ITAM-role login through the deployed UI.** After restart and UI redeploy, log in as each ITAM role and compare /login, /me, sidebar and Settings > Roles. Why human: needs the live deployment and real tenant `enabledFeatures`.
3. **Policy sign-off on the review fixes** flagged "requires human verification" (CR-01, WR-01, and the partial WR-04/WR-06 deferrals).

### Gaps Summary

No gaps. Every roadmap success criterion and plan must-have checked against the current code resolves to VERIFIED. The status is `human_needed` solely because of live-only confirmations that the caller instructed must not be passed on the basis of repository state.

---

_Verified: 2026-10-12_
_Verifier: Claude (gsd-verifier)_
