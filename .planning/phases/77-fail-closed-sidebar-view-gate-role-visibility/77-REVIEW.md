---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
reviewed: 2026-10-19T00:00:00Z
reviewed_incremental: 2026-10-19
incremental_files:
  - App.tsx
  - src/__tests__/catalogueAccess.test.ts
  - utils/permissionRefresh.ts
  - src/__tests__/permissionRefresh.test.ts
  - services/apiService.ts
  - backend/authentication_service.py
  - backend/role_endpoints.py
  - backend/websocket_manager.py
  - backend/tests/test_custom_role_mfa.py
  - backend/tests/test_role_write_api.py
  - backend/tests/test_websocket_connect_rate_limit.py
incremental_scope: fix commit a1f4488d1 (WR-01); fix commit b76b8af8d (WR-08), second incremental pass 2026-10-19; fix commit 41fb29db5 (WR-09), third incremental pass 2026-10-19; fix commits 3bb575186 (WR-10) and bee9299ce (WR-02, WR-03), fourth incremental pass 2026-10-19
depth: standard
files_reviewed: 58
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
  - backend/tests/test_websocket_connect_rate_limit.py
  - backend/user_endpoints.py
  - backend/websocket_manager.py
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
  warning: 11
  info: 12
  total: 23
status: issues_found
---

# Phase 77: Code Review Report

**Reviewed:** 2026-10-19
**Depth:** standard
**Files Reviewed:** 58
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

**Second incremental re-review (2026-10-19, fix b76b8af8d for WR-08, diff base 7ab88bd43).** The new `refreshThenLoad(refresh, load)` helper in `utils/permissionRefresh.ts` and its one call site (`App.tsx:847`) remove the stale-list load from the 30s tick and the `visibilitychange` handler, so WR-08 is marked resolved below. Traced: `refreshPermissions` cannot reject today (`api.fetchCurrentPermissions` swallows every error; the body after the await only reads refs and calls pure helpers), a shared in-flight promise from a focus or 403 refresh gives the tick the same result so exactly one load runs, and the signed-out case (`prev` null gives `'error'`, then `load()` runs and `loadAllData` returns at its token check) behaves as before the change, so it is not a regression. The review adds one warning (WR-09, the data load is now chained to an `/auth/me` request that has no timeout and no rejection handling) and one info item (IN-08, the explicit reload in `refreshPermissions` duplicates the one the Initial Data Load effect already makes).

**Third incremental re-review (2026-10-19, fix 41fb29db5 for WR-09, diff base 745fcfd47).** `fetchCurrentPermissions` now aborts through an `AbortController` after `PERMISSIONS_TIMEOUT_MS` (10 s) and clears the timer in `finally`, and `refreshThenLoad` treats a rejecting refresh as `'error'`. Both halves of the WR-09 Fix text are applied, and the two new tests pass (14 of 14 in `permissionRefresh.test.ts`, run at HEAD). WR-09 is marked resolved below for the failure it described (a stalled `/auth/me`). Traced and found sound: `authFetch` forwards the signal (it passes the `instanceof AbortSignal` guard and is spread into both the first request and the 401 retry); the abort surfaces as a rejection that `fetchCurrentPermissions` maps to `null`, so `refreshPermissions` returns `'error'` and `load()` runs with the kept list; nothing reads an aborted `/auth/me` as "backend offline" (`setIsBackendConnected(false)` is only set from `loadAllData`'s own critical-endpoint failures and the health poll, and `fetchCurrentPermissions` has the single caller `App.tsx:815`); the timer is cleared on every path; 10 s is shorter than the 30 s tick (so a timed-out read cannot overlap the next tick) and the 403 refresh is shared through `refreshInFlight`, so it adds no second request; the new test block restores real timers, unstubs `fetch` and clears `sessionStorage` in `afterEach`, so nothing leaks. The pass adds one warning (WR-10, the signal reaches the 401 retry inside a `try` whose `catch` signs the user out) and one info item (IN-09, the timeout does not bound the token-refresh wait and the test does not cover the 401 path).

**Fourth incremental re-review (2026-10-19, fixes 3bb575186 for WR-10 and bee9299ce for WR-02 and WR-03, diff base a44984c4d).** All three are marked resolved below for the failures they described. Re-run at HEAD: `test_custom_role_mfa.py`, `test_role_write_api.py` and `test_websocket_connect_rate_limit.py` pass (94 of 94) and `permissionRefresh.test.ts` passes (15 of 15). Traced and found sound: `verify_token_async` is a superset of the sync check for sockets (same refresh-token, agent, missing-`sub` and missing-`tenant_id` rejections, same `allow_agent=True` default, same `_set_tenant_id`), so nothing the sync path rejected is now accepted; `token_data` is always bound where the support-chat block reads it (any failure of the `try` returns False first); the sync `verify_token` and `mfa_required_for` now have no production caller, and the one remaining `mfa_action_for` call without `required` (signup, built-in "Tenant Admin") is correct by table; `fetchCurrentPermissions` cannot apply a late result because only the race value reaches `refreshPermissions` and the dangling read swallows its own errors and never touches app state; the new `ws` test fixture restores `sio.emit` through `monkeypatch` and removes its sids, user entries and rate-limit buckets. The pass adds one warning (WR-11, the root cause behind WR-10 is still live for four other `authFetch` callers that pass an `AbortSignal`) and three info items (IN-10 the abandoned `/auth/me` request is never cancelled, IN-11 the sync token path is now dead code with a stale docstring, IN-12 the cache invalidation is not in a `finally` and can be undone by an in-flight lookup).

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

**Status: RESOLVED by bee9299ce** (confirmed in the fourth 2026-10-19 incremental pass; see the resolution check at the end of this section).

**File:** `backend/authentication_service.py:104-114`, called from `verify_token` at `:328`; consumers `backend/websocket_manager.py:178` and `:225`
**Issue:** The synchronous `mfa_required_for` returns `not builtin` when no fresh cache entry exists. For a custom role that means True, so MFA is "required" even if the role holds no admin-tier permission. `verify_token` (the WebSocket path) then raises `_enforce_admin_mfa` 403 for any token without `mfa_verified`, which is every non-admin custom-role user because they never do MFA. The WebSocket `connect` handler catches the exception and returns False, so the socket is refused.

The cache is filled only by the async path (`resolve_mfa_required`) on the same worker within the last 60 seconds. A custom-role user whose last HTTP request on that worker was more than 60 seconds ago, or who lands on another worker, gets realtime notifications, chat and support push refused intermittently. The mirror case also exists: a built-in role such as `analyst` that has a legacy tenant document adding `manage:users` returns False on a cold cache, so that role is not asked for MFA on the WebSocket.

**Fix:** The sync path cannot read the role store. Either:
- make the WebSocket handler await `verify_token_async` (it already runs in an async context), or
- have the sync variant skip MFA enforcement for roles it cannot decide and rely on the HTTP gate, or
- warm the cache at login and refresh it when an entry is read after expiry (stale-while-revalidate).

**Resolution check (bee9299ce):** `websocket_manager.connect` (`backend/websocket_manager.py:176-186`) now awaits `verify_token_async` once, the first option of the Fix text, so the socket asks `resolve_mfa_required` (role store on a cold cache) exactly like every HTTP route. Verified: (1) the async check carries every rejection the sync one had (refresh token as access token, agent gate, missing `sub`, missing `tenant_id`, JTI and user-cutoff caches, `_enforce_admin_mfa`) and `allow_agent` defaults to True in both, so agent sockets behave as before and nothing newly passes; (2) it adds the DB revocation lookup and the 60 s bulk sync that HTTP already runs, with the same fail-open on a DB error, so a revoked token is refused on a socket where the sync path only saw the in-process cache (an improvement, and a DB error is no worse than before); the bulk-sync timestamp is set before the scan, so a connect burst does not repeat it, and the per-IP rate limit still runs before any of this (the updated test asserts `verify_token_async` is not awaited once limited); (3) `token_data` is bound on every path that reaches the support-chat block (a failure inside the `try`, including the missing-tenant return, exits first), and the old second decode with its swallowed `except` is gone; (4) the tests cover a non-admin custom role connecting on a cold cache, an admin-tier custom role refused, and an extended built-in refused. The negative assertions only check `is False`, which would also hold for an unrelated rejection, but the same fixture connects `Helpdesk`, so the setup is sound. No remaining sync production caller of `verify_token` or `mfa_required_for` (see IN-11).

### WR-03: MFA role cache is never invalidated; the 60s promotion window is per worker, and the helper is dead code

**Status: RESOLVED by bee9299ce** (confirmed in the fourth 2026-10-19 incremental pass; see the resolution check at the end of this section). Two small residuals are tracked as IN-12.

**File:** `backend/authentication_service.py:70-81, 117-136`; `backend/role_endpoints.py:248, 276`
**Issue:** The comment says a role edit is "enforced within a minute", but `_clear_mfa_role_cache` is called only from tests. After an editor adds `manage:users`, `manage:rbac` or another admin-tier permission to a custom role, any worker that cached `False` keeps letting non-MFA sessions of that role use it for up to 60 seconds. Workers are separate processes, so clearing in the editing worker would not reach the others either. This is a bounded window, but it is the one place where the edit-to-enforcement guarantee (ACC-08, D-14) is weaker than stated. Separately, `resolve_mfa_required` returns `not builtin` on a store error, so a built-in role with a tenant override document fails open (False) while the store is down.

**Fix:**
- Call `_clear_mfa_role_cache()` from `create_role`, `update_role` and `delete_role` for the local worker.
- Make the TTL shorter, or store a tenant-level `rolesVersion` and key the cache on it.
- Fix the docstring to say the guarantee is "within 60s on other workers".
- On a store error, return True for any role that could carry an override document, or at least log at error level.

**Resolution check (bee9299ce):** `authentication_service.invalidate_mfa_role_cache(tenant_id)` drops every entry whose key tenant matches, and `create_role`, `update_role` and `delete_role` call it right after the DB write (`backend/role_endpoints.py:205, 250, 279`), before the audit write, so an audit failure cannot skip it. Verified: (1) the cache key tenant (`token.tenant_id`) equals the resolved target tenant the endpoints pass, including a Super Admin editing a named tenant; (2) no other code writes the `roles` collection at runtime (`app_startup.py` seeding runs at boot with a cold cache); (3) the comment and docstring now state the guarantee honestly (next request on the editing worker, within 60 s on other workers); (4) `resolve_mfa_required` logs at error level on a store failure and returns `(not builtin) or last-known True`, so an extended built-in no longer drops to the table's False while the store is down if a True was seen, and a custom name still fails closed; the error answer is not cached. What remains is a design limit rather than a defect: with a cold cache and a down store, a built-in name with an override document still answers by table (False), and the other workers still wait out the TTL. Both are documented in the code. See IN-12 for the invalidation placement and an in-flight-lookup race. The three new tests pass and assert tenant scoping, the PUT and DELETE paths, and the strict fallback.

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

**Status: RESOLVED by b76b8af8d** (confirmed in the second 2026-10-19 incremental pass; see the resolution check at the end of this section). The overlap of other `loadAllData` callers is noted there; the chaining of the tick to `/auth/me` is tracked as WR-09.

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

**Resolution check (b76b8af8d):** `App.tsx:847` is now `void refreshThenLoad(refreshPermissions, loadAllData)`, the second option of the Fix text. Verified: (1) the tick and the `visibilitychange` handler no longer start a load beside the refresh, so no load runs with the pre-change list while the refresh-triggered one runs with the new list. On `'changed'` the refresh's own `loadAllData()` (with the ref already set, WR-01) is the only load; on `'same'` or `'error'` one load runs with the kept list. (2) A focus or 403 refresh in flight is shared (`refreshInFlight`), so a tick that joins it gets the same result and does not add a second load after `'changed'`. (3) Three behavioural tests cover ordering, the `'changed'` skip and the `'error'` load; they are sound (`refresh()` is invoked synchronously, so `settle` is assigned before it is called). Residual, not a regression and not worth keeping WR-08 open: a load that is already in flight when a refresh changes the list (a previous tick's load that took over 30 s, the reconnect load at `App.tsx:789`, the Initial Data Load effect) is still unordered against the new load, because `loadAllData` has no sequence token. That window is much narrower than the one this finding described.

### WR-09: The periodic data load now waits on an `/auth/me` request that has no timeout and no rejection handling

**Status: RESOLVED by 41fb29db5** (confirmed in the third 2026-10-19 incremental pass; see the resolution check at the end of this section). Two follow-ups are tracked separately: WR-10 (a new misfire the signal introduces in `authFetch`) and IN-09 (the timeout does not bound the token-refresh wait).

**File:** `utils/permissionRefresh.ts:65-67` (`refreshThenLoad`); dependency `services/apiService.ts:755-764` (`fetchCurrentPermissions` over `authFetch`, line 269) and the shared promise `App.tsx:808-829` (`refreshInFlight`)
**Issue:** Before b76b8af8d the tick called `loadAllData()` unconditionally and independently of `refreshPermissions()`. `refreshThenLoad` makes the load conditional on the refresh settling, so the data refresh now inherits the refresh's failure modes:
- `authFetch` and `fetchCurrentPermissions` set no timeout or `AbortSignal`. If the `/auth/me` request stalls (half-open connection, a proxy that holds the request), the promise never settles and `refreshInFlight.current` is never cleared (it is cleared only in `finally`). Every later tick, visibility change, focus and 403 refresh then returns that same pending promise, so `load()` is never called again and the 30s data refresh stops until the page is reloaded. A stalled `/auth/me` with otherwise healthy endpoints used to cost only the permission refresh; it now also freezes all data.
- `await refresh()` has no `try/catch`. Today `refreshPermissions` cannot reject, but if any future change in its body (or in `lostAccess`/`evaluateViewAccess`) throws, `refreshThenLoad` rejects, `load()` is skipped and the caller's `void` leaves an unhandled rejection. The helper's contract ("load unless the refresh reloaded") should not depend on the refresh never throwing.
- The tests cover `'same'`, `'changed'` and `'error'` but not a rejecting or never-settling refresh.
**Fix:**
```ts
export async function refreshThenLoad(refresh: () => Promise<RefreshResult>, load: () => void): Promise<void> {
  let result: RefreshResult = 'error';
  try { result = await refresh(); } catch { /* keep the last list; still refresh data */ }
  if (result !== 'changed') load();
}
```
and bound the permission request, for example `authFetch(\`${API_BASE}/auth/me\`, { signal: AbortSignal.timeout(10000) })` inside `fetchCurrentPermissions` (its `catch` already maps the abort to `null`, which becomes `'error'`). Add a test with a rejecting refresh.

**Resolution check (41fb29db5):** Verified at HEAD. (1) `fetchCurrentPermissions` (`services/apiService.ts:758-771`) creates the controller and timer before the `try`, passes `{ signal }` to `authFetch`, and clears the timer in `finally`, so there is no timer leak on success, failure or abort. (2) `authFetch` (line 269) keeps the signal (`rawSignal instanceof AbortSignal`) and forwards it to every `makeRequest`, so a stalled `/auth/me` is aborted; the rejection hits the `catch` and returns `null`, which `refreshPermissions` maps to `'error'`, clears `refreshInFlight` in its `.finally`, and `refreshThenLoad` then calls `load()`. A stalled `/auth/me` therefore costs at most 10 s of delay on one tick instead of freezing the data refresh. (3) `refreshThenLoad` wraps `await refresh()` in `try/catch`, so a rejecting refresh still loads and the returned promise settles; the `void` caller can no longer produce an unhandled rejection. (4) 10 s is below the 30 s tick, so a timed-out read cannot overlap the next tick, and the 15 s 403 window is only an event debounce (the read it triggers is shared through `refreshInFlight`), so the two do not interact. (5) An abort is never reported as a lost backend: `setIsBackendConnected(false)` is set only by `loadAllData`'s critical-endpoint failures (`App.tsx:582`) and the health poll, neither of which calls this function. (6) The two new tests pass and clean up after themselves (`afterEach` restores real timers, unstubs the global `fetch` and clears `sessionStorage`). Not covered by this fix: the abort does not reach the token-refresh request (IN-09), and the signal changes what the 401-retry `catch` in `authFetch` does (WR-10).

### WR-10: An aborted `/auth/me` retry after a 401 token refresh signs the user out

**Status: RESOLVED by 3bb575186** for `fetchCurrentPermissions` (confirmed in the fourth 2026-10-19 incremental pass; see the resolution check at the end of this section). The commit removed the signal from this caller instead of changing `authFetch`, so the same misfire is still reachable from other callers: see WR-11.

**File:** `services/apiService.ts:305-317` (the 401 branch of `authFetch`), reached through `fetchCurrentPermissions` at `services/apiService.ts:758-771`
**Issue:** The 401 branch is `try { const newToken = await refreshAccessToken(); response = await makeRequest(newToken); } catch { _expireSession(); throw new Error('Session expired'); }`. The retry `makeRequest` carries the caller's signal, and the `catch` treats every failure of either step the same way. Before 41fb29db5 `fetchCurrentPermissions` passed no signal, so only a genuine refresh failure could reach that `catch`. Now the 10 s timer also starts the clock for the proactive refresh and the 401 refresh, and an abort during or before the retry lands in the `catch`:
- the 10 s budget is spent while `refreshAccessToken` runs (it is shared and has no timeout of its own); if it ends after the timer fired, `fetch(url, { signal })` with an already-aborted signal rejects at once with `AbortError`;
- or the retry itself stalls past the remaining budget.
Either way `_expireSession()` runs: it sets `_sessionEnding`, removes `token` and `refresh_token`, clears the caches and redirects to `/login` after 50 ms. A valid session with a good, freshly refreshed token is ended by a slow backend. It needs a 401 on `/auth/me` (a token revoked server-side, or one that expired while the proactive refresh was in backoff) plus slowness of about 10 s, so it is uncommon, but the result is a forced sign-out on a path that runs every 30 s. The cleared `refresh_token` and `_sessionEnding = true` also make every in-flight request fail with "Session ended" until the redirect. Any other caller that passes a signal into `authFetch` (existing ones included) has the same exposure.
**Fix:** Separate the refresh from the retry, so only a refresh failure ends the session, and let an abort pass through untouched:
```ts
let newToken: string;
try {
    newToken = await refreshAccessToken();
} catch {
    _expireSession();
    throw new Error('Session expired');
}
response = await makeRequest(newToken);   // an AbortError or network error here must not end the session
```
(If a retry that still answers 401 should end the session, handle it by status after the retry, not by exception.) Add a test: stub `fetch` so the first `/auth/me` returns 401, `/auth/refresh` returns a token, and the retry rejects with `AbortError`; assert `fetchCurrentPermissions()` resolves `null` and `window.location.href` is unchanged and the token is still in `sessionStorage`.

**Resolution check (3bb575186):** `fetchCurrentPermissions` (`services/apiService.ts:758-779`) no longer passes a signal; it races the read against a `PERMISSIONS_TIMEOUT_MS` timer that resolves `null` and clears the timer in `finally`. Verified: (1) with no signal, an abort can no longer reach `authFetch`'s retry `catch`, so a slow backend cannot trigger `_expireSession()` from this call; a genuine refresh failure still ends the session, as it should; (2) the race now also bounds the token-refresh wait, which closes the gap IN-09 described for this call; (3) a timed-out read cannot apply a stale answer: only the race value reaches `refreshPermissions` (`App.tsx:815`), the abandoned read has its own `try/catch` (no unhandled rejection) and writes no app state, and a late 403 on `/auth/me` does not raise the permission-denied event (`shouldSignalPermissionDenied` skips `/api/auth/`); (4) `timer` is assigned synchronously in the `Promise` executor, so `clearTimeout` never sees `undefined` after a settled race; (5) the new test reproduces 401, then refresh ok, then a stalled retry, and asserts `null`, two `/auth/me` calls and the refreshed token kept in `sessionStorage` (it passes at HEAD, 15 of 15). It does not assert that `window.location` is untouched, which `sessionStorage` already implies since `_expireSession` removes the token. Trade-off of not aborting: IN-10.

### WR-11: `authFetch` still signs the user out when a caller's `AbortSignal` fires during the post-401 retry

**File:** `services/apiService.ts:311-317` (the 401 branch of `authFetch`); callers that pass a signal: `components/RemoteAccessDashboard.tsx:31, 45`, `components/SoftwareDeployment.tsx:117, 127`, `components/ComplianceFrameworksDashboard.tsx:137, 157`
**Issue:** 3bb575186 fixed WR-10 by taking the signal away from one caller. The cause is unchanged: `try { newToken = await refreshAccessToken(); response = await makeRequest(newToken); } catch { _expireSession(); throw new Error('Session expired'); }` treats an abort or a network error on the retry like a failed token refresh. These three components abort their requests in an effect cleanup (`controller.abort()`, for example `RemoteAccessDashboard.tsx:62`, `SoftwareDeployment.tsx:46`). The realistic trigger needs no slow backend: the user opens one of those screens with an access token that has just expired (a 401, so a refresh runs), then navigates away or changes the filter while the refresh is in flight. The cleanup aborts, the retry `fetch` rejects at once with `AbortError`, and `_expireSession()` removes `token` and `refresh_token`, sets `_sessionEnding` and redirects to `/login` after 50 ms, ending a valid session that has a good refreshed token. The components already special-case `AbortError` in their own `catch`, which shows they expect an abort to be harmless.
**Fix:** Split the refresh from the retry so only a refresh failure ends the session, and let an abort or network error on the retry propagate to the caller:
```ts
let newToken: string;
try {
    newToken = await refreshAccessToken();
} catch {
    _expireSession();
    throw new Error('Session expired');
}
response = await makeRequest(newToken);   // AbortError / network error here must not end the session
```
Add a test with a caller signal: first answer 401, refresh ok, abort before the retry resolves; assert the call rejects with `AbortError`, the token in `sessionStorage` is the refreshed one and `_sessionEnding` is not set.

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

### IN-08: `refreshPermissions` and the Initial Data Load effect both reload data on a changed list

**File:** `App.tsx:823` (`loadAllData();` in `refreshPermissions`) and `App.tsx:759-770` (effect on `[currentUser, loadAllData]` that calls `loadAllData()` whenever a user exists)
**Issue:** `setCurrentUser(next)` changes `currentUser`, so after the render the Initial Data Load effect runs and calls `loadAllData()` again. A `'changed'` refresh therefore starts two full loads (about 90 requests), both with the new list. This does not reintroduce WR-01 or WR-08 (both loads use the same list, so whichever finishes last writes the same data), but it makes the explicit `loadAllData()` in `refreshPermissions` redundant and means the `refreshThenLoad` comment ("the refresh already reloaded") describes a reload that happens twice. The same effect also reloads on every other `setCurrentUser`, for example the empty-list fallback at `App.tsx:1075`.
**Fix:** Either keep the explicit call (it guarantees the load starts with the ref set) and make the effect depend on the user's identity instead of the whole object (`currentUser?.email`, `currentUser?.tenantId`), or drop the explicit call and rely on the effect. Pick one so a list change costs one load.

### IN-09: The 10 s timeout does not bound the token-refresh wait, and the test does not cover the 401 or near-expiry paths

**Status: PARTLY ADDRESSED by 3bb575186** (fourth 2026-10-19 incremental pass). The new race covers the whole `authFetch` call, so the 10 s limit now includes the token-refresh wait (first fix option) and the new WR-10 test exercises the 401 branch. Still open: no test uses a near-expiry token (the proactive refresh path), and `src/__tests__/permissionRefresh.test.ts:204` still pins the literal `10000` beside the imported constant.

**File:** `services/apiService.ts:157` (`refreshAccessToken` has no signal or timeout; `authFetch` awaits it at `:294` before the first request and at `:312` on a 401); `src/__tests__/permissionRefresh.test.ts:189-212`
**Issue:** The abort only cancels the `/auth/me` request. If the token is within 5 minutes of expiry (or the request gets a 401), `authFetch` first awaits the shared `refreshAccessToken()`, a bare `fetch` with no timeout. If `/auth/refresh` stalls, `fetchCurrentPermissions` still hangs past 10 s, `refreshInFlight` stays set, and the tick-chained load stalls as it did in WR-09. The window is narrow (it recurs only when the refresh endpoint is the stalled one, and then every other `authFetch` caller is blocked on the same promise anyway), so it is not worth reopening WR-09, but the "never longer than 10 s" claim in the constant's comment only holds for the `/auth/me` request. The new test uses the token `'tok'`, for which `jwtSecondsUntilExpiry` returns `Infinity`, so neither the proactive refresh nor the 401 branch is exercised (that is why WR-10 is not caught). The test also pins the literal `10000` in an assertion, which only duplicates the constant.
**Fix:** Either race the whole call (`Promise.race([authFetch(...), timeout])` with the timer settling the result) so the 10 s limit covers the refresh wait too, or give `refreshAccessToken` its own `AbortSignal.timeout`. Add a case with a near-expiry token (`header.eyJleHAiOjF9.sig` style payload) and a 401 first answer. Drop the `toBe(10000)` assertion or import the constant only.

### IN-10: A timed-out `/auth/me` request is abandoned, not cancelled

**File:** `services/apiService.ts:758-779`
**Issue:** Dropping the abort (the WR-10 fix) means a stalled `/auth/me` stays open after the 10 s timer fires, and the next 30 s tick starts another. Against a backend or proxy that holds requests, one connection per tick accumulates until the browser's own timeout. Under HTTP/1.1 (6 connections per host) a few of them can compete with the data loads for slots. Bounded and low likelihood, and it trades against the sign-out risk of WR-10, so it is only a note.
**Fix:** Fix WR-11 in `authFetch` first, then restore the `AbortController` in `fetchCurrentPermissions` so the timer cancels the request. Alternatively skip starting a new read while an abandoned one is still pending (keep a module-level "read pending" flag cleared when `read` settles).

### IN-11: The synchronous token path is dead in production and its docstrings are stale

**File:** `backend/authentication_service.py:111-121, 291-299, 160-169`; `backend/tests/test_custom_role_mfa.py:168-184`
**Issue:** After bee9299ce no production code calls `verify_token` (every route, tunnel, API-key and WebSocket path uses `verify_token_async`) or `mfa_required_for` except through `verify_token` and `mfa_action_for` without `required` (signup, built-in name). The `verify_token` docstring still says the WebSocket registry uses it, and the `mfa_required_for` docstring still describes a "WebSocket path". The sync function keeps a second copy of the validation rules that must stay in step with the async one (CRIT-01 checks, cutoff logic), and `test_custom_role_mfa.py` tests the sync cold-cache guess, which no request hits any more.
**Fix:** Update the docstrings. Either delete `verify_token` and `mfa_required_for` and move their tests to the async path, or share the claim validation in one helper so the two cannot drift.

### IN-12: MFA cache invalidation is not in a `finally`, and an in-flight lookup can re-store the old answer

**File:** `backend/role_endpoints.py:196-206` (`create_role`), `:249-250`, `:278-279`; `backend/authentication_service.py:142-144`
**Issue:** (1) In `create_role`, `invalidate_mfa_role_cache` runs only after the duplicate check succeeds. If `insert_one` succeeds and the follow-up `custom_role_docs` read then raises, the request answers 503 but the document exists and the tenant's cache was not cleared. The duplicate branch (409) also skips it. (2) `resolve_mfa_required` reads the role store, then stores its answer. A lookup that read the old document just before a role write and stores just after the invalidation re-caches the pre-edit answer for up to 60 s, so "enforced on the next request" is not strict under concurrency. Both are narrow windows on one worker.
**Fix:** Call the invalidation in a `finally` around the write section (clearing is idempotent and cheap), and optionally keep a per-tenant generation counter that `resolve_mfa_required` compares before storing: read `gen` first, and store only if `_mfa_gen.get(tenant) == gen`.

---

_Reviewed: 2026-10-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Incremental re-review: 2026-10-19 (a1f4488d1, App.tsx and src/__tests__/catalogueAccess.test.ts)_
_Incremental re-review 2: 2026-10-19 (b76b8af8d, App.tsx, utils/permissionRefresh.ts and src/__tests__/permissionRefresh.test.ts)_
_Incremental re-review 3: 2026-10-19 (41fb29db5, services/apiService.ts, utils/permissionRefresh.ts and src/__tests__/permissionRefresh.test.ts)_
_Incremental re-review 4: 2026-10-19 (3bb575186 and bee9299ce, backend/authentication_service.py, backend/role_endpoints.py, backend/websocket_manager.py, services/apiService.ts and their tests)_
