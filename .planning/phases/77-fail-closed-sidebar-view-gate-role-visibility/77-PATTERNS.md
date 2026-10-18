# Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility - Pattern Map

**Mapped:** 2026-10-18
**Files analyzed:** 26 (new + modified, from CONTEXT D-01..D-18 and RESEARCH structure)
**Analogs found:** 24 / 26
All analog paths below were checked as git-tracked (`git ls-files`); none are mirror paths.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/role_endpoints.py` (EDIT: POST/PUT/DELETE, visibility, catalogue) | route | CRUD | itself (`list_roles`) + `backend/user_endpoints.py` | exact |
| `backend/role_contents.py` (NEW) | service/util | transform | `backend/role_assignment.py` | role-match |
| `backend/role_visibility.py` (NEW) | utility | transform | `backend/tenant_features.py` (`narrow`, `hidden_screens`) | role-match |
| `backend/permission_vocabulary.py` (NEW) | utility | transform | `backend/tenant_features.py` (reads manifest/switch JSON) | partial |
| `backend/rbac_service.py` (EDIT: closure in `granted_permissions`, `_fallback_permissions`) | service | request-response | itself | exact |
| `backend/rbac_defaults.py` (EDIT: `deliverable_closure`, admin-tier set) | config | transform | `implied_closure`, `ceiling_allows` | exact |
| `backend/role_assignment.py` (EDIT: `resolve_assignable_role`) | service | request-response | itself | exact |
| `backend/user_endpoints.py` (EDIT: replace `_VALID_ROLE_KEYS`) | route | CRUD | itself, lines 39, 274, 365 | exact |
| `backend/ldap_service.py`, `backend/saml_mapping.py` (EDIT) | service | CRUD | `role_assignment.refuse_directory_platform_role` call sites | role-match |
| `backend/authentication_service.py` (EDIT: permission-based MFA, D-14) | service | request-response | itself (`_MFA_REQUIRED_ROLE_KEYS` ~l.72) | exact |
| `backend/tests/test_role_write_api.py`, `test_role_visibility.py`, `test_closure_delivery.py`, `test_custom_role_assignment.py`, `test_role_tenant_isolation.py` (NEW) | test | CRUD | `test_roles_endpoint.py`, `test_role_assignment_ceiling.py` | exact |
| `backend/tests/test_login_me_permissions.py`, `test_tenant_feature_switches.py` (EDIT) | test | request-response | themselves | exact |
| `utils/viewAccess.ts` (NEW) | utility | transform | `utils/permissions.ts` | exact |
| `utils/permissions.ts` (EDIT) | utility | transform | itself | exact |
| `components/Sidebar.tsx` (EDIT l.181) | component | request-response | itself | exact |
| `components/NoAccessPanel.tsx`, `ZeroAccessScreen.tsx` (NEW) | component | request-response | `components/ConfirmationModal.tsx` (icons/Tailwind style) | partial |
| `components/RoleVisibilityPanel.tsx` (NEW) | component | request-response | `components/SettingsRolesTab.tsx` | role-match |
| `components/RoleDeleteRefusalModal.tsx` (NEW) | component | event-driven | `components/ConfirmationModal.tsx` (on `Modal.tsx`) | role-match |
| `components/SettingsRolesTab.tsx`, `RoleEditorModal.tsx` (EDIT) | component | CRUD | themselves | exact |
| `components/NotificationCenter.tsx` (EDIT: hide when unreadable) | component | polling | itself l.123-130 | exact |
| `App.tsx` (EDIT: gate, landing, 403 listener) | provider/shell | event-driven | itself (`handleSetCurrentView`, `refreshPermissions`, `ifOn`) | exact |
| `services/apiService.ts` (EDIT: 403 event, role API, logout timeout, `fetchIntegrations`) | service | request-response | itself l.311-314 (`omni:mfa-required`) | exact |
| `src/__tests__/viewAccess.test.ts`, `permissionRefresh.test.ts` (NEW) | test | transform | `src/__tests__/permissions.test.ts` | exact |
| `src/__tests__/SidebarFailClosed.test.tsx`, `NoAccessScreens.test.tsx`, `RoleVisibilityPanel.test.tsx` (NEW) | test | component | `src/__tests__/SidebarTenantSwitches.test.tsx` | exact |
| `src/__tests__/catalogueAccess.test.ts` (EDIT: source-grep guards) | test | source-grep | itself l.156-170 | exact |

## Pattern Assignments

### `backend/role_endpoints.py` (route, CRUD)

**Analog:** itself (read in full, 87 lines) plus `backend/user_endpoints.py` for write/audit shape.

**Imports/guard** (role_endpoints.py l.1-16): FastAPI `APIRouter(prefix="/api/roles")`, `get_database`, `is_super_admin`, `verify_permission`, `effective_permissions`, `RBACService`. The mount guard `ROLE_MANAGEMENT_GUARD` (catalogue_mounts_billing_identity.py) is inherited by every route on this router; new routes need no ledger entry. Add in-route `manage:rbac` dep modelled on `_require_role_list_access` (l.28-38):
```python
async def _require_role_list_access(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    if await verify_permission(current_user, "manage:users") or await verify_permission(current_user, "manage:rbac"):
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: manage:users or manage:rbac")
```
**Raw handle for role docs** (l.68-70): `docs = await db._db.roles.find({"tenantId": tenant_id}).to_list(500)`. Writes use the same raw handle with an explicit validated `tenantId` in every filter.
**Skip-built-in rule** (l.73): `RBACService._normalize_role(name) in builtin_keys`; new name validation must be at least this strict.
**Error handling** (l.83-85): wrap store errors, log, raise 503 "Role store unavailable". Add `builtIn: bool` to the `Role` model (l.19-25); built-ins `True`, docs `False` (D-18).
**Tenant resolution + existence check:** `user_endpoints.py` l.69-70 `_tenant_exists`; l.277-284 (`if caller_is_super_admin and user.tenantId: target_tenant_id = user.tenantId else get_tenant_id()`).
**Audit** (user_endpoints.py l.72-82): copy `_audit` with `resource_type="role"`:
```python
await get_audit_service().log_action_async(
    user_name=actor, action=action, resource_type="user", resource_id=target,
    details=f"{action}: {target}", tenant_id=tenant_id)
```
(wrapped in try/except that logs and continues). Call sites l.322, 431, 478.
**Ceiling for contents** (reuse `rbac_defaults.ceiling_allows`, rbac_defaults.py l.300-310; symmetric-difference delta per RESEARCH Pattern 3; fail closed 503 like role_assignment.py l.134-141).

### `backend/role_contents.py` / `role_visibility.py` / `permission_vocabulary.py` (NEW)

**Analog:** `backend/role_assignment.py` (pure + async helper layout, `HTTPException` messages, module docstring citing decision ids) and `backend/tenant_features.py` (`narrow` l.127-131, `hidden_screens`, `screen_permissions` for the visibility computation).
**Constraint:** `test_rbac_defaults.py::test_no_second_permission_table` fails on any backend list/tuple/set of 5+ permission strings; derive vocabularies from `ROLE_DEFAULTS`, the manifest and the switch catalogue. Put the admin-tier set (D-14) inside `rbac_defaults.py` (scanner skips it).
**Name normalization:** `RBACService._normalize_role` / `rbac_defaults.normalize_role`; reserve names whose key is in `builtin_role_keys()`, equals `AGENT_ROLE`, or is empty (D-18).

### `backend/rbac_service.py` and `rbac_defaults.py` (closure, D-11)

**Analog:** `granted_permissions` (rbac_service.py ~l.113-125) and `_fallback_permissions`:
```python
perms = await effective_permissions(db, role, tenant_id)
if "*" in perms or not tenant_features.applies_to(role):
    return perms
enabled = await tenant_features.enabled_features(tenant_id, lambda: db)
narrowed = tenant_features.narrow(perms, enabled)
return narrowed + tenant_features.hidden_screens(narrowed, enabled)
```
Insert the vocabulary-filtered closure between `applies_to` return and `narrow`, in both functions. Base on `implied_closure` (rbac_defaults.py l.284-297):
```python
closed = set(perms)
for perm in list(closed):
    if perm.startswith("manage:"):
        suffix = perm[len("manage:"):]
        closed.add("view:" + suffix); closed.add("request:" + suffix)
return frozenset(closed)
```
`effective_permissions` stays un-closed (it is the role definition used by the ceiling).

### `backend/role_assignment.py` / `user_endpoints.py` / `ldap_service.py` / `saml_mapping.py`

**Analog:** `assert_can_assign_role` (role_assignment.py l.95-146) and `user_endpoints.py` l.39 `_VALID_ROLE_KEYS = rbac_defaults.builtin_role_keys()` with checks at l.274 and l.365:
```python
requested_role_key = _normalize_role(user.role)
if requested_role_key not in _VALID_ROLE_KEYS:
    raise HTTPException(status_code=400, detail=f"Invalid role '{user.role}'")
```
Replace with `resolve_assignable_role(db, typed, tenant_id)` (canonical stored name for custom roles, own tenant only), then the existing `assert_can_assign_role`. Directory call sites mirror `refuse_directory_platform_role` (l.50-55). Cross-tenant move (user_endpoints ~l.395-400) must re-validate the role against the destination tenant (D-18).

### `backend/authentication_service.py` (MFA, D-14)
**Analog:** itself, `_MFA_REQUIRED_ROLE_KEYS` ~l.72-73 (name-keyed frozenset). Replace with a check over `effective_permissions` against the admin-tier set from `rbac_defaults`.

### Backend tests

**Analog:** `backend/tests/test_roles_endpoint.py` (TestClient on a bare `FastAPI` with `dependency_overrides` for `get_current_user`, `_custom(name, tenant, permissions)` doc helper l.25-30) and `test_role_assignment_ceiling.py` (hard-coded EXPECTED matrix, `_caller`, `_store(extra_docs)`, `_BrokenRoles` fail-closed case, `@pytest.mark.parametrize`).
```python
from tests.rbac_test_support import role_store, shared_role_docs
db, raw = role_store(roles=shared_role_docs() + list(extra_docs))
```
`StoreCollection` supports `insert_one`, `update_one`, `delete_one`, `count_documents` (rbac_test_support.py l.19-56). Use function-level checks for the role x screen matrix; limit `probe_real_app` to a small sample (about 215 s for 12 tests). Update exact-list assertions in `test_login_me_permissions.py` and `test_tenant_feature_switches.py` first (itam_admin gains `request:assets`, `view:assets`, `view:licenses`).

### `utils/viewAccess.ts` (NEW, utility, transform)

**Analog:** `utils/permissions.ts` and `utils/catalogueAccess.ts`.
**Imports:**
```ts
import type { AppView, Permission, User } from '../types';
import { catalogueFor, viewPermission, CATALOGUES, NAV_GROUPS } from './catalogueAccess';
import { screenAllowed, isSuperAdminRoleName, isPlatformRoleName } from './permissions';
```
**Core rule to copy** (App.tsx l.1165-1181 current gate, to be lifted into the pure function):
```ts
if (isSuperAdminRoleName(currentUser?.role)) { setCurrentView(view); return; }
const requiredPermission = viewPermission(view) as Permission;
const screenOk = isPlatformRoleName(currentUser?.role) || screenAllowed(view, hasPermission);
if (hasPermission(requiredPermission) && screenOk) ...
```
Add: unknown view (no `catalogueFor`) denied for everyone; permission "unknown" via `Array.isArray(user.permissions)` (permissions.ts l.96 treats non-array as `[]`); `landingView` preference `['dashboard','itam']` then first allowed nav item (D-12). `derivePermissionState` (permissions.ts l.92-108) shows the `*`/super-admin handling to honour.

### `components/Sidebar.tsx` (EDIT)
**Analog:** itself l.180-181. Replace `userContext?.hasPermission || (() => true)` with `|| (() => false)`. Keep file under 500 lines (pinned by a catalogueAccess test). Replace literal super-admin comparisons (l.224, l.287) with `isSuperAdminRoleName`.

### `components/NoAccessPanel.tsx`, `ZeroAccessScreen.tsx`, `RoleDeleteRefusalModal.tsx`
**Analog:** `components/ConfirmationModal.tsx` (props interface, `Modal` + footer buttons, `AlertTriangleIcon` from `./icons`, `isDestructive`). Use `components/icons.tsx`, `Modal`, `showToast`, `SkeletonDashboard`; follow `77-UI-SPEC.md` for copy and tokens.

### `components/SettingsRolesTab.tsx` / `RoleVisibilityPanel.tsx` / `RoleEditorModal.tsx`
**Analog:** `SettingsRolesTab.tsx` l.1-40 (Props `{roles, canManageSettings, onEdit, onDelete, onNew}`, table with permission-count chip). Use `role.builtIn` (not `isEditable`) for Built-in/Custom chip and disabled Edit/Delete; add a "What it can see" row panel fetching `GET /api/roles/{id}/visibility`. Disable the name field when editing (D-13).

### `App.tsx` (EDIT; already ~2000 lines, put new logic in new modules)
**Analogs (self):** `handleSetCurrentView` l.1165-1181 (replace `console.warn` branch); `refreshPermissions` ~l.814 with `visibilitychange` and 30 s refresh ~l.824-838 (reuse, add `omni:permission-denied` listener, return `'changed'|'same'|'error'`); `loadAllData` `ifOn(view, fetch)` ~l.497 (swap `switchedOnFor` for `canReadView`); remove `currentScreenOff` effect ~l.1020-1026 and its `return null` ~l.1594; `renderView` `default:` (~l.1845) must return unmapped panel, not Dashboard; `ChatAssistant onNavigate` (~l.1980) use handler; `setCurrentView('compliance')` (~l.893) and `handleLogin` (~l.620), `registerTenant` (~l.1149) use landing. Zero-access early return goes beside `if (!currentUser)` (~l.1583).

### `services/apiService.ts` (EDIT)
**Analog (403 event precedent), l.311-314:**
```ts
if (response.status === 403 && response.headers.get('X-MFA-Required') && !_mfaRequired) {
    _mfaRequired = true;
    window.dispatchEvent(new Event('omni:mfa-required'));
}
```
Add a sibling: 403 without `X-MFA-Required`, URL not under `/auth/`, debounced leading-edge ~15 s, dispatch `omni:permission-denied`. Also: replace fake `saveRole`/`deleteRole` (~l.2728-2740) with real calls; `logoutSession` (~l.238-254) gets an `AbortController` ~5 s timeout; `fetchIntegrations` (~l.1225-1235) add `if (!res.ok) return []`.

### `components/NotificationCenter.tsx` (EDIT)
**Analog:** itself l.123-130 (60 s `getNotifications()` poll). Gate by `canReadView('notifications')`; skip poll and hide bell when not readable (manifest permission is `view:dashboard`).

### Frontend tests
**Analog 1:** `src/__tests__/SidebarTenantSwitches.test.tsx` (mocks `../../services/apiService` and `socketService`, renders `Sidebar` inside `UserContext.Provider value={{currentUser, hasPermission, serverLockedFeatures}}`, reads button labels via `container.querySelectorAll('button')`):
```tsx
vi.mock('../../services/apiService', () => ({ authFetch: vi.fn(), fetchSupportUnreadCount: () => Promise.resolve(0) }));
vi.mock('../../services/socketService', () => ({ socketService: { on: vi.fn(), off: vi.fn() } }));
```
Fail-closed variant: render with `UserContext.Provider value={null}`/missing `hasPermission` and assert no nav buttons.
**Analog 2:** `src/__tests__/permissions.test.ts` for pure-function tests (`viewAccess`, `permissionRefresh`). **Analog 3:** `catalogueAccess.test.ts` l.156-170 for source-grep guards (no `default:` Dashboard fallback, no `onNavigate={... setCurrentView(`, no literal super-admin compare outside `utils/permissions.ts`).

## Shared Patterns

### Tenant-scoped raw role access
**Source:** `backend/role_endpoints.py` l.68-70. Role writes/reads use `db._db.roles` with explicit validated `tenantId`; never the wrapper (unscoped for `platform-admin`). Refuse target tenants `platform-admin`, `all`, `platform`.

### Ceiling / fail closed
**Source:** `backend/role_assignment.py` l.134-146 (`try` resolve both sets, 503 on store error, `ceiling_allows` else 403). Apply to role-content writes and assignment.

### Audit
**Source:** `backend/user_endpoints.py` l.72-82 (`get_audit_service().log_action_async`, errors logged not raised).

### One permission source in the UI
**Source:** `utils/permissions.ts` `derivePermissionState` + `isSuperAdminRoleName`/`isPlatformRoleName`; permissions only from server-delivered `currentUser.permissions`, no client closure.

### Manifest reader
**Source:** `utils/catalogueAccess.ts` l.1-40 (`CATALOGUES`, `CATALOGUE_GROUPS`, `catalogueFor`, `viewPermission`); never hard-code view-to-permission maps.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/permission_vocabulary.py` | utility | transform | No existing "known permission strings" aggregator; compose from `ROLE_DEFAULTS` + manifest + switch JSON (closest: `tenant_features.py` JSON loading) |
| `components/NoAccessPanel.tsx` / `ZeroAccessScreen.tsx` | component | request-response | No existing empty/forbidden full-page screen; follow 77-UI-SPEC and `ConfirmationModal` styling |

## Metadata

**Analog search scope:** `backend/` (role/rbac/user/tenant_features/tests), `utils/`, `components/` (Sidebar, Settings*, Role*, ConfirmationModal, NotificationCenter), `services/apiService.ts`, `App.tsx`, `src/__tests__/`.
**Pattern extraction date:** 2026-10-18
**Note:** App.tsx / apiService.ts line numbers come from RESEARCH.md (verified there this week) except l.1165-1181 and l.311-314, read directly here; the working tree has unrelated uncommitted changes, so re-grep before editing.
