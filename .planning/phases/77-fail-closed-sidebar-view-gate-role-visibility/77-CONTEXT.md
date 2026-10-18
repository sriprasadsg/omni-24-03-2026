# Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility - Context

**Gathered:** 2026-10-18
**Status:** Ready for planning

<domain>
## Phase Boundary

A user sees, can reach, and is told about exactly the catalogues their role allows, and a role-permission edit takes effect without a full re-login (ACC-06..ACC-09). Concretely: the sidebar and every navigation path fail closed against the Phase 76 manifest, a render-time gate shows a no-access state instead of a forbidden screen's content, a user with no permitted screen gets a working landing and sign-out, admins get a "what can this role see" view, real tenant custom roles make role edits possible, and permission changes reach an open session on focus or on a 403. Regression tests cover per-role and per-tenant visibility and guards, including super-admin and `platform-admin`.

Phase 76 (backend route enforcement) is committed but not deployed; this phase is planned to ship with or before it, so restricted roles do not meet raw 403s.

</domain>

<decisions>
## Implementation Decisions

### Role editing (custom tenant roles)
- **D-01:** Roles become editable for real through **tenant custom roles**: an admin creates, edits and deletes their own tenant's custom role documents (`db.roles` with the tenant's `tenantId`, which `GET /api/roles` already lists per 75 D-15) and assigns them to users. The 13 built-in roles stay fixed by the code table and the startup mirror (75 D-12); they are not editable and not narrowed per tenant. The fake in-memory `saveRole`/`deleteRole` in `services/apiService.ts` are replaced by the real API. — **Reversibility:** costly — once users hold custom roles, removing the feature means reassigning every such user and dropping tenant role documents.
- **D-02:** Who may write roles: anyone holding `manage:rbac` in the tenant (tenant admins by default), plus Super Admin for any tenant. **Ceiling:** a custom role may contain only permissions the editor holds, with the D-11 closure applied to the editor's set (the 75 D-20 rule, reused). `rbac_defaults.PLATFORM_ONLY_PERMISSIONS` are never grantable to a tenant role, and `manage:tenants` stays super-admin only (75 D-06).
- **D-03:** Deleting a custom role that users still hold is **refused** with the list of users who hold it; the admin reassigns them first. Nobody silently loses or changes access.
- **D-04:** Custom roles are assignable everywhere a built-in role is: user create/update (`backend/user_endpoints.py`, today `_VALID_ROLE_KEYS = builtin_role_keys()`) and the SAML/LDAP group→role mappings (`backend/saml_mapping.py`, `backend/ldap_service.py`, which today accept built-in keys only), all behind the 75 D-20 ceiling and the 75 D-22 super-admin-tier refusal. A custom role is resolved within its own tenant only; one tenant's role edit never changes another tenant's users (roadmap SC5).
- **Constraint (from scouting):** a custom role name must not collide with a built-in role after `RBACService._normalize_role`, since `GET /api/roles` already skips tenant documents whose normalized name is built-in.

### Blocked screens and zero access
- **D-05:** A user who reaches a screen their role cannot see (URL hash, deep link, bookmark, in-app button, or the initial `'dashboard'` default) gets an **in-place no-access panel** in the content area: "You don't have access to <screen>", the permission it needs, and a "Go to <landing>" button. The sidebar stays; nothing of the forbidden screen renders. This replaces the current `console.warn` in `App.tsx` `handleSetCurrentView` and covers views with no manifest permission (fail closed; 76 IN-04).
- **D-06:** **Landing view:** the dashboard if the role holds `view:dashboard`, otherwise the first allowed sidebar item in menu order (ITAM roles land in the ITAM console, 75 D-09). The same rule drives the D-05 "Go to" button and the post-login view.
- **D-07:** A user with **no permitted screen** gets a **full-page no-access screen** with no sidebar: the signed-in email, role and tenant, "Your role has no screens yet, ask your administrator", a **Sign out** button, and a **Retry** that re-reads permissions (75 D-19 users land here).
- **D-08:** On an allowed screen, widgets, tabs and panels backed by a catalogue the role cannot read are **hidden and their fetches skipped**, extending the spec C6 `ifOn` skip in `App.tsx` `loadAllData` from feature switches to role permissions: no 403s, error toasts or "Backend offline" banners for restricted roles (covers the Phase 76 startup fetches, e.g. integrations and infrastructure, that 403 for non-admins).
- **Derived (ACC-08):** a 403 triggers the same permission re-read as window focus (`refreshPermissions`, which already runs on `visibilitychange` and every 30 s since spec C6). If the open screen is no longer allowed after a refresh, it switches to the D-05 panel; if nothing is allowed, to the D-07 screen.

### "What can this role see" view (ACC-07)
- **D-09:** Lives in **Settings > Roles** (`components/SettingsRolesTab.tsx`): each role row gets a "What it can see" panel next to the D-01 custom-role editor. **Layout:** per role, screens grouped by sidebar group, each marked view / manage / switched off.
- **D-10:** "Can see" means **role effective permissions narrowed by the tenant's feature switches** (spec C6), the same check `rbac_utils.verify_permission` applies, so it matches what the backend enforces (roadmap SC3). Screens the role grants but the tenant switched off are listed separately as "switched off for this tenant". Open to anyone who can list roles (`manage:users` or `manage:rbac`, 75 D-16) for their own tenant's built-in and custom roles; Super Admin views any tenant through the existing tenant switcher; platform roles are shown to Super Admin only.

### manage:X unlocks the menu item
- **D-11:** `/login` and `/me` (and every session-mint response, 75 D-24) deliver the effective set with the closure **`manage:X ⇒ view:X` and `request:X`** applied, so the menu matches the backend guard (76 D-03/D-07) for every role, custom roles included. Built-in effect: `itam_admin` gains Assets (`assetManagement`) and Certificates. One closure rule is used everywhere: assignment ceiling (75 D-20), role-editor ceiling (D-02), `/me` delivery and the D-09/D-10 view. Phase 75 delivery tests are updated accordingly.
- **Constraint (from scouting):** backend checks of `request:X` must accept the closure too, or the menu would show a request action the backend refuses: `backend/itam_asset_request_endpoints.py:21` checks `request:assets` strictly today.

### Fail-closed sidebar (ACC-06, from the requirement)
- The sidebar's fail-open fallback is removed: `components/Sidebar.tsx:181` `userContext?.hasPermission || (() => true)` becomes deny when the context or permissions are missing or unknown.

### Post-research amendments (2026-10-18, user-approved after 77-RESEARCH.md)
- **D-12 (refines D-06):** landing preference is `['dashboard', 'itam']`, then the first allowed sidebar item in menu order. Menu order alone would land all three ITAM roles on Assets (`assetManagement` precedes `itam` in `shared/catalogue-access.json`); the ITAM roles land in the ITAM console as 75 D-09 intended. The manifest order is not changed.
- **D-13:** a custom role's **name is fixed** after creation; description and permissions stay editable. Renaming means creating a new role and reassigning (users store the role by name). The server refuses a changed name and the editor disables the name field when editing.
- **D-14 (MFA):** MFA becomes **permission-based**: any user whose role's effective set holds an admin-tier permission requires MFA, the same as the built-in admin roles. This replaces the name-keyed `_MFA_REQUIRED_ROLE_KEYS` in `backend/authentication_service.py` (~line 72) as the source of truth, so a custom role cannot be a way around MFA; the built-in admin roles keep requiring it. The admin-tier set is defined once in `backend/rbac_defaults.py`. — **Reversibility:** costly — users who never enrolled MFA but hold an admin-tier custom role are prompted to enroll on next sign-in.
- **D-15 (extends D-03):** deleting a custom role is also refused while the tenant's SAML/LDAP group mappings name it; the refusal lists those mappings next to the users who hold it.
- **D-16 (Claude's call on research Open Question 5):** the server emits a `screen-off:<view>` marker for every nav screen the role grants but the tenant switched off (research Pattern 9), so the UI-SPEC `switched_off` and `role` copy variants can be told apart.
- **D-17 (research Open Questions 6-8):** a Super Admin with no tenant selected sees the built-in roles unnarrowed, with the basis line saying no tenant is selected; custom roles need a selected tenant. Custom roles may contain only permission strings known to the role table, manifest or switch catalogue. D-08's widget hiding covers the app shell (startup fetches, `NotificationCenter`, dashboard widgets that read gated data, a reusable `canReadView`); ITAM console tab gating stays deferred as ACC-F1.
- **D-18 (research constraints):**
  - Reserve custom-role names whose normalized key is a built-in key, equals `AGENT_ROLE` (`agent`), or is empty.
  - Add a `builtIn` flag to the role response instead of reusing `isEditable` (five built-ins are seeded `isEditable: true`).
  - When a Super Admin moves a user to another tenant, validate the user's role against the destination tenant.
  - Give Sign out a fetch timeout so it never waits on Retry or a hung backend.

### Claude's Discretion
- Role-write API shape (routes, payload, validation messages), audit-ledger entries for role create/edit/delete, and how the role editor shows implied permissions when `manage:X` is ticked.
- Where the closure is computed (resolver vs delivery layer), as long as `/me` delivery and backend enforcement cannot diverge.
- Unifying the frontend's scattered super-admin name checks onto `utils/permissions.ts` `isSuperAdminRoleName` / `isPlatformRoleName` (75 D-05 left this to Phase 77).
- 403-refresh debouncing, wording and styling of the D-05/D-07 screens (subject to the UI-SPEC from `/gsd-ui-phase 77`).
- How the D-09/D-10 data is computed (backend endpoint from the resolver and manifest is preferred over client-side recomputation, since SC3 requires matching backend enforcement).
- Test structure for SC5 (per role, per tenant, super-admin and `platform-admin`, cross-tenant role-edit isolation).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone and requirements
- `.planning/ROADMAP.md` § "Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility" — goal and success criteria 1-5
- `.planning/REQUIREMENTS.md` — ACC-06, ACC-07, ACC-08, ACC-09; Out of Scope table (no new permission model)

### Prior phase decisions
- `.planning/phases/75-permission-resolver-single-source-of-truth/75-CONTEXT.md` — resolver, single table, D-05 super-admin variants, D-09 ITAM landing, D-12 startup mirror, D-15/D-16 role list, D-17 no fallback, D-19 empty-permission login, D-20 ceiling + closure, D-22 SAML/LDAP, D-24 session-mint responses, D-26 cached role list; deferred note on persisted role writes
- `.planning/phases/76-catalogue-manifest-backend-route-enforcement/76-CONTEXT.md` — D-03 manage⇒view read guard, D-07 closure via /me deferred here, D-12 API-key self-service
- `.planning/phases/76-catalogue-manifest-backend-route-enforcement/76-11-SUMMARY.md` § "Needs a human decision" — open manifest permission policy items (see Deferred)
- `.planning/phases/76-catalogue-manifest-backend-route-enforcement/76-VERIFICATION.md` and `76-UAT.md` — post-deploy checks that this phase's UI must make pass gracefully (viewer/itam/analyst refusals without blank pages)

### Manifest and access data
- `shared/catalogue-access.json` — the single catalogue manifest (permission per view, routes per catalogue)
- `shared/catalogue-gaps.json` — gap ledger (groups not yet guarded; their screens still follow the manifest permission in the UI)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `utils/catalogueAccess.ts`: `CATALOGUES`, `CATALOGUE_GROUPS`, `NAV_GROUPS`, `viewPermission(view)`, `catalogueFor(view)`, `viewForHash(hash)`, `findNavDrift` — the manifest reader the sidebar, gate and role view should all use.
- `utils/permissions.ts`: `derivePermissionState`, `screenAllowed`, `switchedOnFor`, `isSuperAdminRoleName`, `isPlatformRoleName`.
- `App.tsx` `refreshPermissions` (~line 814) + `visibilitychange`/30 s refresh (~line 824); `services/apiService.ts` `fetchCurrentPermissions` (~line 740) — ACC-08 focus refresh already exists; add the 403 trigger.
- `App.tsx` `loadAllData` `ifOn(view, fetch)` (~line 497) — the fetch-skip pattern D-08 extends.
- `App.tsx` `currentScreenOff` redirect (~line 1020) — spec C6 switched-off screen handling to fold into the D-05/D-06 gate.
- `backend/role_endpoints.py` `list_roles` — built-ins + own-tenant role documents with effective permissions; the natural home of the role-write API and the D-10 data.
- `backend/role_assignment.py` `assert_can_assign_role` — 75 D-20 ceiling helper to reuse for the D-02 role-editor ceiling.
- `backend/rbac_service.py` `effective_permissions` (line 75), `_normalize_role`; `backend/tenant_features.py` `enabled_features`; `backend/rbac_defaults.py` `ROLE_DEFAULTS`, `PLATFORM_ONLY_PERMISSIONS`, `builtin_role_keys()`.
- `components/RoleEditorModal.tsx` (permission groups, feature labels) and `components/SettingsRolesTab.tsx` (role list, "New Custom Role") — existing UI to wire to the real API.

### Established Patterns
- Permissions come only from the server-delivered `currentUser.permissions` (75 D-17), already narrowed by tenant feature switches (spec C6); no role-list fallback.
- Platform roles (Super Admin, Platform Support, Platform Billing) skip tenant feature switches in the UI (`isPlatformRoleName`).
- Backend guards are `catalogue_guard` tags checked by the deny-by-default parity gate (Phase 76); new routes need a guard or a ledger entry.
- Tests: backend pytest with real-app probes (`backend/tests/_route_walk.py` `probe_real_app`), frontend vitest under `src/__tests__/` (catalogueAccess, SidebarAuditFixes, SidebarTenantSwitches).

### Integration Points
- `components/Sidebar.tsx` filtering (~lines 181-254) — fail-closed source of the menu.
- `App.tsx` `handleSetCurrentView` (~line 1165), hash handler (~line 426), initial `currentView` `'dashboard'` (line 280) — render-time gate and landing.
- `backend/user_endpoints.py` `_VALID_ROLE_KEYS`, `backend/saml_mapping.py:165`, `backend/ldap_service.py:591` — role validation to widen to own-tenant custom roles.
- `backend/itam_asset_request_endpoints.py:21` — strict `request:assets` check to align with D-11.

</code_context>

<specifics>
## Specific Ideas

- `itam_admin` must see Assets and Certificates after D-11 (it holds `manage:assets` but not `view:assets`).
- An `itam_viewer` without `view:dashboard` still lands somewhere valid (roadmap SC2): the ITAM console under D-06.
- The no-access screen's Retry and the 403 refresh let an admin's role fix show up without the user signing out.

</specifics>

<deferred>
## Deferred Ideas

- **Narrowing built-in roles per tenant** (a tenant override that removes permissions from a built-in role): not chosen; the resolver unions tenant documents with defaults, so it needs a resolver change. Future phase if wanted.
- **Roles × screens comparison matrix**: not chosen; the per-role panel (D-09) ships first.
- **Unique index on custom role names (optional migration 023, research Pitfall 15):** deferred. It would run on the user's next backend restart; this phase relies on an application-level name check with a read-after-write check for this admin-only action.
- **Phase 76-11 "Needs a human decision" manifest items** (retentionPolicy/PAM `manage:settings`, platform_support vs secrets/integrations reads, fleetGeoMap/Observability `manage:agents`, hadr `view:backups`, write lists with view strings, detection rules/FIM for analysts, tenant/bundle management reads, knowledge base read): not discussed here. The D-10 view will show whatever the manifest says, so they stay open policy questions for the user.

### Reviewed Todos (not folded)
- "Fix stale capability-count assertions in integration.rs" (Rust agent tests) — matched on the keyword "tests" only; unrelated to the sidebar or view gate.

</deferred>

---

*Phase: 77-fail-closed-sidebar-view-gate-role-visibility*
*Context gathered: 2026-10-18*
