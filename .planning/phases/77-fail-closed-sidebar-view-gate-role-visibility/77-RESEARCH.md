# Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility - Research

**Researched:** 2026-10-18
**Domain:** RBAC delivery and enforcement alignment (FastAPI + Mongo) plus app-shell access gating (React 19 / Vite / vitest)
**Confidence:** HIGH on code facts (every in-repo claim below was read in this session); MEDIUM on UI behaviour that needs a real browser to confirm (flagged for end-of-phase human verification)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Role editing (custom tenant roles)**
- **D-01:** Roles become editable for real through **tenant custom roles**: an admin creates, edits and deletes their own tenant's custom role documents (`db.roles` with the tenant's `tenantId`, which `GET /api/roles` already lists per 75 D-15) and assigns them to users. The 13 built-in roles stay fixed by the code table and the startup mirror (75 D-12); they are not editable and not narrowed per tenant. The fake in-memory `saveRole`/`deleteRole` in `services/apiService.ts` are replaced by the real API. — **Reversibility:** costly — once users hold custom roles, removing the feature means reassigning every such user and dropping tenant role documents.
- **D-02:** Who may write roles: anyone holding `manage:rbac` in the tenant (tenant admins by default), plus Super Admin for any tenant. **Ceiling:** a custom role may contain only permissions the editor holds, with the D-11 closure applied to the editor's set (the 75 D-20 rule, reused). `rbac_defaults.PLATFORM_ONLY_PERMISSIONS` are never grantable to a tenant role, and `manage:tenants` stays super-admin only (75 D-06).
- **D-03:** Deleting a custom role that users still hold is **refused** with the list of users who hold it; the admin reassigns them first. Nobody silently loses or changes access.
- **D-04:** Custom roles are assignable everywhere a built-in role is: user create/update (`backend/user_endpoints.py`, today `_VALID_ROLE_KEYS = builtin_role_keys()`) and the SAML/LDAP group→role mappings (`backend/saml_mapping.py`, `backend/ldap_service.py`, which today accept built-in keys only), all behind the 75 D-20 ceiling and the 75 D-22 super-admin-tier refusal. A custom role is resolved within its own tenant only; one tenant's role edit never changes another tenant's users (roadmap SC5).
- **Constraint (from scouting):** a custom role name must not collide with a built-in role after `RBACService._normalize_role`, since `GET /api/roles` already skips tenant documents whose normalized name is built-in.

**Blocked screens and zero access**
- **D-05:** A user who reaches a screen their role cannot see (URL hash, deep link, bookmark, in-app button, or the initial `'dashboard'` default) gets an **in-place no-access panel** in the content area: "You don't have access to <screen>", the permission it needs, and a "Go to <landing>" button. The sidebar stays; nothing of the forbidden screen renders. This replaces the current `console.warn` in `App.tsx` `handleSetCurrentView` and covers views with no manifest permission (fail closed; 76 IN-04).
- **D-06:** **Landing view:** the dashboard if the role holds `view:dashboard`, otherwise the first allowed sidebar item in menu order (ITAM roles land in the ITAM console, 75 D-09). The same rule drives the D-05 "Go to" button and the post-login view.
- **D-07:** A user with **no permitted screen** gets a **full-page no-access screen** with no sidebar: the signed-in email, role and tenant, "Your role has no screens yet, ask your administrator", a **Sign out** button, and a **Retry** that re-reads permissions (75 D-19 users land here).
- **D-08:** On an allowed screen, widgets, tabs and panels backed by a catalogue the role cannot read are **hidden and their fetches skipped**, extending the spec C6 `ifOn` skip in `App.tsx` `loadAllData` from feature switches to role permissions: no 403s, error toasts or "Backend offline" banners for restricted roles (covers the Phase 76 startup fetches, e.g. integrations and infrastructure, that 403 for non-admins).
- **Derived (ACC-08):** a 403 triggers the same permission re-read as window focus (`refreshPermissions`, which already runs on `visibilitychange` and every 30 s since spec C6). If the open screen is no longer allowed after a refresh, it switches to the D-05 panel; if nothing is allowed, to the D-07 screen.

**"What can this role see" view (ACC-07)**
- **D-09:** Lives in **Settings > Roles** (`components/SettingsRolesTab.tsx`): each role row gets a "What it can see" panel next to the D-01 custom-role editor. **Layout:** per role, screens grouped by sidebar group, each marked view / manage / switched off.
- **D-10:** "Can see" means **role effective permissions narrowed by the tenant's feature switches** (spec C6), the same check `rbac_utils.verify_permission` applies, so it matches what the backend enforces (roadmap SC3). Screens the role grants but the tenant switched off are listed separately as "switched off for this tenant". Open to anyone who can list roles (`manage:users` or `manage:rbac`, 75 D-16) for their own tenant's built-in and custom roles; Super Admin views any tenant through the existing tenant switcher; platform roles are shown to Super Admin only.

**manage:X unlocks the menu item**
- **D-11:** `/login` and `/me` (and every session-mint response, 75 D-24) deliver the effective set with the closure **`manage:X ⇒ view:X` and `request:X`** applied, so the menu matches the backend guard (76 D-03/D-07) for every role, custom roles included. Built-in effect: `itam_admin` gains Assets (`assetManagement`) and Certificates. One closure rule is used everywhere: assignment ceiling (75 D-20), role-editor ceiling (D-02), `/me` delivery and the D-09/D-10 view. Phase 75 delivery tests are updated accordingly.
- **Constraint (from scouting):** backend checks of `request:X` must accept the closure too, or the menu would show a request action the backend refuses: `backend/itam_asset_request_endpoints.py:21` checks `request:assets` strictly today.

**Fail-closed sidebar (ACC-06, from the requirement)**
- The sidebar's fail-open fallback is removed: `components/Sidebar.tsx:181` `userContext?.hasPermission || (() => true)` becomes deny when the context or permissions are missing or unknown.

### Claude's Discretion
- Role-write API shape (routes, payload, validation messages), audit-ledger entries for role create/edit/delete, and how the role editor shows implied permissions when `manage:X` is ticked.
- Where the closure is computed (resolver vs delivery layer), as long as `/me` delivery and backend enforcement cannot diverge.
- Unifying the frontend's scattered super-admin name checks onto `utils/permissions.ts` `isSuperAdminRoleName` / `isPlatformRoleName` (75 D-05 left this to Phase 77).
- 403-refresh debouncing, wording and styling of the D-05/D-07 screens (subject to the UI-SPEC from `/gsd-ui-phase 77`).
- How the D-09/D-10 data is computed (backend endpoint from the resolver and manifest is preferred over client-side recomputation, since SC3 requires matching backend enforcement).
- Test structure for SC5 (per role, per tenant, super-admin and `platform-admin`, cross-tenant role-edit isolation).

### Deferred Ideas (OUT OF SCOPE)
- **Narrowing built-in roles per tenant** (a tenant override that removes permissions from a built-in role): not chosen; the resolver unions tenant documents with defaults, so it needs a resolver change. Future phase if wanted.
- **Roles × screens comparison matrix**: not chosen; the per-role panel (D-09) ships first.
- **Phase 76-11 "Needs a human decision" manifest items** (retentionPolicy/PAM `manage:settings`, platform_support vs secrets/integrations reads, fleetGeoMap/Observability `manage:agents`, hadr `view:backups`, write lists with view strings, detection rules/FIM for analysts, tenant/bundle management reads, knowledge base read): not discussed here. The D-10 view will show whatever the manifest says, so they stay open policy questions for the user.
- Reviewed todo not folded: "Fix stale capability-count assertions in integration.rs" (Rust agent tests).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ACC-06 | Sidebar fails closed, render-time gate on the active view and every navigation path, no-access state with guaranteed landing and sign-out | Sidebar fallback at `components/Sidebar.tsx:181`; the only gate today is `handleSetCurrentView` (`App.tsx:1163-1182`), while the initial view, `setCurrentView('compliance')` (`App.tsx:893`), `ChatAssistant onNavigate` (`App.tsx:1980`) and the `default:` branch of `renderView` (`App.tsx:1845`) all bypass it. Pattern: pure `utils/viewAccess.ts` + render-time gate, see Architecture Patterns 6 and 7. |
| ACC-07 | Admin "what can this role see" view matching backend enforcement | New `GET /api/roles/{role_id}/visibility` computed from `rbac_service` resolver + `tenant_features` + manifest (Pattern 5); proven equal to `session_permissions` and to `check_catalogue_access` by a backend property test. |
| ACC-08 | Permissions refresh on 403 and on window focus | Focus/30 s refresh already exists (`App.tsx:814-838`); add a debounced `omni:permission-denied` event from `authFetch` (Pattern 8). `/me` is read fresh from the DB on every call, so a role edit is visible on the next refresh. |
| ACC-09 | Regression tests per role and per tenant incl. super-admin / `platform-admin` | Validation Architecture: function-level matrix (fast) + small real-app probe sample (slow: 215 s for 12 existing tests) + cross-tenant role-edit isolation test over the in-memory store. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

Extracted from `./CLAUDE.md` and auto-memory; the planner must verify compliance.
- Do what has been asked, nothing more; prefer editing existing files; never create documentation files unless requested.
- Keep files under 500 lines. `App.tsx` is already ~2000 lines (pre-existing), so all new logic goes into new small modules; `Sidebar.tsx` (332 lines) and `SettingsRolesTab.tsx` (67 lines) must stay under the cap after edits, and a vitest in `catalogueAccess.test.ts` already asserts `Sidebar.tsx` stays under 500 lines.
- Never save working files or tests to the repo root; tests go under `backend/tests/` and `src/__tests__/`.
- Read a file before editing it; validate input at system boundaries; never commit secrets.
- Always run tests after code changes; `npm run build && npm test`. `.planning/config.json` sets `test_command` to `npx vitest run src/__tests__` and `build_command` to `npm run build`.
- Memory-derived operating constraints: never restart or redeploy the backend or UI (the user owns restarts, secrets and the UI publish); the live backend runs from this checkout; Phase 76 is committed but not deployed; archive, never delete; do not run `run-on-ubuntu.sh`; the working tree carries unrelated uncommitted changes, so read files as they are and stage only phase files.

## Summary

The backend half of this phase is mostly assembly of parts that already exist: `rbac_defaults.implied_closure` and `ceiling_allows` (the D-20 rule), `role_assignment.assert_can_assign_role`, `rbac_service.effective_permissions/granted_permissions`, `tenant_features.narrow/hidden_screens`, and the router-level `ROLE_MANAGEMENT_GUARD` mount that Phase 76 put on `role_endpoints.router`. Any new route added to that router automatically carries the manifest guard tag the deny-by-default parity test demands (read: `manage:users` OR `manage:rbac`; write: `manage:rbac`), so no ledger or exemption change is needed as long as the routes stay in `backend/role_endpoints.py`. The frontend half is larger: the gate, landing, zero-access screen, 403 trigger, visibility panel, real role editor and delete refusal flow, plus removing at least five navigation paths that bypass the one existing check.

Code reading surfaced eight things the CONTEXT did not anticipate and that change the plan (details in Common Pitfalls): (1) putting the D-11 closure inside `granted_permissions` makes the strict `request:assets` check at `itam_asset_request_endpoints.py:21` accept the closure with no edit to that file, and applying it before `tenant_features.narrow` is required or a switched-off screen leaks to `itam_admin`; (2) D-06's "first allowed item in menu order" lands every ITAM role on **Assets**, not the ITAM console, because `assetManagement` precedes `itam` in the manifest; (3) five built-in roles are seeded `isEditable: true` and a test pins that, so the API needs a separate `builtIn` flag; (4) a custom role named `agent` would be treated as an endpoint-agent token; (5) MFA is enforced by a hard-coded role-key set, so a custom role with `manage:rbac` would not require MFA; (6) renaming a custom role silently strands every holder because users store the role name; (7) the `default:` branch of `renderView` renders the Dashboard for any unknown view; (8) the `switched_off` vs `role` copy variants cannot be told apart from the delivered permission list for ordinary `view:X` switches.

**Primary recommendation:** Compute the D-11 closure once, inside `rbac_service.granted_permissions` (before narrowing, vocabulary-filtered), so enforcement, `/login`, `/me` and the visibility view share one function; add the role-write and visibility routes to `backend/role_endpoints.py` using the raw `db._db.roles` handle with an explicit validated `tenantId`; and build the frontend gate as a pure, tested `utils/viewAccess.ts` consumed by a render-time check in `App.tsx`, never by scattered `setCurrentView` callers.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| manage:X ⇒ view:X/request:X closure | API / Backend (`granted_permissions`) | Browser (reads delivered list only) | One function feeds `verify_permission`, `/login`, `/me` and the visibility view, so delivery and enforcement cannot diverge |
| Custom role create/edit/delete, ceiling, name rules | API / Backend | Database (`roles`, raw handle, explicit `tenantId`) | Authorization and tenant scoping must be server-side; the client editor only reflects the server's grantable list |
| "What can this role see" payload | API / Backend | Browser (renders it, never recomputes) | SC3 requires matching enforcement; markers come from the server |
| Fail-closed sidebar, render-time view gate, landing, zero-access screen | Browser / Client | API (supplies the permission list and markers) | Pure presentation of server-delivered permissions; the server remains the enforcement point |
| Permission refresh on focus / 403 | Browser (event from `authFetch`, `refreshPermissions`) | API (`GET /api/auth/me`, read fresh each call) | Client re-reads; the server needs no cache invalidation because JWTs carry no permissions |
| Reserved names, admin-tier MFA for custom roles | API / Backend | — | Role-name semantics (`agent`, platform keys) and MFA live in `authentication_service` |
| Cross-tenant isolation of role documents | Database + API | — | `_role_docs` queries only the caller's tenant plus the `all`/`platform` sentinels via the raw handle (D-23) |
| Route guard for new role routes | API / Backend (`catalogue_mounts_billing_identity.MOUNTS`) | Test (`test_catalogue_route_parity`) | Mount guard is inherited by every route on the router |

## Standard Stack

No new external packages are needed. Everything below is already in the repo. [VERIFIED: package.json:30-60, `backend/venv` importlib.metadata]

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.141.1 (venv) | role-write and visibility routes | already hosts all routers |
| Pydantic | 2.13.5 (venv) | request models (`extra="forbid"`, length caps) | `user_endpoints.py` already uses `model_dump` (v2 API) |
| Motor | 3.7.1 (venv) | raw `db._db.roles` writes | the project's isolation wrapper deliberately cannot be used for role reads on `/login` (D-23) |
| React | ^19.2.0 | gate, panels, screens | existing |
| Tailwind CSS | ^3.4.17 | styling per 77-UI-SPEC | existing, no new tokens |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 (venv) | backend tests | all backend tests; harness in `backend/tests/rbac_test_support.py` |
| vitest / @testing-library/react / jsdom | ^5.0.0 / ^16.3.0 / ^26.1.0 | frontend tests | `src/__tests__/*.test.ts(x)`, setup in `src/__tests__/setup.ts` |
| lucide-react | ^1.16.0 declared (UI-SPEC says 1.28.0) | icons the local `components/icons.tsx` lacks | local icon set first, per UI-SPEC |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Closure in `granted_permissions` (recommended) | Closure only in `session_permissions` (delivery) | Delivery-only leaves `request:assets` strict (itam_admin sees a request action the backend refuses) and, if applied after `narrow`, misses `screen-off:` markers for closure-granted screens. Rejected. |
| Server-side visibility endpoint (recommended) | Client recompute from role permissions | SC3 forbids it; the client has no feature-switch or closure source of truth |
| Custom-role write via wrapper `db.roles` | Raw handle with explicit `tenantId` (recommended) | Wrapper rewrites filters from a ContextVar and is unscoped for the platform context (`database.py` `_inject_tenant_id` returns the filter untouched when tenant is `"platform-admin"`), so a Super Admin write could escape tenant scoping |

**Installation:** none.

**Version verification:** versions read from `package.json` (declared ranges) and the backend venv (`importlib.metadata`) in this session. No registry lookups were needed because no package is added.

## Package Legitimacy Audit

No external packages are installed or added by this phase, so the Package Legitimacy Gate is not applicable.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 sign-in (/login, MFA verify, signup) ─┐
 session restore (/auth/me) ───────────┤  session_permissions(db, role, tenant)
 refresh (focus/30s/403) ──────────────┘          │
                                                  ▼
        effective_permissions (defaults ∪ role docs; own tenant, "all", "platform")
                                                  │  + deliverable closure (NEW, vocabulary-filtered)
                                                  ▼
                tenant_features.narrow + hidden_screens  (screen-off:<view> markers)
                          │                                      │
                          ▼                                      ▼
             currentUser.permissions (client)          verify_permission / has_permission
                          │                            (backend enforcement, same function)
   ┌──────────────────────┼──────────────────────────────────────────┐
   ▼                      ▼                                          ▼
 Sidebar (deny if      utils/viewAccess.ts (pure)             loadAllData / widgets:
 unknown)              evaluateViewAccess / landingView        canReadView() skips fetches
   │                      │
   │            ┌─────────┴───────────┐
   │            ▼                     ▼
   │     no screen at all?      requested view denied?
   │            │                     │
   │   ZeroAccessScreen        NoAccessPanel (in <main>)  ── "Go to <landing>" ──► replace hash
   │   (Retry → /me, Sign out)  (reason: role | switched_off | unmapped)
   ▼
 allowed view renders
                          authFetch: 403 (not /auth/, not MFA) ──► 'omni:permission-denied' (debounced) ──► refreshPermissions()

 Settings > Roles:  SettingsRolesTab ──► GET /api/roles, POST/PUT/DELETE /api/roles[/id]
                    "What it can see" ──► GET /api/roles/{id}/visibility
                    RoleEditorModal   ──► GET /api/roles/permission-catalogue (grantable set)
 All of the above routes: role_endpoints.router ► ROLE_MANAGEMENT_GUARD (mount) ► in-route manage:rbac / list-access dep
                          write path: raw db._db.roles, explicit tenantId, ceiling = ceiling_allows(editor_perms, delta)
```

### Recommended Project Structure
```
backend/
├── role_endpoints.py        # EDIT: add POST/PUT/DELETE, visibility, permission-catalogue; keep < 500 lines
├── role_contents.py         # NEW: name rules, reserved names, permission validation, content ceiling (pure + async helper)
├── role_visibility.py       # NEW: pure compute(perms, enabled_features, manifest) -> payload
├── permission_vocabulary.py # NEW: known_permissions() from ROLE_DEFAULTS + manifest + switch catalogue (data, no literals)
├── rbac_service.py          # EDIT: granted_permissions/_fallback_permissions apply deliverable closure before narrow
├── role_assignment.py       # EDIT: resolve_assignable_role(); reuse ceiling_allows for contents
├── user_endpoints.py        # EDIT: replace _VALID_ROLE_KEYS check with resolve_assignable_role
├── ldap_service.py, saml_mapping.py  # EDIT: upsert_mapping accepts own-tenant custom roles
└── tests/                   # NEW test modules listed under Validation Architecture
utils/
├── viewAccess.ts            # NEW: canReadView, evaluateViewAccess, landingView, hasAnyScreen
└── permissions.ts           # EDIT: super-admin helpers only; no new rules
components/
├── NoAccessPanel.tsx  ZeroAccessScreen.tsx  RoleVisibilityPanel.tsx  RoleDeleteRefusalModal.tsx   # NEW
└── Sidebar.tsx  SettingsRolesTab.tsx  RoleEditorModal.tsx  NotificationCenter.tsx                  # EDIT
```

### Pattern 1: One closure, applied in the resolver before narrowing (D-11)
**What:** Add `rbac_defaults.deliverable_closure(perms, vocabulary)` (pure: `implied_closure` filtered to known permission strings) and call it in `rbac_service.granted_permissions` and `_fallback_permissions` between the role lookup and `tenant_features.narrow`. `effective_permissions` stays un-closed (it is the role's definition: the ceiling helper and the role list apply their own closure).
**Why here:** `verify_permission` (the fast path returns early only when the permission is a table default; otherwise it calls `granted_permissions`, `backend/rbac_utils.py:121-128`) and `/login`/`/me` (`session_permissions` → `granted_permissions`, `backend/rbac_service.py:139-155`) then agree by construction, and `request:assets` at `itam_asset_request_endpoints.py:21` passes for `itam_admin` with no edit.
**Why before `narrow`:** `hidden_screens(narrowed, enabled)` only emits `screen-off:<view>` when the permission is held (`tenant_features.py:145-151`, `needs in held`), so a closure applied afterwards would leave `itam_admin` with Assets visible while `ScreenSwitchMiddleware` returns 403.
**Why filter:** unfiltered, the closure adds 55 meaningless `request:*` strings to a tenant admin's `/me` (measured), 8 to `itam_admin`; filtered it adds exactly `request:assets`, `view:assets`, `view:licenses` for `itam_admin` and nothing for `tenant_admin` (measured with `python3 -I` over `rbac_defaults`, manifest and switch catalogue). [VERIFIED: measured this session]
```python
# Proposed (names verified: rbac_defaults.implied_closure at rbac_defaults.py:284-297, tenant_features.narrow at :127-131)
async def granted_permissions(db, role, tenant_id):
    perms = await effective_permissions(db, role, tenant_id)
    if "*" in perms or not tenant_features.applies_to(role):
        return perms
    perms = rbac_defaults.deliverable_closure(perms, permission_vocabulary.known_permissions())
    enabled = await tenant_features.enabled_features(tenant_id, lambda: db)
    narrowed = tenant_features.narrow(perms, enabled)
    return narrowed + tenant_features.hidden_screens(narrowed, enabled)
```
Note: platform roles return before the closure (they are never narrowed and hold explicit sets).

### Pattern 2: Role-write tenant resolution and storage
- Target tenant: non-super callers use `current_user.tenant_id`; a Super Admin must pass an explicit `tenantId` (query for GET/DELETE, body or query for POST/PUT), validated against `db.tenants` like `user_endpoints._tenant_exists`. Refuse (400) when the target is `rbac_defaults.PLATFORM_TENANT_ID` (`"platform-admin"`), `"all"` or `"platform"`, for the same reason `assert_role_fits_tenant` keeps tenant roles out of the platform tenant. Do not rely on the `X-Tenant-ID` override or `get_tenant_id()` (the override exists in `tenant_middleware.py` but the existing user routes treat an explicit param as the source of truth).
- Writes go through `db._db.roles` with `{"tenantId": target}` in every filter and in the inserted document. Never accept `tenantId`, `id`, `isEditable` or `permissions: ["*"]` from the body (`ConfigDict(extra="forbid")`).
- Document shape (superset of what `list_roles` reads, `role_endpoints.py:75-82`): `{id: "role-<uuid4>", name, nameKey: normalize_role(name), description, permissions: sorted unique, isEditable: True, tenantId, createdBy, createdAt, updatedBy, updatedAt}`. Legacy tenant documents have no `nameKey`; compare `normalize_role(doc["name"])` in Python for uniqueness, do not rely on the field.
- `effective_permissions` already drops `*`, `SUPER_ADMIN_ONLY_PERMISSIONS` and (for non-platform roles) `PLATFORM_ONLY_PERMISSIONS` found in documents (`rbac_service.py:100-105`); validate on write as well so the stored document matches what is delivered.

### Pattern 3: Content ceiling reuses the 75 D-20 helper
```python
# Proposed. ceiling_allows(caller_perms, target_perms) is rbac_defaults.py:300-310.
delta = set(old_perms) ^ set(new_perms)          # added or removed
if not is_super_admin(caller.role):
    caller_perms = await effective_permissions(db, caller.role, caller.tenant_id)
    if not rbac_defaults.ceiling_allows(caller_perms, delta):
        raise HTTPException(403, "You can only grant permissions you hold yourself")
```
Symmetric difference matches the UI-SPEC rule that permissions the editor cannot touch render checked and locked: an editor may neither add nor remove what they do not hold, and an unchanged inherited permission never blocks an edit. A role-store error must fail closed (503) like `assert_can_assign_role`.

### Pattern 4: Delete refusal payload
`DELETE /api/roles/{role_id}` returns `409` with `detail = {"code": "role_in_use", "holderCount": N, "holders": [{"name","email"} x <=50], "mappings": [...]}` when any user of the tenant still holds the role (match `normalize_role(user.role) == doc.nameKey` in Python over the tenant's users, projection `{role, email, full_name}`; a case-sensitive Mongo equality would miss legacy spellings). The UI-SPEC copy needs only counts, name and email.

### Pattern 5: Visibility payload (pure function, one source)
Inputs: the role's effective permissions, the tenant's `enabledFeatures`, the manifest (already loaded in `tenant_features._MANIFEST`; expose a getter rather than re-reading the file). Steps: `pre = deliverable_closure(effective)`; `narrowed = tenant_features.narrow(pre, enabled)`; `markers = tenant_features.hidden_screens(narrowed, enabled)` (plus the Pattern 9 marker if adopted). For each `nav:true` entry in manifest order: `granted = permission in pre`; `visible = permission in narrowed and f"screen-off:{view}" not in markers`; access = `"switched_off"` if `granted and not visible`; else `"manage"` if the permission starts with `manage:` or the role holds the `manage:` twin of a `view:` permission, else `"view"`. Platform roles (`not tenant_features.applies_to(role)`) skip narrowing; `["*"]` marks every screen manage. Return groups in `CATALOGUE_GROUPS` order with `total` per group so the client never counts.
Scope note for the planner: only 3 of the 8 groups are `enforce: true` (`infra`, `security`, `mgmt`: `shared/catalogue-access.json` lines 6, 7 and 11); for the other five the backend does not yet refuse at route level (ledgered, ACC-F2), so "matches what the backend enforces" is literal only for the enforced groups; document that in the panel's help text or the plan. Bundle-mode hiding and plan-tier locks in `Sidebar.tsx:245-247` are UI-only and are not part of D-10.

### Pattern 6: Frontend access evaluation is a pure module
```ts
// Proposed utils/viewAccess.ts. catalogueFor/viewPermission/NAV_GROUPS exist in utils/catalogueAccess.ts;
// screenAllowed/isSuperAdminRoleName/isPlatformRoleName exist in utils/permissions.ts.
export type Denial = { reason: 'role' | 'switched_off' | 'unmapped'; permission?: string; label: string };
export function evaluateViewAccess(view: string, user: User, has: (p: Permission) => boolean): { allowed: true } | { allowed: false } & Denial
export function canReadView(view: AppView, user, has): boolean       // read list + twin; used by loadAllData ifOn and widgets
export function landingView(user, has): AppView | null                // null => zero-access screen
export function hasAnyScreen(user, has): boolean
```
Rules: unknown view (no manifest entry) is denied for everyone, super admin included (there is nothing to render, and `default:` must stop rendering the Dashboard); a resolved super admin or delivered `*` is allowed everywhere else; platform roles skip `screenAllowed` (as `App.tsx:1020` does); everyone else needs `has(entry.permission)` and `screenAllowed(view, has)`. No client-side closure: the server already delivered it.

### Pattern 7: Render-time gate, initial view, landing
- Gate inside `renderView()` (derived from `currentView` + permissions), not in `handleSetCurrentView`. `handleSetCurrentView` then always sets the view (denied views show the panel, D-05) and replaces the `console.warn` branch (`App.tsx:1178-1180`).
- Remove the `currentScreenOff` redirect effect (`App.tsx:1020-1026`) and its `return null` (`App.tsx:1594`); the gate subsumes it.
- Initial view: when the session user first becomes known, use the hash view if present (denied hash shows the panel, not a redirect), else `landingView(...)`. Until resolved render `SkeletonDashboard` (C09), so an allowed user never sees a flash. `handleLogin` (`App.tsx:620`) and `registerTenant` (`App.tsx:1149`) call the same function instead of `setCurrentView('dashboard')`.
- Replace `ChatAssistant onNavigate={(view) => setCurrentView(view as any)}` (`App.tsx:1980`) with `handleSetCurrentView`; the socket-driven `setCurrentView('compliance')` (`App.tsx:893`) is covered by the render gate but should also use the handler.
- Zero-access early return goes after all hooks, next to the existing `if (!currentUser)` return (`App.tsx:1583`), before the main JSX, so `ChatFab`, `CharacterTourBot`, `InteractiveVoiceBot`, `CallOverlay` and their fetches never mount.

### Pattern 8: 403 → refresh
Mirror the existing `omni:mfa-required` precedent (`services/apiService.ts:311-314`): after `makeRequest`, if `status === 403` and no `X-MFA-Required` header and the URL is not under `/auth/`, call a module-level `notifyPermissionDenied()` that dispatches `window.dispatchEvent(new Event('omni:permission-denied'))` at most once per window (recommend 15 s; leading edge only). `App` listens and calls `refreshPermissions()`. Exclude `/auth/` because `fetchCurrentPermissions` itself uses `authFetch`. Make `refreshPermissions` return `'changed' | 'same' | 'error'` (null from `fetchCurrentPermissions` means error) so the Retry button can render the three UI-SPEC outcomes, and track "access changed" for the in-place notice by comparing the gate result before and after.

### Pattern 9 (recommended extension): server marker for every switched-off nav screen
`hidden_screens` only covers per-screen switches (`SCREEN_SWITCHES`). For an ordinary `view:X` switch the permission simply disappears from the list, so the client cannot tell UI-SPEC variant `switched_off` from `role`. Emit `screen-off:<view>` for every nav view whose permission is in the pre-narrow closure but not in the narrowed list. Cost: a handful of lines in `granted_permissions` plus updating the exact-marker assertions in `test_tenant_feature_switches.py::test_granted_permissions_mark_the_switched_off_screens`. If rejected, collapse both variants to the `role` copy for non-screen switches (Open Question 5).

### Anti-Patterns to Avoid
- **Gating in `handleSetCurrentView` only:** every other `setCurrentView` caller and the initial state bypass it (listed in Pattern 7).
- **Client-side closure or client-side recompute of visibility:** violates "one closure rule" and SC3.
- **Writing roles through `db.roles` (wrapper):** the wrapper's tenant filter comes from a ContextVar and is bypassed for `platform-admin` (`database.py` `_inject_tenant_id`).
- **Literal permission lists in new backend modules:** `test_rbac_defaults.py::test_no_second_permission_table` fails on any `backend/*.py` list/tuple/set of 5+ permission strings and on role-keyed permission dicts (`scan_permission_lists`, `scan_role_tables`). Derive vocabularies from data.
- **Probing every role × every screen through `probe_real_app`:** one existing 12-test run took 215 s; use function-level checks for the matrix.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| manage ⇒ view/request | a second closure | `rbac_defaults.implied_closure` (+ vocabulary filter) | Phase 75 D-20 rule; 76 `manage_twin` only covers `view:` reads |
| Role-name normalization | regex/lowercase | `RBACService._normalize_role` / `rbac_defaults.normalize_role` | single rule; `test_role_literal_guard.py` fails on spelling sets |
| Assignment/content ceiling | custom subset logic | `rbac_defaults.ceiling_allows`, `role_assignment.assert_can_assign_role` | tested matrix in `test_role_assignment_ceiling.py` |
| Tenant narrowing | per-feature `if`s | `tenant_features.narrow`, `hidden_screens`, `enabled_features` | fail-closed semantics already pinned by tests |
| Audit entries | writing `audit_logs` directly | `get_audit_service().log_action_async(...)` as in `user_endpoints._audit` (pass `previous_state`) | adapter onto the hash-chained ledger; the `/api/` middleware already audits mutating routes |
| Route guards | per-route `Depends(verify_permission)` only | the mount guard (inherited) plus an in-route dependency for defense in depth and standalone testability | parity test reads the tag |
| Super-admin test in UI | string comparisons | `isSuperAdminRoleName`, `isPlatformRoleName` | 26 literal comparisons exist today (unification task) |
| Modals, toasts, icons, skeletons | new primitives | `Modal`, `ConfirmationModal`, `showToast`, `components/icons.tsx`, `SkeletonDashboard` | UI-SPEC mandates them |

**Key insight:** every rule in this phase already has a single implementation; the failure mode is writing a second copy (a client closure, a second reserved-name set, a second visibility calculation) that drifts from the first.

## Common Pitfalls

### Pitfall 1: D-06 contradicts the manifest order for ITAM roles
**What goes wrong:** "first allowed sidebar item in menu order" gives every ITAM role `assetManagement` (Assets), not the ITAM console.
**Why:** manifest order is `agents, agentCapabilities, assetManagement, itam` (`shared/catalogue-access.json:36-39`: `{"view": "assetManagement", "label": "Assets", "group": "infra", ...}` precedes `{"view": "itam", "label": "IT Asset Management", ...}`), and all three ITAM roles hold `view:assets` (`rbac_defaults.py:104-115`). Computed over the table: `itam_admin` first=`assetManagement` (5 screens after closure, gaining `assetManagement` and `certificates`), `itam_user` first=`assetManagement`, `itam_viewer` first=`assetManagement`; `platform_billing` first=`auditLog`; every other built-in lands on `dashboard`. [VERIFIED: computed with `python3 -I` this session]
**How to avoid:** implement a landing preference list `['dashboard', 'itam']` ahead of "first allowed in menu order" (so the stated intent "ITAM roles land in the ITAM console" holds) and ask the user to confirm (Open Question 1). Do not reorder the manifest (a test pins nav order).
**Warning signs:** a test that asserts `landingView(itam_viewer) === 'itam'` fails if only menu order is used.

### Pitfall 2: Five built-ins are "editable" in the API
**What goes wrong:** `list_roles` returns `isEditable: builtin.is_editable`, and `analyst`, `security_analyst`, `incident_responder`, `user`, `viewer` are seeded `True` (`rbac_defaults.py:193-202`); `test_rbac_defaults.py:232-235` pins `doc["isEditable"] is (doc["name"] not in non_editable)`. The UI would offer Edit/Delete on built-ins, contradicting D-01.
**How to avoid:** add `builtIn: bool` to the `Role` response model (True for every table role) and make the UI use `builtIn` for the Built-in/Custom chip and for disabling Edit/Delete. Do not change the seeds.

### Pitfall 3: A custom role named `agent` becomes an agent token
**What goes wrong:** `AGENT_ROLE = "agent"` and `is_agent_payload` treats `payload.get("role") == AGENT_ROLE` as an endpoint agent (`authentication_service.py:197-202`); `catalogue_guards.agent_tolerant` skips permission checks for `role == AGENT_ROLE` (`catalogue_guards.py:143`). A user holding a custom role literally named `agent` would carry that role in the JWT.
**How to avoid:** reserve names whose normalized key is in `rbac_defaults.builtin_role_keys()`, equals `AGENT_ROLE`, or is empty, and test it. [VERIFIED: authentication_service.py:197-202, catalogue_guards.py:143]

### Pitfall 4: MFA is keyed on role names, not permissions
**What goes wrong:** `_MFA_REQUIRED_ROLE_KEYS = frozenset({"super_admin", "platform_support", "platform_billing", "tenant_admin", "admin", "itam_admin"})` (`authentication_service.py:72-73`). A custom role with `manage:rbac`, `manage:users` or `manage:settings` is an admin in practice and never needs MFA.
**How to avoid:** needs a decision (Open Question 4). Cheapest safe default: refuse admin-tier permissions in custom roles; fuller fix: make the MFA check consult the role's permissions. Either way a test must pin the chosen behaviour.

### Pitfall 5: Renaming a custom role strands its holders
**What goes wrong:** users store the role name (`user_endpoints.py:309` `"role": stored_role_name(user.role)`), and `_role_docs` matches by exact name. A rename leaves holders with a role that resolves to `[]` (zero access, D-19), and LDAP/SAML mappings keep the old string.
**How to avoid:** make the name immutable after create (server 400 on a changed name; UI disables the field on edit), or cascade atomically. Recommend immutable (Open Question 2).

### Pitfall 6: Custom role assigned by a differently-spelled name
**What goes wrong:** `_role_docs` matches `name` exactly (`rbac_service.py:53`). If an admin types `helpdesk` for a role stored as `Helpdesk`, `effective_permissions` finds nothing.
**How to avoid:** `role_assignment.resolve_assignable_role(db, typed, tenant_id)` returns the canonical stored document name for a custom role (or the existing `stored_role_name` result for a built-in), and user create/update, `assert_can_assign_role` and mapping writes all use that canonical string. `AddUserModal` already submits `r.name` (`components/AddUserModal.tsx:85`).

### Pitfall 7: Deleting a role that mappings or the editor still reference
D-03 only names users. LDAP/SAML group mappings store the role string (`ldap_service.upsert_mapping` / `saml_mapping.upsert_mapping`) and silently produce zero-access users at the next sync if the role disappears. Include mappings in the 409 (Open Question 3).

### Pitfall 8: Super Admin cross-tenant moves
`update_user` lets a Super Admin change `tenantId` (`user_endpoints.py:395-400`). A user holding tenant A's custom role moved to B resolves to `[]`. Validate the role against the destination tenant on a move.

### Pitfall 9: `default:` renders the Dashboard
`renderView()` ends with `default: return <ErrorBoundary name="Dashboard"><Dashboard .../>` (`App.tsx:1845`). Any view string without a case (programmatic `as any` navigations) shows Dashboard content, fail-open for a role without `view:dashboard`. The gate must precede the switch and `default` must return the unmapped panel.

### Pitfall 10: `ifOn` already skips by role, but by coincidence
`switchedOnFor` skips a fetch only when the permission is tenant-switchable (`utils/permissions.ts:29-35`). Every `ifOn` view in `loadAllData` except `tasks` (`view:profile`) has a switchable permission (computed: 31 of 32 views, `tasks` is the exception). So restricted roles are mostly skipped today, and the remaining 403 sources are different: `NotificationCenter` polls `getNotifications()` every 60 s (`NotificationCenter.tsx:123-130`, `getNotifications` → `${API_BASE}/notifications`, `apiService.ts:3898-3900`) while the manifest entry `{"view": "notifications", ... "permission": "view:dashboard", ...}` (`catalogue-access.json:214`, group `mgmt`, enforced) means roles without `view:dashboard` (all three ITAM roles) get a 403 every minute; and `fetchIntegrations` does not check `res.ok` and assigns the 403 error body as data (`apiService.ts:1225-1235`).
**How to avoid:** replace `switchedOnFor` in `ifOn` with the explicit `canReadView`, hide the notification bell when the role cannot read `notifications`, and add `if (!res.ok) return []` to `fetchIntegrations`. Treat D-08's "tabs" as app-shell scope; ITAM console tab gating is ACC-F1 (deferred in REQUIREMENTS.md:40).

### Pitfall 11: Retry and Sign out must not depend on each other
`logoutSession` awaits a `fetch` with no timeout (`apiService.ts:238-254`) and `handleLogout` redirects in `.finally`. If the backend hangs, Sign out hangs too. Add an `AbortController` timeout (about 5 s) to the logout fetch and test that Sign out works while Retry is pending (UI-SPEC requirement).

### Pitfall 12: `refreshPermissions` only runs while connected
The focus/30 s refresh effect returns early `if (!isBackendConnected)` (`App.tsx:826-838`). Acceptable, but the Retry button must call `refreshPermissions` directly, not depend on that effect.

### Pitfall 13: Permissions "unknown" vs "empty"
`derivePermissionState` treats a non-array `permissions` as `[]` (`utils/permissions.ts:96`), so an object missing the field looks like zero access. Add an explicit `permissionsKnown(user)` (`Array.isArray`), show the skeleton while unknown, trigger one refresh, and treat a still-unknown result as empty (fail closed) rather than spinning forever.

### Pitfall 14: Tests that pin the old delivery
`test_login_me_permissions.py` (`ITAM_EXPECTED["itam_admin"]` and the `test_itam_viewer_login_list_is_exact` style exact lists) and `test_tenant_feature_switches.py` assert exact delivered lists; with the closure `itam_admin` gains `request:assets`, `view:assets`, `view:licenses`. Update them as the first backend task (Wave 0), not at the end.

### Pitfall 15: Role-store races
No unique index exists on `roles` (no migration touches it). Two concurrent creates of one name can both pass an application check. Acceptable for an admin-only action with a read-after-write check; an optional migration 023 (`create_index([("tenantId",1),("nameKey",1)], unique=True, partialFilterExpression={"nameKey": {"$exists": True}})`) closes it but runs at the user's next backend restart, so make it a separate, user-approved task.

## Code Examples

Verified current behaviour that the plan replaces (quotes are verbatim):

```tsx
// components/Sidebar.tsx:181 (fail-open fallback to remove)
const hasPermission = userContext?.hasPermission || (() => true);
```
```tsx
// App.tsx:1178-1180 (silent denial to replace with the panel)
} else {
  console.warn(`User does not have permission to view: ${view}`);
```
```tsx
// App.tsx:1980 (navigation path that bypasses the gate)
onNavigate={(view) => setCurrentView(view as any)}
```
```ts
// services/apiService.ts:311-314 (the precedent for a window event from authFetch)
if (response.status === 403 && response.headers.get('X-MFA-Required') && !_mfaRequired) {
    _mfaRequired = true;
    window.dispatchEvent(new Event('omni:mfa-required'));
}
```
```python
# backend/catalogue_mounts_billing_identity.py (the guard every route on role_endpoints.router inherits)
ROLE_MANAGEMENT_GUARD = catalogue_guard("roleManagement", read=_USER_READ, write=("manage:rbac",))
```

Proposed role-write skeleton (all names verified; values are the project's own):
```python
class RoleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=64)
    description: str = Field(default="", max_length=500)
    permissions: List[str] = Field(default_factory=list, max_length=400)
    tenantId: Optional[str] = None            # Super Admin only; ignored/403 for others

@router.post("", response_model=Role, status_code=201, dependencies=[Depends(_require_role_write_access)])
async def create_role(body: RoleWrite, current_user: TokenData = Depends(get_current_user)):
    tenant = await _resolve_write_tenant(current_user, body.tenantId)      # 400 for platform tenant / sentinels
    name = validate_role_name(body.name, existing=await _tenant_role_docs(tenant))   # reserved + built-in + duplicate
    perms = validate_permissions(body.permissions)                         # vocabulary, not banned, <= cap
    await assert_can_edit_role_contents(get_database(), current_user, old=[], new=perms)
    ...insert via get_database()._db.roles, then audit "role.created"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Role edits kept in browser memory (`saveRole`/`deleteRole`, `apiService.ts:2728-2740`) | Server-persisted tenant custom roles | This phase | Role edits become real and visible to other sessions |
| Closure only in the backend read guard (76 D-07) | Closure in the resolver used by enforcement and delivery | This phase | Menu equals guard for every role |
| Gate = one `if` in `handleSetCurrentView` | Pure access function + render-time gate | This phase | One definition for sidebar, hash, deep link, in-app navigation |

**Deprecated/outdated:** `currentScreenOff` redirect effect (`App.tsx:1020-1026`); `Sidebar`'s literal super-admin comparison (`Sidebar.tsx:224`, `:287`), which omits `platform-admin` that `isSuperAdminRoleName` accepts.

## Runtime State Inventory

Not a rename/migration phase. Related stored state worth stating explicitly:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `roles` collection: 13 shared mirror documents (tenantId `all`/`platform`); tenant custom role documents (none expected on this fresh VM, per memory); `users.role` strings; `ldap_group_mappings` / `saml_group_mappings` role strings | code edit only; no data migration. New documents are additive |
| Live service config | None | None |
| OS-registered state | None | None |
| Secrets/env vars | None | None |
| Build artifacts | `dist-new/` is the Vite output dir (`vite.config.ts`); the UI publish belongs to the user | do not publish or restart |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node / npm | vitest, build | yes | v20.20.2 / 10.8.2 | — |
| Python + `backend/venv` | pytest | yes | 3.12.3 / pytest 9.1.1 | — |
| vitest baseline | frontend tests | yes | 3 files, 57 tests passed (`permissions`, `catalogueAccess`, `SidebarTenantSwitches`) | — |
| Backend baseline | role tests | yes | 230 passed in 15.9 s (`test_roles_endpoint`, `test_login_me_permissions`, `test_role_assignment_ceiling`) | — |
| Live MongoDB | not needed | not probed | — | tests use the in-memory `role_store` and the throwaway env of `_route_walk.throwaway_env()`; never point tests at the live DB |
| Real browser for UI verification | UI-SPEC checks, C15/C51 | not probed | — | `human_verify_mode: end-of-phase` in config; list as UAT items |

**Missing dependencies with no fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | vitest ^5.0.0 + @testing-library/react (jsdom) for the UI; pytest 9.1.1 + pytest-asyncio 1.4.0 for the backend |
| Config file | `vite.config.ts` (`test:` block, include `src/**/*.{test,spec}`), `backend/tests/conftest.py` |
| Quick run command | `npx vitest run src/__tests__/<file>` ; `cd backend && venv/bin/python -m pytest tests/<file> -q` |
| Full suite command | `npx vitest run src/__tests__` ; `cd backend && venv/bin/python -m pytest tests -q` (the catalogue/real-app modules take minutes) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACC-06 | Sidebar denies with no context / empty / unknown permissions; no item for ungranted catalogue; `platform-admin` spelling still sees everything | unit (jsdom) | `npx vitest run src/__tests__/SidebarFailClosed.test.tsx` | Wave 0 |
| ACC-06 | `evaluateViewAccess` matrix: role, switched_off, unmapped (super admin included), platform roles, hash/deep link/in-app all route through it | unit | `npx vitest run src/__tests__/viewAccess.test.ts` | Wave 0 |
| ACC-06 | `landingView`: dashboard; ITAM roles -> itam; platform_billing -> auditLog; zero screens -> null | unit | `npx vitest run src/__tests__/viewAccess.test.ts` | Wave 0 |
| ACC-06 | `NoAccessPanel` three variants + focus; `ZeroAccessScreen` Retry tri-state, Sign out works while Retry pending | component | `npx vitest run src/__tests__/NoAccessScreens.test.tsx` | Wave 0 |
| ACC-06 | Source guards: no `default:` Dashboard fallback, no `onNavigate={... setCurrentView(` bypass, no literal super-admin comparison outside `utils/permissions.ts` | source-grep (pattern of `catalogueAccess.test.ts:156-170`) | `npx vitest run src/__tests__/catalogueAccess.test.ts` | extend existing |
| ACC-07 | Visibility payload equals `session_permissions` result per built-in role and switch config; platform/super roles; custom role; other tenant's role 404; platform roles hidden from non-super | backend unit (in-memory store) | `pytest tests/test_role_visibility.py -q` | Wave 0 |
| ACC-07 | Payload equals `check_catalogue_access` outcome for every enforced-group catalogue (function level, no handler run) | backend unit | `pytest tests/test_role_visibility.py -q` | Wave 0 |
| ACC-07 | `RoleVisibilityPanel` states (loading, empty, error, groups, switched-off sub-list) | component | `npx vitest run src/__tests__/RoleVisibilityPanel.test.tsx` | Wave 0 |
| ACC-08 | `authFetch` dispatches `omni:permission-denied` once per window; not for `/auth/`, not for `X-MFA-Required`; App refresh result switches gate | unit | `npx vitest run src/__tests__/permissionRefresh.test.ts` | Wave 0 |
| ACC-08 | Role edit visible in next `/me` without re-login (edit role doc, call `/me` again) | backend unit | `pytest tests/test_role_write_api.py -q` | Wave 0 |
| ACC-09 | Closure delivery: `itam_admin` gains `assetManagement`/`certificates` (+`request:assets`, `view:assets`, `view:licenses`); tenant admin unchanged; screen-off marker for closure-granted screen; `_fallback_permissions` parity; `request:assets` check passes for `itam_admin` | backend unit | `pytest tests/test_closure_delivery.py tests/test_login_me_permissions.py -q` | Wave 0 + update |
| ACC-09 | Role-write API: ceiling matrix, banned/platform/super-only permissions, reserved + built-in name collisions (all spellings), `agent`, caps, immutable name, 409 holders/mappings, platform tenant refused, extra fields rejected, audit entry | backend unit | `pytest tests/test_role_write_api.py -q` | Wave 0 |
| ACC-09 | Custom-role assignment: user create/update, other tenant's role rejected, canonical name stored, tenant move, LDAP/SAML mapping accept/refuse + ceiling | backend unit | `pytest tests/test_custom_role_assignment.py -q` | Wave 0 |
| ACC-09 | Per-tenant isolation: tenant A edit never changes tenant B `/me`; same-named roles independent; wrong-tenant role id 404; `all`/`platform` sentinels unreachable by the API | backend unit | `pytest tests/test_role_tenant_isolation.py -q` | Wave 0 |
| ACC-09 | Super-admin handling: `Super Admin`, `super_admin`, `superadmin`, `platform-admin` get `["*"]`, pass every guard; platform roles not narrowed | backend unit | `pytest tests/test_role_tenant_isolation.py -q` | Wave 0 |
| ACC-09 | Route parity still green with new routes (inherited mount guard) | backend, slow | `pytest tests/test_catalogue_route_parity.py -q` | exists |
| ACC-09 | Real-app probe sample (<= 20 cases): new write routes refuse `viewer`/`itam_admin` (403) and accept tenant admin past the guard | backend, slow | `pytest tests/test_role_routes_real_app.py -q` | Wave 0 |

### Sampling Rate
- **Per task commit:** the single new/changed test file (vitest or pytest) plus any exact-list tests it touches.
- **Per wave merge:** `npx vitest run src/__tests__` and `pytest tests/test_role*.py tests/test_login_me_permissions.py tests/test_tenant_feature_switches.py tests/test_rbac_defaults.py tests/test_role_assignment_ceiling.py tests/test_catalogue_guards.py -q`.
- **Phase gate:** full vitest, `npm run build`, then `pytest tests/test_catalogue_route_parity.py tests/test_catalogue_slice_billing_identity.py tests/test_audit_parity.py -q` (slow: budget several minutes), before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/test_closure_delivery.py`, `test_role_write_api.py`, `test_role_visibility.py`, `test_custom_role_assignment.py`, `test_role_tenant_isolation.py`, `test_role_routes_real_app.py` — cover ACC-07/08/09.
- [ ] `src/__tests__/viewAccess.test.ts`, `SidebarFailClosed.test.tsx`, `NoAccessScreens.test.tsx`, `RoleVisibilityPanel.test.tsx`, `permissionRefresh.test.ts`, role editor / roles tab tests — cover ACC-06/07/08.
- [ ] Update exact-list assertions in `test_login_me_permissions.py` and `test_tenant_feature_switches.py` for the closure (do first).
- [ ] Optional cross-stack fixture: `shared/role-nav-snapshot.json` (role -> visible nav views, generated from the backend table and checked by a backend test) consumed by the vitest Sidebar test, so "per role" visibility is proven against the real table without duplicating it in TypeScript. Regeneration must be a script the developer runs; a test must only read it (the Phase 76 ledger rule PROH-76-03 forbids tests writing shared files).
- Framework install: none.

## Security Domain

### Applicable ASVS Categories (level 1, `security_enforcement` on)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | admin-tier MFA for roles that carry admin permissions (Pitfall 4) |
| V3 Session Management | yes | no change to JWT; sessions revoked on role reassignment already (`revoke_user_sessions`); permissions refreshed via `/me` |
| V4 Access Control | yes | catalogue mount guard + in-route `manage:rbac`; D-20 ceiling for contents and assignment; tenant-scoped lookups |
| V5 Input Validation | yes | Pydantic `extra="forbid"`, name pattern and length, permission vocabulary and cap, id format |
| V6 Cryptography | no | nothing new |
| V7 Logging | yes | `role.created/updated/deleted` via the audit adapter with before/after permission sets |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Privilege escalation by writing a role above the editor's own set | Elevation | `ceiling_allows(editor_perms, delta)`, symmetric difference, fail closed on store error |
| Escalation by assigning an over-privileged custom role | Elevation | existing `assert_can_assign_role` on the canonical custom role name |
| Cross-tenant role write/read/IDOR by role id | Tampering / Info disclosure | every lookup filtered by the validated `tenantId`; never the `all`/`platform` sentinels; 404 for other tenants' ids |
| Super Admin write landing in the platform tenant or a shared sentinel | Tampering | refuse `platform-admin`, `all`, `platform` as targets |
| Role-name impersonation (`agent`, built-in spellings, platform roles) | Spoofing / Elevation | reserved-name rule after `normalize_role` (Pitfall 3) |
| Admin without MFA through a custom role | Elevation | Pitfall 4 decision |
| Mass assignment (`tenantId`, `id`, `isEditable`, `*`) | Tampering | `extra="forbid"`, banned permission strings `*`, `SUPER_ADMIN_ONLY_PERMISSIONS`, `PLATFORM_ONLY_PERMISSIONS` |
| Oversized payload / many roles | DoS | caps on name, description, permissions per role and roles per tenant (list_roles reads `to_list(500)`) |
| Stored script in role name/description | Tampering | React escapes text; keep names to a restricted character set; never `dangerouslySetInnerHTML` |
| Stale permissions after edit | Info disclosure | enforcement reads the DB per request; UI refresh on focus/403 |
| Delete race (user assigned during delete) | Tampering | accept; D-19 gives zero access, never more access |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Filtering the delivered closure to known permission strings (instead of the raw `implied_closure`) is acceptable | Pattern 1 | Low; raw closure adds ~55 junk strings to a tenant admin `/me` but is functionally harmless |
| A2 | ITAM roles should land in the ITAM console via a preference list, overriding pure menu order | Pitfall 1 | Users land on Assets instead; user must confirm |
| A3 | Custom role names are immutable after creation | Pitfall 5 | If renaming is wanted, a cascade (users, mappings, sessions) must be designed |
| A4 | Deleting a custom role is also refused while LDAP/SAML mappings reference it | Pitfall 7 | If not, mappings silently create zero-access users |
| A5 | Custom roles carrying admin-tier permissions need MFA or must be refused | Pitfall 4 | Admin accounts without MFA |
| A6 | A server `screen-off:` marker for every switched-off nav screen is acceptable (changes `/me` payload and the marker test) | Pattern 9 | Panel falls back to the generic `role` copy |
| A7 | Real-app probe cost (about 215 s for 12 existing tests) is representative; the large matrix belongs at function level | Validation | If probes are cheaper than measured, a wider real-app sample is affordable |
| A8 | Closure in `granted_permissions` also widening strict `view:X` / `request:X` checks for any `manage:X` holder (custom roles included) is intended by D-11 | Pattern 1 | Slightly broader backend access for custom roles with a manage: but no view: grant |
| A9 | An unselected-tenant Super Admin view should show built-in roles unnarrowed with an explicit label | Open Question 6 | Wrong basis line shown to the owner |
| A10 | Optional unique index migration (023) is wanted | Pitfall 15 | Duplicate role names under a race |

## Open Questions

1. **ITAM landing (D-06).** Menu order puts Assets before the ITAM console. Recommendation: landing preference `['dashboard', 'itam']` then first allowed; confirm with the user. 
2. **Rename of a custom role.** Recommendation: immutable name (UI disables the field on edit).
3. **Delete refusal scope.** Recommendation: also refuse while LDAP/SAML mappings of the tenant reference the role; return the mappings next to the holders.
4. **MFA for admin-tier custom roles.** Recommendation: until MFA consults permissions, refuse custom roles that include `manage:rbac`, `manage:users`, `manage:settings`, `manage:api_keys` or `control:remote_access` (define the set inside `rbac_defaults.py`, which the drift scanner skips); present both options to the user.
5. **`switched_off` vs `role` copy.** Adopt Pattern 9 (server markers) or collapse to one reason for non-screen switches.
6. **Super Admin with no tenant selected.** What does Settings > Roles and "What it can see" show? Recommendation: built-in roles unnarrowed with basis line "No tenant selected; tenant screen switches do not narrow it" (needs a copy line the UI-SPEC lacks); custom roles require a selected tenant.
7. **D-08 scope against ACC-F1.** Recommendation: startup fetches, `NotificationCenter`, the Dashboard widgets that read gated data, and a reusable `canReadView`; leave ITAM console tabs to ACC-F1.
8. **Permission vocabulary.** Custom roles can only contain strings known to the table, manifest or switch catalogue; routes that check outside it (for example HA/DR `view:backups`, noted in 76-11) cannot be granted to custom roles, even by a Super Admin. Acceptable?
9. **Optional index migration** (Pitfall 15): include as a user-approved task or skip.

## Sources

### Primary (HIGH confidence, read in this session)
- `backend/role_endpoints.py`, `role_assignment.py`, `rbac_service.py`, `rbac_defaults.py`, `rbac_utils.py`, `tenant_features.py`, `catalogue_guards.py`, `catalogue_mounts_billing_identity.py`, `catalogue_mounts.py`, `user_endpoints.py`, `authentication_service.py` (lines 68-79, 190-210, 385-410), `authentication_endpoints.py` (login/me/signup), `tenant_middleware.py`, `database.py`, `app_startup.py` (role mirror), `saml_mapping.py`, `ldap_service.py`, `ldap_endpoints.py`, `itam_asset_request_endpoints.py`, `audit_service.py`
- `backend/tests/_route_walk.py`, `_catalogue_parity.py`, `rbac_test_support.py`, `test_roles_endpoint.py`, `test_role_assignment_ceiling.py`, `test_login_me_permissions.py`, `test_rbac_defaults.py`, `test_catalogue_slice_assets.py`
- `shared/catalogue-access.json`, `shared/tenant-feature-switches.json`, `shared/catalogue-gaps.json`
- `App.tsx` (280, 426-457, 480-598, 602-690, 747-838, 1011-1026, 1163-1182, 1593-1600, 1815-1999), `components/Sidebar.tsx`, `SettingsRolesTab.tsx`, `RoleEditorModal.tsx`, `SettingsDashboard.tsx`, `NotificationCenter.tsx`, `utils/catalogueAccess.ts`, `utils/permissions.ts`, `contexts/UserContext.tsx`, `services/apiService.ts` (238-317, 437-473, 700-760, 1225-1235, 2728-2740, 3898-3906), `src/__tests__/*` patterns
- `.planning/phases/75-*/75-CONTEXT.md`, `76-*/76-CONTEXT.md`, `76-UAT.md`, `76-11-SUMMARY.md`, `REQUIREMENTS.md`, `ROADMAP.md`
- Commands run: `npx vitest run` (3 files, 57 passed); `venv/bin/python -m pytest` (230 passed, 15.9 s; 12 slice tests 215 s); `python3 -I` scripts for role/nav and closure measurements

### Secondary (MEDIUM confidence)
- 77-UI-SPEC.md (approved design contract; behaviour needing a browser is unverified here)

### Tertiary (LOW confidence)
- None. The code graph (`.planning/graphs/graph.json`) was 127 hours and 488 commits stale, so it was not used.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, nothing new is installed; versions read from `package.json` and the venv.
- Architecture: HIGH for backend (guards, resolver, isolation read in full); MEDIUM for frontend wiring (App.tsx read by range, not entirely).
- Pitfalls: HIGH for items 1-3, 5-6, 9-11 (direct code evidence); MEDIUM for 4, 7, 8, 15 (design consequences, not failing tests).

**Research date:** 2026-10-18
**Valid until:** 2026-11-17 (stable; revalidate if Phase 76 is deployed or `shared/catalogue-access.json` changes order)
