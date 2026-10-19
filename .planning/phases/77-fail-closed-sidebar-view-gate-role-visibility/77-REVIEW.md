---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
reviewed: 2026-10-19T00:00:00Z
reviewed_incremental: 2026-10-19
incremental_files:
  - App.tsx
  - src/__tests__/catalogueAccess.test.ts
incremental_scope: fix commit a1f4488d1 (WR-01)
depth: standard
files_reviewed: 56
files_reviewed_list:
  - App.tsx
  - backend/authentication_endpoints.py
  - backend/authentication_service.py
  - backend/ldap_endpoints.py
  - backend/ldap_service.py
  - backend/permission_vocabulary.py
  - backend/rbac_defaults.py
  - backend/rbac_service.py
  - backend/role_assignment.py
  - backend/role_contents.py
  - backend/role_endpoints.py
  - backend/role_visibility.py
  - backend/saml_mapping.py
  - backend/sso_endpoints.py
  - backend/tenant_features.py
  - backend/tests/test_closure_delivery.py
  - backend/tests/test_custom_role_assignment.py
  - backend/tests/test_custom_role_mfa.py
  - backend/tests/test_effective_permissions.py
  - backend/tests/test_login_me_permissions.py
  - backend/tests/test_role_literal_guard.py
  - backend/tests/test_role_routes_real_app.py
  - backend/tests/test_role_tenant_isolation.py
  - backend/tests/test_role_visibility.py
  - backend/tests/test_role_write_api.py
  - backend/tests/test_roles_endpoint.py
  - backend/tests/test_tenant_feature_switches.py
  - backend/user_endpoints.py
  - components/Dashboard.tsx
  - components/NoAccessPanel.tsx
  - components/NotificationCenter.tsx
  - components/RoleDeleteRefusalModal.tsx
  - components/RoleEditorModal.tsx
  - components/RoleVisibilityPanel.tsx
  - components/SettingsDashboard.tsx
  - components/SettingsRolesTab.tsx
  - components/Sidebar.tsx
  - components/ZeroAccessScreen.tsx
  - services/apiService.ts
  - services/roleApi.ts
  - src/__tests__/HiddenWidgets.test.tsx
  - src/__tests__/NoAccessScreens.test.tsx
  - src/__tests__/RoleDeleteFlow.test.tsx
  - src/__tests__/RoleEditorModal.test.tsx
  - src/__tests__/RoleVisibilityPanel.test.tsx
  - src/__tests__/SettingsRolesTab.test.tsx
  - src/__tests__/SidebarFailClosed.test.tsx
  - src/__tests__/SidebarTenantSwitches.test.tsx
  - src/__tests__/catalogueAccess.test.ts
  - src/__tests__/permissionRefresh.test.ts
  - src/__tests__/rolePermissions.test.ts
  - src/__tests__/viewAccess.test.ts
  - utils/permissionRefresh.ts
  - utils/permissions.ts
  - utils/rolePermissions.ts
  - utils/viewAccess.ts
findings:
  critical: 0
  warning: 8
  info: 7
  total: 15
status: issues_found
---

# Phase 77: Code Review Report

**Reviewed:** 2026-10-19
**Depth:** standard
**Files Reviewed:** 56
**Status:** issues_found

## Summary

Reviewed the committed HEAD content of the listed files. For the large files (App.tsx, apiService.ts, SettingsDashboard.tsx, Dashboard.tsx) the review was driven by `git diff e2911f81 HEAD` plus the surrounding code. Test files were skimmed for reliability only.

The access-control core is sound. I traced these paths and found no fail-open and no cross-tenant leak:

- Every role document read or write goes through an explicit `tenantId`, and `resolve_target_tenant` is the only source of that id. A non-super caller can never name another tenant, and sentinel tenants are refused.
- `/api/roles/{id}` PUT, DELETE and `/visibility` can only see the resolved tenant's custom documents. Built-in ids answer 404 or take the built-in branch.
- The editor ceiling checks the symmetric difference against the caller's closure and fails closed with 503 on a store error.
- Assignment resolves the stored name against the destination tenant first (`resolve_assignable_role`), then applies `assert_can_assign_role`. LDAP/SAML mapping writes re-validate in the mapper, and a global mapping (no tenant) refuses custom roles.
- Role-name validation folds every built-in spelling through the same `normalize_role` that `is_super_admin` uses. I checked the literal super-admin sets in `auth_roles.py`, `change_management_endpoints.py` and others. Every spelling in them normalizes to a refused built-in key, so no custom name can satisfy a literal comparison.
- `deliverable_closure` is applied before `narrow`. I computed the vocabulary against the switch catalogue: no derived `view:X` or `request:X` survives an off `manage:X` switch today (empty leak set).
- `get_current_user` is JWT-only, so the role write routes are not reachable by a scoped API key.

**Incremental re-review (2026-10-19, fix a1f4488d1 for WR-01).** The one-line fix (`currentUserRef.current = next;` before `setCurrentUser(next)` in `refreshPermissions`) is correct for the deterministic stale-read: `loadAllData` has an empty dependency list and reads `currentUserRef.current` synchronously before its first `await`, so it now sees the refreshed list. WR-01 is marked resolved below. The re-review adds one new warning (WR-08, the 30s tick still starts a stale-list load that nothing orders against the refresh-triggered one) and one info item (IN-07, the new source guard test). No other new defects: the ordering with `setAccessChanged`/`lostAccess`, two refreshes, and sign-out were traced and are safe (details under WR-01).

There are no blockers. The seven original warnings are one stale-state bug in the permission refresh, two MFA-cache problems, two server-side robustness gaps in role edit and delete, one hash-routing prototype-key bug, and a Super Admin UI gap for tenant custom roles. The info items are minor.

## Warnings

### WR-01: Permission refresh reloads app data with the OLD permissions

**Status: RESOLVED by a1f4488d1** (confirmed in the 2026-10-19 incremental pass). The residual overlap with the 30s tick that the Fix text below also mentions is tracked separately as WR-08.

**File:** `App.tsx:821-822` (inside `refreshPermissions`); the stale read is at `App.tsx:488` in `loadAllData`
**Issue:** `refreshPermissions` calls `setCurrentUser(next); loadAllData();` back to back. `loadAllData` reads `currentUserRef.current` synchronously at its start (`const user = currentUserRef.current`). The ref is only reassigned during render (line 280), so it still holds the previous user and permission list when `loadAllData` runs. The login, signup and session-restore paths already handle this by setting the ref by hand (lines 612, 658, 751, "loadAllData below runs before the re-render"). The refresh path does not.

Consequences:
- When a refresh GRANTS access, `ifOn(...)` and `canReadView` still use the old list. The newly allowed catalogues are skipped, so the freshly unlocked screen shows empty data until the next 30s tick.
- When a refresh REMOVES access, the reload still fires requests the role can no longer make. Each 403 calls `notifyPermissionDenied`, which opens another refresh window.
- The 30s tick at line 846 runs `loadAllData(); refreshPermissions();` concurrently, so `loadAllData` also races the refresh there.

**Fix:**
```ts
const next: User = { ...prev, permissions: fresh };
currentUserRef.current = next;   // loadAllData below runs before the re-render
if (lostAccess(currentViewRef.current, prev, next)) setAccessChanged(true);
setCurrentUser(next);
loadAllData();
```
Do the same in the 30s tick: `refreshPermissions().then(() => loadAllData())`, or let the 'changed' branch do the reload only.

**Resolution check (a1f4488d1):** `App.tsx:821` now sets the ref before `setCurrentUser(next)` and `loadAllData()`. Verified: (1) `loadAllData` (`App.tsx:473`, `useCallback(..., [])`) runs synchronously up to `const user = currentUserRef.current` (line 488) with no `await` before it, so the new value is what it reads. (2) The render-time `currentUserRef.current = currentUser` (line 280) later writes the same `next` object, so there is no revert; `setAccessChanged` and `setCurrentUser` are batched into one render. (3) `lostAccess` takes `prev`/`next` as arguments, so assigning the ref after it changes nothing. (4) Two refreshes cannot interleave: `refreshInFlight` is shared and cleared in `finally`, and `prev` is re-read after the await. (5) Sign-out: `setCurrentUser(null)` then a full page reload, so a refresh finishing in between is bounded by the reload. The fix mirrors the sign-in paths at lines 612, 658 and 751. Not fixed by this commit: the 30s tick overlap (WR-08).

### WR-02: Sync `mfa_required_for` fails closed for every non-admin custom role (WebSocket rejects)

**File:** `backend/authentication_service.py:104-114`, called from `verify_token` at `:328`; consumers `backend/websocket_manager.py:178` and `:225`
**Issue:** The synchronous `mfa_required_for` returns `not builtin` when no fresh cache entry exists. For a custom role that means True, so MFA is "required" even if the role holds no admin-tier permission. `verify_token` (the WebSocket path) then raises `_enforce_admin_mfa` 403 for any token without `mfa_verified`, which is every non-admin custom-role user because they never do MFA. The WebSocket `connect` handler catches the exception and returns False, so the socket is refused.

The cache is filled only by the async path (`resolve_mfa_required`) on the same worker within the last 60 seconds. A custom-role user whose last HTTP request on that worker was more than 60 seconds ago, or who lands on another worker, gets realtime notifications, chat and support push refused intermittently. The mirror case also exists: a built-in role such as `analyst` that has a legacy tenant document adding `manage:users` returns False on a cold cache, so that role is not asked for MFA on the WebSocket.

**Fix:** The sync path cannot read the role store. Either:
- make the WebSocket handler await `verify_token_async` (it already runs in an async context), or
- have the sync variant skip MFA enforcement for roles it cannot decide and rely on the HTTP gate, or
- warm the cache at login and refresh it when an entry is read after expiry (stale-while-revalidate).

### WR-03: MFA role cache is never invalidated; the 60s promotion window is per worker, and the helper is dead code

**File:** `backend/authentication_service.py:70-81, 117-136`; `backend/role_endpoints.py:248, 276`
**Issue:** The comment says a role edit is "enforced within a minute", but `_clear_mfa_role_cache` is called only from tests. After an editor adds `manage:users`, `manage:rbac` or another admin-tier permission to a custom role, any worker that cached `False` keeps letting non-MFA sessions of that role use it for up to 60 seconds. Workers are separate processes, so clearing in the editing worker would not reach the others either. This is a bounded window, but it is the one place where the edit-to-enforcement guarantee (ACC-08, D-14) is weaker than stated. Separately, `resolve_mfa_required` returns `not builtin` on a store error, so a built-in role with a tenant override document fails open (False) while the store is down.

**Fix:**
- Call `_clear_mfa_role_cache()` from `create_role`, `update_role` and `delete_role` for the local worker.
- Make the TTL shorter, or store a tenant-level `rolesVersion` and key the cache on it.
- Fix the docstring to say the guarantee is "within 60s on other workers".
- On a store error, return True for any role that could carry an override document, or at least log at error level.

### WR-04: A role holding any now-unknown or banned permission string can never be edited

**File:** `backend/role_endpoints.py:241-243` (`update_role` validation); `components/RoleEditorModal.tsx:123` (re-submit of locked rows)
**Issue:** `update_role` runs `role_contents.validate_permissions(body.permissions)` over the entire submitted list. `validate_permissions` rejects anything outside `GRANTABLE_PERMISSIONS`. The editor deliberately keeps "locked" permissions (the role's permissions not in the caller's catalogue) and re-submits them. For a role document that already contains a string that is no longer grantable (an unknown or retired permission, or a banned one like `manage:tenants` that `effective_permissions` ignores anyway), every save fails with 400 "These permissions cannot be granted by a custom role: ...". The locked checkbox cannot be unticked, so the role is stuck until it is deleted. The ceiling check already uses the symmetric difference, so only the added strings need the grantable check.

**Fix:** Validate only the newly added permissions for grantability, and carry retained ones through unchanged:
```python
added = set(body.permissions) - set(old_permissions)
role_contents.validate_permissions(added)          # 400 only for strings being introduced
permissions = sorted(set(body.permissions))        # retained legacy strings stay
```
Optionally drop non-grantable strings that are already on the role when the editor saves (explicit "cleanup").

### WR-05: `role_usage` caps the holder and mapping scan at 5000, so a role in use can be deleted

**File:** `backend/role_contents.py:174, 180`; `backend/role_endpoints.py:270-276`
**Issue:** `users.find(...).to_list(5000)` and `...mappings.to_list(5000)` silently truncate. In a tenant with more than 5000 users, or more than 5000 mappings, holders beyond the cap are invisible, so `holder_count` can be 0 for a role that is still assigned. `delete_role` then removes the document and those users end up with a role that resolves to `[]`, which is the "nobody silently loses access" outcome PROH-77-04 forbids. The check-then-delete is also not atomic: a user assigned between `role_usage` and `delete_one` is stranded.

**Fix:** Count with a query instead of loading documents, for example `count_documents({"tenantId": t, "role": {"$regex": ..., "$options": "i"}})` or filter on a stored normalized key. Cap only the listed rows. If a hard scan limit stays, refuse the delete (409 or 503) when the cap is reached.

### WR-06: `resolveHashView` returns inherited `Object.prototype` members for `#constructor` and `#__proto__`

**File:** `utils/viewAccess.ts:94-98` (`HASH_ALIASES[wanted] ?? viewForHash(wanted)`); consumers `App.tsx:437` and `App.tsx:1056`
**Issue:** `HASH_ALIASES` is a plain object literal, so `HASH_ALIASES['constructor']` (the `Object` function) and `HASH_ALIASES['__proto__']` (`Object.prototype`) are truthy and are returned as an "AppView". `App` passes that to `setCurrentView` (a function value is treated by React as an updater). The landing effect uses `resolveHashView(...) ?? landingView(...)`, so for a link like `https://host/#constructor` it never falls back to the real landing view. The user lands on an unmapped-view panel labelled "function Object() { [native code] }" or "[object Object]". It fails closed, but a crafted link breaks landing for the signed-in user.

**Fix:**
```ts
const HASH_ALIASES = new Map<string, AppView>(Object.entries({ ... }) as [string, AppView][]);
...
return HASH_ALIASES.get(wanted) ?? viewForHash(wanted);
```
or `Object.hasOwn(HASH_ALIASES, wanted) ? HASH_ALIASES[wanted] : viewForHash(wanted)`.

### WR-07: A Super Admin cannot pick a tenant's custom roles when creating or editing a user

**File:** `App.tsx:491` (`ifOn('roleManagement', api.fetchRoles)`), `services/apiService.ts:770-772` (`fetchRoles` takes no tenant), `components/SettingsDashboard.tsx:245-248` and `components/AddUserModal.tsx:19-22`
**Issue:** The App-level role list is fetched without `?tenantId=`. For a Super Admin the server returns the built-in roles only (D-17). The Roles tab fetches the tenant list itself, but `availableRolesForAssignment`, which feeds the Add/Edit User modals, comes from the App list. As a result a Super Admin creating a user in tenant X cannot choose X's custom roles in the UI, although the API supports it (`resolve_assignable_role` with the destination tenant). When the Super Admin edits a user who already holds a custom role, that role is missing from the dropdown, so the form may show a blank or the wrong value.

**Fix:** Have the user modals fetch `fetchRoles(selectedTenantId)` (the roleApi helper already supports it) when the caller is a Super Admin. Or make `handleSaveRole`/the viewing-tenant change refetch with the viewed tenant.

### WR-08: Overlapping `loadAllData` runs have no ordering; the 30s tick still loads with the stale list and can overwrite the refreshed load

**File:** `App.tsx:847` (`const refresh = () => { loadAllData(); refreshPermissions(); };`) and `App.tsx:473-575` (`loadAllData` setters)
**Issue:** a1f4488d1 fixes the refresh-triggered load, but the tick and the `visibilitychange` handler call `loadAllData()` first, with the pre-change list, and then `refreshPermissions()`. When the refresh reports a change, it starts a second `loadAllData()` with the new list while the first is still in flight (each is about 45 requests). Neither run is guarded by a sequence token and each one calls about 45 setters at the end, so whichever finishes last wins. If the stale run finishes last:
- on a GRANT it writes `[]`/`null` fallbacks over the newly loaded catalogues (the stale run SKIPPED them), so the unlocked screen is empty until the next 30s tick, which is the WR-01 symptom for the tick path;
- on a REMOVAL it restores data for catalogues the role can no longer read (still gated by `ViewGate`, but kept in state).
The order is not deterministic, so this is intermittent. Focus and 403-triggered refreshes call `refreshPermissions()` alone and are not affected.
**Fix:** Add a last-writer-wins guard in `loadAllData`:
```ts
const loadSeq = useRef(0);
// in loadAllData, after the token check:
const seq = ++loadSeq.current;
// after Promise.allSettled and before the setters:
if (seq !== loadSeq.current) return;   // a newer load superseded this one
```
or change the tick to `const refresh = () => { void refreshPermissions().then(r => { if (r !== 'changed') loadAllData(); }); };` so exactly one load runs per tick.

## Info

### IN-01: Role names that differ only by repeated whitespace render like a built-in role

**File:** `backend/role_contents.py:39, 62-85`
**Issue:** `NAME_PATTERN` allows consecutive spaces, but `normalize_role` maps each space to one `_`. A custom role named `Tenant  Admin` (two spaces) normalizes to `tenant__admin`, which is not a built-in key, so it is accepted. HTML collapses the whitespace, so it looks identical to the built-in `Tenant Admin` in lists and user rows. It carries no privilege (every authorization check uses the normalized key), but it defeats the D-18 goal that a custom role never impersonates a built-in. The same holds for `Super  Admin`.
**Fix:** Reject runs of whitespace or separators in `NAME_PATTERN`, or collapse them before both the pattern check and `normalize_role`.

### IN-02: No unique index backs the role-name uniqueness rule

**File:** `backend/role_endpoints.py:199-204`
**Issue:** Uniqueness relies on a pre-check plus a read-after-write. Two concurrent creates of the same name both insert, both see two documents, and both delete their own copy, so both callers get 409 and neither role exists. It is safe but surprising. The docs already store `nameKey`.
**Fix:** Add a migration with a unique index on `(tenantId, nameKey)` (partial on documents that have `nameKey`) and map `DuplicateKeyError` to 409.

### IN-03: `isEditable` is ignored by PUT and DELETE

**File:** `backend/role_endpoints.py:213-223, 226-283`
**Issue:** `custom_role_docs` returns any non-built-in-named document, including a legacy one with `isEditable: false`, and `update_role` and `delete_role` modify it. The list endpoint reports `isEditable` to the UI, but the server does not enforce it.
**Fix:** In `_load_custom_role`, 403 when `doc.get("isEditable") is False`.

### IN-04: A role change is committed even if its audit entry cannot be written

**File:** `backend/role_endpoints.py:79-89, 209, 254, 281`
**Issue:** `_audit_role` logs and swallows failures (documented as T-77-11). For a hash-chained audit ledger, permission grants, edits and deletes can therefore take effect with no ledger entry. This is a design choice, but it is a security-relevant gap worth a conscious decision, for example fail the write (503) for `role.created` and `role.updated` when the audit service is down.
**Fix:** Either keep the trade-off and add an error-level alert, or write the audit entry first and refuse the change when it fails.

### IN-05: Smaller correctness and consistency points

**Files:** `services/roleApi.ts:78-82`, `backend/user_endpoints.py:280-288`, `components/ZeroAccessScreen.tsx:36-39`, `App.tsx:812-824`
- `fetchPermissionCatalogue(tenantId)` appends `?tenantId=` but `GET /api/roles/permission-catalogue` has no such parameter. The parameter is silently ignored, so the catalogue is the editor's own closure. Either drop the argument or accept and validate it.
- In `create_user`, `resolve_assignable_role` runs before the tenant-exists check, so a Super Admin naming an unknown tenant with a custom role gets "Invalid role '...'" instead of "Tenant ... does not exist". Check the tenant first.
- `ZeroAccessScreen` sets `mounted.current = false` in the effect cleanup but never sets it back to true. Under `React.StrictMode` in development (index.tsx:28) the simulated unmount leaves it false, so after Retry the status never updates and the button stays on "Checking...". Add `mounted.current = true;` at the start of the effect.
- `refreshPermissions` starts the `/api/auth/me` request before checking `currentUserRef.current`. On the login page every window focus sends a pointless request. Return `'error'` early when there is no user.

### IN-06: Test coverage relies on source-text matching

**Files:** `src/__tests__/catalogueAccess.test.ts` (new "App.tsx fails closed" and "super-admin recognised only through the shared helpers" blocks)
**Issue:** These tests read `App.tsx` and other sources as strings and assert regexes (for example `/<ViewGate[^>]*render=\{renderView\}/`). They pass or fail on formatting changes (a line break inside the JSX, a rename) rather than behaviour. They document intent but will produce false failures and cannot prove the gate works. Behavioural coverage (render `App` with a denied view) would be more reliable. The other new tests are behavioural.
**Fix:** Keep them as drift guards but back the same assertions with one rendered test of `ViewGate` and the `default:` branch.

### IN-07: The WR-01 source guard test is order-in-text only and brittle

**File:** `src/__tests__/catalogueAccess.test.ts:201-211`
**Issue:** The new test slices `App.tsx` from `const refreshPermissions = useCallback(` to the first `}, [loadAllData]);` and checks that `currentUserRef.current = next;` appears before the first `loadAllData();`. It passes as written (44 of 44 pass), but:
- it can pass vacuously: the substring match also succeeds if the assignment sits in a comment, an unreachable branch or a different branch than the one that reaches `loadAllData()`;
- it fails on harmless edits: a changed dependency array (then the slice runs to `slice(start, -1)`, nearly the end of the file), `void loadAllData()` is fine but `loadAllData().then(...)` yields `indexOf` -1 and a false failure, or a renamed local `next`;
- the `expect(start)` assertion runs after the slice is built, so a missing start gives a confusing failure message (the test still fails correctly);
- it does not cover the tick path (WR-08) or any runtime behaviour.
This is the same drift-guard pattern as IN-06.
**Fix:** Assert `start` and the end index before slicing, and back it with one behavioural test (render `App` with mocked `api`, make `fetchCurrentPermissions` return a wider list, and assert `fetchAssets` or similar is called after the refresh).

---

_Reviewed: 2026-10-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Incremental re-review: 2026-10-19 (a1f4488d1, App.tsx and src/__tests__/catalogueAccess.test.ts)_
