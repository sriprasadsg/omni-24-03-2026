---
phase: "77"
slug: "fail-closed-sidebar-view-gate-role-visibility"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-19"
---

# Phase 77 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| server-delivered permissions -> sidebar / render-time gate | The client presents only what the server granted | Permission list (access policy) |
| URL hash / deep link / in-app callers -> rendered view | Untrusted navigation input picks what renders | View selection (UI only) |
| role table / role documents -> delivered permission list | What the server tells the UI the user may see; verify_permission answers from the same resolver | Access policy |
| server -> client permission list (refresh) | The client must reflect, never widen, what the server delivers | Permission list |
| admin browser / editor UI -> /api/roles writes | Untrusted role name, description and permission list; the server enforces the ceiling | Role contents |
| tenant A admin -> role documents of tenant B or the shared sentinels | Must never cross | Tenant role data |
| Super Admin -> any tenant (role writes, tenantId query, user tenant move) | Explicit, validated target only; a role must exist in the destination | Role and user records |
| admin -> user role field / directory mapping | Untrusted role names name what access a user gets | User access |
| session token -> admin-tier routes | Admin powers require a second factor | Session / MFA state |
| role lister -> another role's visibility; tenant admin -> platform role definitions | Reveals a role's reach; tenant-scoped, platform roles Super Admin only | Role reach |
| refusal payload -> admin UI | Holder names and emails of the admin's own tenant | User identity (PII, same tenant) |
| server payload -> rendered role names and descriptions | Admin-supplied strings shown to other admins | Untrusted text |
| client fetch plan -> guarded API | The client asks only for what the role can read; the server still enforces | Catalogue data |
| user -> sign-out | Leaving the session must not depend on backend health | Session tokens |
| test run -> live system | Tests must stay hermetic | Production data |

---

## Threat Register

Register authored at plan time across 77-01..77-13 (`<threat_model>` blocks). Verified 2026-10-19 at ASVS L1 (grep depth): each mitigation located in the implementation and, where named, its test. Supporting runs the same day: vitest 413 passed; Phase 77 backend set 584 passed; route parity 50 passed.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-77-01 | Elevation of Privilege | rbac_defaults.deliverable_closure | high | mitigate | Closure only adds view:X/request:X for manage:X, intersected with KNOWN_PERMISSIONS; tests prove no control: string, no view-to-manage, nothing unknown (PROH-77-01) — evidence: `rbac_defaults.deliverable_closure` intersects with `permission_vocabulary.KNOWN_PERMISSIONS`; `test_closure_delivery.py` (no control:, nothing unknown) | closed |
| T-77-02 | Information Disclosure | closure vs tenant switches | high | mitigate | Closure runs before tenant_features narrowing in both granted_permissions and _fallback_permissions; test shows itam_admin loses view:assets/manage:assets when switched off and gets screen-off markers — evidence: `rbac_service.py:126` closure before tenant narrowing; `test_closure_delivery.py` D-16 marker tests | closed |
| T-77-SC | Tampering | npm/pip installs | low | accept | No packages are installed by this plan | closed (accepted) |
| T-77-03 | Information Disclosure | App.tsx renderView and navigation paths | medium | mitigate | Render-time ViewGate around renderView, default branch returns the unmapped panel, ChatAssistant and socket paths routed through the handler; source guards in catalogueAccess.test.ts (PROH-77-02); the backend guard (Phase 76) stays the enforcement point — evidence: `App.tsx` `ViewGate` + `evaluateViewAccess`; `catalogueAccess.test.ts` (ViewGate wraps renderView, no Dashboard default) | closed |
| T-77-05 | Elevation of Privilege | role contents | high | mitigate | assert_can_edit_contents: ceiling_allows(caller effective, old XOR new), 503 on store error; banned set for every editor (PROH-77-03) — evidence: `role_contents.assert_can_edit_contents` with `ceiling_allows(caller, old ^ new)`, 503 on store error | closed |
| T-77-06 | Tampering / Information Disclosure | role id IDOR across tenants | high | mitigate | Every lookup filtered by the resolved tenantId on the raw handle; 404 for other tenants' ids; tested — evidence: `role_contents` reads filtered by `tenantId`; `test_role_write_api.py::test_other_tenants_builtin_and_legacy_ids_are_404` | closed |
| T-77-07 | Tampering | Super Admin write into platform-admin, all or platform | high | mitigate | resolve_target_tenant refuses the three sentinels and unknown tenants — evidence: `role_contents.resolve_target_tenant` refuses `SENTINEL_TENANTS` and unknown tenants | closed |
| T-77-08 | Spoofing / Elevation | role names agent, built-in spellings | high | mitigate | validate_role_name reserves normalize_role keys in builtin_role_keys(), 'agent' and empty; tested for every spelling — evidence: `role_contents.validate_role_name` refuses `AGENT_ROLE`, built-in keys in any spelling, empty | closed |
| T-77-09 | Tampering | mass assignment (tenantId, id, isEditable, *) | medium | mitigate | Pydantic extra="forbid", tenantId honoured only for Super Admin, server-generated id, banned strings — evidence: `role_endpoints.py` request models `ConfigDict(extra="forbid")` | closed |
| T-77-10 | Denial of Service | oversized payloads, many roles | low | mitigate | Name 2-64, description 500, permissions capped at the grantable vocabulary, 200 custom roles per tenant — evidence: `NAME_PATTERN` 2-64, `MAX_DESCRIPTION = 500`, `MAX_CUSTOM_ROLES_PER_TENANT = 200`, permissions capped at grantable set | closed |
| T-77-11 | Repudiation | role changes | medium | mitigate | role.created/updated/deleted via the hash-chained audit adapter with previous_state; the /api/ audit middleware also records the request — evidence: `role_endpoints.py` `_audit_role` for role.created / role.updated / role.deleted with previous_state | closed |
| T-77-12 | Tampering | delete while held | medium | mitigate | 409 role_in_use with holders and mappings (PROH-77-04); delete race accepted (a racing assignment resolves to [] per 75 D-19, never more access) — evidence: `role_endpoints.py` 409 `role_in_use` with holders and mappings | closed |
| T-77-13 | Elevation of Privilege | admin-tier custom role without MFA | high | mitigate | Permission-based check over effective_permissions in verify_token_async and the sync path; fail closed for custom names on store error or cache miss; test_custom_role_mfa.py — evidence: `rbac_defaults.requires_mfa` over effective permissions in `authentication_service.py:131`; `test_custom_role_mfa.py` | closed |
| T-77-14 | Denial of Service | fail-closed MFA lookup locking out non-admin custom-role users during a store outage | low | accept | A store outage already blocks most of the app; built-in names fall back to the table answer; documented assumption D14-WS-CACHE-MISS | closed (accepted) |
| T-77-15 | Information Disclosure | stale permissions after a role edit | medium | mitigate | Focus and 403 refresh through refreshPermissions; the backend reads the DB per request regardless (PROH-77-05) — evidence: `App.tsx` `refreshPermissions` on focus and 403 | closed |
| T-77-16 | Denial of Service | refresh storm from repeated 403s | low | mitigate | Leading-plus-trailing 15 s window (at most two refreshes per window), shared in-flight request, /api/auth/ excluded — evidence: `utils/permissionRefresh.ts` `PERMISSION_DENIED_WINDOW_MS = 15000`, `/api/auth/` and MFA excluded | closed |
| T-77-17 | Denial of Service | sign-out hanging on a dead backend | low | mitigate | 5 s AbortController on the logout request; local session cleared regardless — evidence: `services/apiService.ts` `logoutSession` AbortController, `LOGOUT_TIMEOUT_MS = 5000`, local clear regardless | closed |
| T-77-18 | Elevation of Privilege | case/spelling variants of a custom role name | high | mitigate | resolve_assignable_role canonicalises before assert_can_assign_role and storage (PROH-77-06) — evidence: `role_assignment.resolve_assignable_role` canonicalises before the ceiling | closed |
| T-77-19 | Tampering | cross-tenant custom role assignment | high | mitigate | find_custom_role reads only the target tenant; other tenants' names are 400 — evidence: `role_contents.find_custom_role` reads only the target tenant | closed |
| T-77-20 | Tampering | Super Admin tenant move stranding or escalating a user | medium | mitigate | Role re-resolved against the destination; 400 and no write when missing — evidence: `user_endpoints.py:370` re-resolves the role against the destination tenant | closed |
| T-77-21 | Elevation of Privilege | directory mapping to an over-privileged custom role | high | mitigate | Mapping writes canonicalise then run the existing ceiling and platform-role refusal — evidence: `sso_endpoints.py:378`, `ldap_endpoints.py` call `resolve_assignable_role` then the ceiling and platform-role refusal | closed |
| T-77-22 | Information Disclosure | other tenants' custom roles via role id | medium | mitigate | find_custom_role scoped to the resolved tenant; 404 across tenants; 403 for a foreign tenantId — evidence: `role_endpoints.py:220` `find_custom_role(db, tenant_id, ...)` | closed |
| T-77-23 | Information Disclosure | platform role definitions to tenant admins | low | mitigate | Platform built-ins resolvable only by a Super Admin (404 otherwise), as in list_roles — evidence: `role_endpoints.py` platform built-ins only for `is_super_admin` callers | closed |
| T-77-24 | Repudiation / Tampering of trust | visibility diverging from enforcement (misleading an admin) | medium | mitigate | Same pipeline as delivery; property test against check_catalogue_access for enforced groups (PROH-77-07) — evidence: `test_role_visibility.py:273` property test against `catalogue_guards.check_catalogue_access` | closed |
| T-77-25 | Information Disclosure | gated widgets rendering error bodies or cached data of another user | low | mitigate | Fetches skipped by canReadView, fetchIntegrations no longer stores error bodies, fetchWithCache already drops caches on 403 (75 D-26); server guards remain authoritative — evidence: `canReadView` gates in `App.tsx`, `Dashboard.tsx`, `NotificationCenter.tsx`; `fetchIntegrations` returns [] on non-ok | closed |
| T-77-26 | Tampering | stored script in role name or description | low | mitigate | React text rendering only (no dangerouslySetInnerHTML); the server restricts the name character set (77-03); canon XSS concerns are covered by /gsd-secure-phase and eslint, not minted here — evidence: No `dangerouslySetInnerHTML` in the role components; server name pattern | closed |
| T-77-27 | Information Disclosure | tenantId query from a non-Super-Admin | low | mitigate | tenantId is sent only for a Super Admin with a selected customer tenant; the server refuses any other caller's foreign tenantId (77-03, 77-07) — evidence: `RoleVisibilityPanel` sends tenantId only for a Super Admin; server 403 for a foreign tenantId | closed |
| T-77-28 | Tampering / Information Disclosure | cross-tenant role edits and reads | high | mitigate | Explicit isolation tests over the write API, /me and visibility (PROH-77-08) — evidence: `test_role_tenant_isolation.py` (A edit never changes B, cross-tenant ids 404, foreign tenantId refused) | closed |
| T-77-29 | Tampering | tests writing the live database or ledger | medium | mitigate | In-memory role_store, monkeypatched audit recorder, probe_real_app with throwaway_env(); shared/ untouched check — evidence: In-memory store + monkeypatched audit recorder in tests; `throwaway_env()` probe | closed |
| T-77-30 | Elevation of Privilege | client offering ungrantable permissions | medium | mitigate | List comes from the server catalogue; the server ceiling (77-03) refuses anything else regardless of the UI — evidence: `RoleEditorModal` lists `fetchPermissionCatalogue` result; server ceiling enforces | closed |
| T-77-31 | Tampering | implied permissions submitted silently | low | mitigate | Implied rows are rendered checked and labelled before submit; submit equals the visible checked set plus locked rows (PROH-77-09) — evidence: `utils/rolePermissions.ts` `impliedBy` / `lockedPermissions`; submit = visible checked set + locked rows | closed |
| T-77-32 | Tampering | delete racing an assignment | low | accept | Server refusal (77-03) covers the common case; a racing assignment resolves to no permissions (75 D-19), never more access | closed (accepted) |
| T-77-33 | Information Disclosure | holder emails in the refusal payload | low | accept | Shown only to manage:rbac holders of the same tenant (or the Super Admin), who already list those users | closed (accepted) |
| T-77-04 | Elevation of Privilege | Sidebar fail-open fallback | medium | mitigate | hasPermission fallback denies, bypass only for a resolved super-admin/platform user, skeleton while unknown, filter through evaluateViewAccess; SidebarFailClosed.test.tsx — evidence: `Sidebar.tsx:182` `(() => false)` fallback, `isSuperAdminRoleName`, `evaluateViewAccess`; `SidebarFailClosed.test.tsx` | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-77-01 | T-77-SC | No packages are installed by this plan | plan-time register (77 PLAN threat_model) | 2026-10-18 |
| AR-77-02 | T-77-14 | A store outage already blocks most of the app; built-in names fall back to the table answer; documented assumption D14-WS-CACHE-MISS | plan-time register (77 PLAN threat_model) | 2026-10-18 |
| AR-77-03 | T-77-32 | Server refusal (77-03) covers the common case; a racing assignment resolves to no permissions (75 D-19), never more access | plan-time register (77 PLAN threat_model) | 2026-10-18 |
| AR-77-04 | T-77-33 | Shown only to manage:rbac holders of the same tenant (or the Super Admin), who already list those users | plan-time register (77 PLAN threat_model) | 2026-10-18 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-19 | 34 | 34 | 0 | secure-phase (orchestrator, L1 grep verification; auditor skipped per short-circuit rule) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-19

## Security Audit 2026-10-19

| Metric | Count |
|---|---|
| Threats found | 34 |
| Closed | 34 |
| Open | 0 |
