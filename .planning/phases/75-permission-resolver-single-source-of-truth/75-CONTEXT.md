# Phase 75: Permission Resolver & Single Source of Truth - Context

**Gathered:** 2026-10-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Every user gets one complete, server-evaluated permission set. It is computed by a single resolver over a single defaults table and delivered identically by `/login` and `/me`. Concretely:
- one defaults table, replacing `rbac_utils.DEFAULT_PERMISSIONS`, `rbac_service.default_roles`, the `app_startup.py` seed lists and the signup list;
- one `effective_permissions()` resolver (defaults ∪ role document), used by `/login`, `/me`, `verify_permission` and the role list;
- seeded shared role documents for every built-in role, including `admin` and `itam_admin`/`itam_user`/`itam_viewer`;
- a real `GET /api/roles`;
- removal of the frontend's empty-permissions fallback.

Requirements: ACC-01, ACC-02.

**Not in this phase:**
- the catalogue manifest and backend route guards (Phase 76);
- the fail-closed sidebar, ViewGate, no-access screen, landing view, 403/focus permission refresh, and the "what can this role see" admin view (Phase 77);
- persisted role create/edit (no backend endpoint exists; see Deferred).

**Security fixes folded in:** the discussion added two narrow fixes because they fall directly out of the role-set decisions:
- `manage:tenants` becomes super-admin only (D-06);
- a role-assignment ceiling (D-18).

</domain>

<decisions>
## Implementation Decisions

### Admin role sets
- **D-01:** `admin` and `Tenant Admin` resolve to the **same** permission set in the single table. `admin` is an alias of `Tenant Admin`, and the 18-permission gap between them today is treated as drift.
- **D-02:** Move the 26 catalogues tenant admins currently reach only through the seeded `Tenant Admin` document into the tenant-admin defaults in the table:
  - `view:advanced_hunting`, `view:agent_groups`, `view:analytics`, `view:android_enterprise`, `view:app_catalog`, `view:asset_intelligence`, `view:attack_timeline`, `view:autopilot`, `view:branch_sites`;
  - `view:conditional_access`, `view:config_drift`, `view:connectors_hub`, `view:detection_rules`, `view:device_config_profiles`, `view:fim`, `view:firmware_drivers`, `view:geographic_map`, `view:mam`;
  - `view:mdm`, `view:mssp`, `view:persistence`, `view:retention_policies`, `view:sca`, `view:security_copilot`, `view:web_monitoring`, `view:zero_trust`.
  - Plus the matching `manage:*` strings the seeded document carries.
  - No other role gains anything from this step.
- **D-03:** These 6 catalogues stay **super-admin only**, reachable solely through the `*` wildcard and never added to any tenant role: `view:federated_learning`, `view:goal_system`, `view:jobs`, `view:predictive_health`, `view:vector_db`, `view:webgpu_inference`.
- **D-04:** **Merge rule for every other built-in role** (`user`, `analyst`, `security_analyst`, `incident_responder`, `viewer`): when sources disagree, the single table gets the **union** of what any of today's sources grants (rbac_utils table, rbac_service table, app_startup seed docs). No user loses access they effectively have today.
  - The plan must output an explicit per-role diff (gained/lost) for review.
  - The explicit decisions D-03, D-06 and D-11 **override** the union. For example, rbac_service's `Tenant Admin` currently has `manage:tenants`, but D-06 removes it.
- **D-05:** Super-admin variants (`Super Admin`, `super_admin`, `superadmin`, `platform-admin`) return `["*"]` from `/login`, `/me` and the resolver, matching `rbac_service.get_permissions_for_role`. Normalization stays in `rbac_service._normalize_role`. The frontend's scattered super-admin name checks keep working; Phase 77 unifies them.
- **D-06:** `manage:tenants` becomes **super-admin only**: remove it from all tenant-admin defaults. In addition, the three bundle-assignment routes in `backend/bundle_endpoints.py` (`PUT`/`PATCH`/`DELETE /tenant/{tenant_id}/assign`, lines ~120–225) require super-admin explicitly, as a second safeguard. Removing it from tenant admins also hides the Tenants and Feature Bundles pages from them.
  - **Reason (found by code reading during discussion, not live-tested):** the `tenants` collection is exempt from tenant isolation (`backend/database.py` `TENANT_ISOLATION_EXEMPT_COLLECTIONS`). That lets any `Tenant Admin` rewrite **any** tenant's feature bundles (cross-tenant write) or self-assign paid bundles.
  - **Reversibility:** reversible.
- **D-07:** Signup stops writing the per-user `permissions` array onto new user records (`backend/authentication_endpoints.py` ~line 342 `enterprise_permissions`). Existing user records keep the field untouched (no migration) and it is ignored. Per-user grants are NOT introduced.

### ITAM role reach
- **D-08:** `itam_admin`, `itam_user` and `itam_viewer` all gain `view:profile`. That permission gates Profile (MFA/password), My Tasks and Notification Prefs. `view:profile` is already in the free tier's `enabledFeatures`, so the frontend tier intersection won't hide it.
- **D-09:** The ITAM roles do **not** get `view:dashboard`. They land in the ITAM console; Phase 77 guarantees a valid landing view, so Phase 75 must not paper over this by granting the dashboard.
- **D-10:** The ITAM roles **keep** `view:assets`, so the main Assets page stays visible to them. ITAM and Assets share one asset store, and the Phase 78 endpoint cost view joins `agents.assetId`.
- **D-11:** The existing ITAM grants carry over unchanged:
  - `itam_admin`: `manage:assets`, `manage:licenses`, `manage:users`, `view:itam`, `manage:procurement`, `manage:finance`;
  - `itam_user`: `view:assets`, `view:licenses`, `view:itam`, `request:assets`;
  - `itam_viewer`: `view:assets`, `view:licenses`, `view:itam`.

### Seeded role documents
- **D-12:** Startup **mirrors the single table** into the shared role documents (`tenantId: "all"`) on every startup, so the table is the only truth.
  - The seed upsert must match on `{name, tenantId: "all"}`, not name alone. Today `app_startup.py` lines ~353/414/522 match on `{"name": ...}` only, which could overwrite a tenant's own same-named role document.
  - Manual database edits to shared documents are reverted on restart, as they are today. Tenant-scoped documents are never touched.
- **D-13:** **Every** built-in role gets a seeded shared document: the existing seven (Super Admin, Tenant Admin, analyst, security_analyst, incident_responder, user, viewer) **plus** `admin`, `itam_admin`, `itam_user` and `itam_viewer`. This satisfies ACC-02 and success criterion 4.
- **D-14:** **Archive** (move, never delete) the one-off backend scripts that write role permission lists directly, so nobody re-runs one and re-creates drift.
  - **Corrected by 75-RESEARCH.md**, which checked each candidate. Archive exactly these 5: `backend/fix_rbac_integrations.py`, `backend/update_sbom_roles.py`, `backend/update_all_sbom_roles.py`, `backend/enable_compliance_for_admin.py`, `backend/reset_db_fresh.py`.
  - Destination: `archive/backend-rbac-oneoffs/`, with an `ARCHIVED.md` (the repo's existing archive convention).
  - **Keep in place:**
    - `fix_rbac.py` and `fix_all_rbac.py` rewrite source files, not role documents;
    - `unlock_enterprise_features.py` writes tenant tier lists only and is invoked by `deploy-ubuntu.sh:366` and `run-on-ubuntu.sh:429`;
    - `diagnose_rbac.py` is read-only.
  - The single-table drift test (success criterion 3) ignores the archive folder.
  - Follows the project's archive-not-delete rule.

### Role list & fallback
- **D-15:** `GET /api/roles` (`backend/role_endpoints.py`, currently a hardcoded 3-role stub) returns:
  - all built-in roles from the single table;
  - plus role documents belonging to the **caller's own tenant**;
  - each with its **effective** permissions computed by the same resolver as `/me`.
  - `Super Admin` is listed only to super-admins.
- **D-16:** `GET /api/roles` requires `manage:users` **or** `manage:rbac`, which covers tenant admins and `itam_admin`. The frontend `fetchWithCache` already tolerates a 403 (falls back to an empty or cached list), so the app must not break for other roles. The planner should verify the App.tsx `Promise.all` load path.
- **D-17:** Remove the frontend fallback in `App.tsx` (~lines 1213–1229). When `currentUser.permissions` is empty it looks the role up in the role list, where the stub "Admin" is `all`. Empty now means no catalogue access (fail closed).

### Role assignment & unknown roles
- **D-18:** **Role-assignment ceiling: nobody can assign a role above their own.** A caller can only assign a role whose effective permissions are a subset of the caller's own.
  - So `itam_admin` can assign the ITAM roles but not `admin`/`Tenant Admin`.
  - Tenant admins can assign everything except super-admin.
  - Super-admin can assign anything.
  - Nobody can change their **own** role.
  - Applies to user create/update in `backend/user_endpoints.py` (today only `_ELEVATED_ROLE_KEYS = {"super_admin"}` is blocked) **and** to the ITAM LDAP group→role mapping path.
  - **Reason (found by code reading, not live-tested):** user CRUD is gated by `manage:assets` via `_require_itam_admin_session_only`, so an `itam_admin` could create or promote a user, including themselves, to `admin`/`Tenant Admin`. With D-01 that set includes `manage:rbac` and `control:remote_access`.
- **D-20 (refines D-18; chosen after research found the literal subset rule blocks tenant admins from assigning any ITAM role):** the ceiling compares **effective permission sets with an implication closure applied to the caller's set only**: `manage:X` ⇒ `view:X` and `request:X`. The rules apply in this order, in one shared helper used by user create/update and by LDAP/SAML mapping writes:
  1. A super-admin-tier target is assignable only by a super-admin caller. That is decided by role-name normalization (`rbac_service._normalize_role`), never by a `"*"` appearing in a document.
  2. A caller changing their **own** account's role is rejected (403) when the requested role differs after normalization. Re-sending the same role is not a change.
  3. A super-admin caller may assign anything.
  4. Otherwise: target effective set ⊆ closure(caller effective set), using the same resolver (so a tenant-scoped document that widens a built-in counts).
  - The full caller × target matrix is a parametrized test.
- **D-21 (consequence of D-20, user-approved):** both tenant-admin roles (`Tenant Admin` and its alias `admin`) gain 6 ITAM permissions in the single table: `manage:procurement`, `manage:finance`, `manage:licenses`, `manage:users`, `view:licenses`, `request:assets`. With D-20's closure this lets tenant admins assign every ITAM role, and lets `itam_admin` assign `itam_user`/`itam_viewer`. It also fixes tenant admins' current 403 on ITAM procurement. This is an explicit exception to D-02's "no other role gains" (that clause was about non-admin roles).
- **D-22 (LDAP/SAML, extends D-18; research finding):** the LDAP and SAML group→role mapping validators accept `super_admin` (`backend/ldap_service.py:563-564`, `backend/saml_mapping.py:137-138`), and the mapping routes are gated only by `manage:assets`. Two fixes:
  - Enforce the D-20 ceiling when a mapping is **written** (callers of `upsert_mapping` at `backend/ldap_endpoints.py:173` and `backend/sso_endpoints.py:373`).
  - **At apply time**, refuse any mapping that resolves to the super-admin tier: log a warning and keep the user's existing/default role. This is in `LDAPUserSyncer.sync_user` (`backend/ldap_service.py:447-448`, `460`) and `SAMLUserProvisioner.provision_user` (`backend/saml_mapping.py:72-73`, `85`).
  - No data migration; existing mappings stay readable. Needs a regression test that fails today.
- **D-23 (resolver data access; research finding):** `/api/auth/login` is a public path with no tenant ContextVar (`backend/tenant_middleware.py:15-18`), so an own-tenant role lookup through the isolation wrapper can never match there. The resolver must read role documents through the raw handle (`db._db.roles`) with an **explicit** `tenantId`: the caller's own tenant first, then the shared sentinels.
- **D-24 (every session-mint response):** every response that carries `user.permissions` uses the resolver: `/login`, `/me`, MFA verify-login (`backend/mfa_endpoints.py:222-234`, currently has no permissions key), and the signup response (`backend/authentication_endpoints.py:~407`, which would otherwise lose permissions entirely once D-07 stops writing the stored array). Passkey/LDAP/SAML flows reload into `/me`.
- **D-25 (Super Admin shared document):** the existing Super Admin shared document lives at `tenantId: "platform"`, not `"all"`, and stays there. Each seed entry carries its own document `tenantId`; D-12's `"all"` applies to all the others. Its permissions mirror `["*"]` (consistent with D-05), replacing the 96-string list.
- **D-26 (cached role list):** the frontend's `omni_cache_roles` sessionStorage entry survives logout within a tab, so a later user could be shown a previous admin's role list. Clear it on logout, and do not serve the cached role list after a 403 from `/api/roles`.
- **D-19:** **A user whose role resolves to no permissions can still log in.** That covers a custom or legacy role with no defaults and no document. Login succeeds with an empty list, and the server logs a warning naming the role (not refused). Phase 77 renders the no-access screen with sign-out.

### Locked before this discussion (carried forward)
- ACC-01: effective permissions = role-document permissions ∪ that role's defaults, from one resolver used by `/login` and `/me`. This matches `rbac_utils.verify_permission`'s current enforcement semantics; `/login`/`/me` and `RBACService.get_user_permissions` currently differ and must be aligned to it.
- Phase 74 D-06: `control:remote_access` stays distinct from `view:remote_access`, and neither implies the other.
- v4.2 out-of-scope: no new permission model; no OPA/Casbin/CASL; no backend enforcement of tenant `enabledFeatures`.

### Claude's Discretion
- Where the single table lives. Research suggested a new `backend/rbac_defaults.py` imported by `rbac_utils` and `rbac_service`; the exact module layout is the planner's call.
- Resolver placement and signature, e.g. `rbac_utils.effective_permissions(user)`. Also whether `verify_permission` and `RBACService.has_permission`/`get_user_permissions` are rewritten to delegate to it; they should, so enforcement and delivery cannot diverge again.
- ~~`itam_admin` may also receive `manage:itam`~~ — resolved after research: **yes**, `itam_admin` gets `manage:itam` (parity with tenant admins; harmless).
- The frontend still intersects permissions with the tenant's `enabledFeatures` client-side. Keep that as-is: `/me` returns the role-effective set (what the backend enforces), and tier gating stays a separate UI concern.
- The drift test's mechanism (import-time assertion vs a pytest that greps for permission-list literals) and the per-role gained/lost diff format.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & decisions
- `.planning/REQUIREMENTS.md` — ACC-01, ACC-02 (this phase), the out-of-scope table, and the deferred ACC-F1/F2.
- `.planning/ROADMAP.md` § "Phase 75" — goal and the 4 success criteria.
- `.planning/research/SUMMARY.md` — milestone research synthesis: keystone resolver, open decisions D-1..D-4, Phase 75 delivery list.
- `.planning/research/PITFALLS.md` — Pitfall 2 (divergent tables / ungranted strings), Pitfall 4 (super-admin handling), Pitfall 5 (stale permissions after role change), Pitfall 6 (empty-sidebar lockout), Pitfall 17 (tier vs permission gating).
- `.planning/research/ARCHITECTURE.md` — proposed `effective_permissions()` resolver and `rbac_defaults.py` layout.

### Prior phase decisions that constrain this one
- `.planning/phases/74-interactive-remote-desktop-control-for-tenant-admins-upgrade/74-CONTEXT.md` — D-06: binary `view:`/`control:remote_access` model.

</canonical_refs>

<code_context>
## Existing Code Insights

### Permission sources to collapse (the drift)
- `backend/rbac_utils.py` lines ~74–183: `DEFAULT_PERMISSIONS`, defined **inside** `verify_permission`.
  - Includes the `itam_*` roles and `control:remote_access`.
  - `admin` lacks 18 permissions that `Tenant Admin` has.
  - `Tenant Admin` includes `manage:tenants` (removed by D-06).
- `backend/rbac_service.py` lines ~50–140: `RBACService.default_roles`, which differs from the above.
- `backend/app_startup.py`:
  - ~line 300–365: `Super Admin` doc with `all_permissions` (includes `admin:*`);
  - ~405–425: `Tenant Admin` doc;
  - ~440–530: `standard_roles`.
  - All are `$set` upserts keyed on name only (D-12).
- `backend/authentication_endpoints.py` ~line 342: signup `enterprise_permissions`, written onto the user record (D-07). Lines ~300–330 and `backend/tenant_endpoints.py` ~line 34–42 hold tenant `enabledFeatures` tier lists. Those are a **different concept** (tier features, not role permissions) and are out of scope.

### Delivery and enforcement paths to unify
- `backend/authentication_endpoints.py` `/login` (~line 223–231) and `/me` (~line 266–281): return only `find_role_doc(...)["permissions"]` or `[]`, the root cause of empty `itam_*`/`admin` permission lists.
- `backend/rbac_utils.py` `verify_permission`: defaults first, then a tenant role document (`roles.find_one({"name", "tenantId"})`). This is the union semantics ACC-01 locks.
- `backend/rbac_service.py` `get_user_permissions`: the role document **replaces** defaults, and defaults are only used when no document exists. It must be aligned.
- `backend/rbac_service.py` `find_role_doc`: own tenant first, then the `"all"`/`"platform"` sentinels via raw `db._db` (DB-F10). Reuse it.
- `backend/rbac_service.py` `_normalize_role`: the single role-name normalizer (`platform-admin` → `super_admin`). Reuse it; never add another literal set.
- `backend/authentication_service.py`: the JWT carries `role` (not permissions); the request-time `TokenData.role` comes from the token. A role change already calls `revoke_user_sessions` (`backend/user_endpoints.py` ~line 391–402), so stale-role-in-token is already handled.

### Role list / fallback / assignment
- `backend/role_endpoints.py`: a 39-line static stub (`Admin` = `["all"]`, User, Viewer), registered via `backend/router_registry.py`.
- `services/apiService.ts` ~line 714: `fetchRoles` → `/roles` through `fetchWithCache` (tolerates errors). `saveRole`/`deleteRole` (~line 2687) are **client-memory only**, with no backend.
- `App.tsx` ~lines 1185–1240: the `hasPermission` memo with the empty-permissions fallback to the role list (D-17); `checkPermission` handles `'all'`. Super-admin name checks are at ~691, 806, 946, 1189, 1234, 1383 and 1859 (Phase 77 unifies them).
- `backend/user_endpoints.py`:
  - `_VALID_ROLE_KEYS` comes from `rbac_service.default_roles` keys.
  - `_ELEVATED_ROLE_KEYS = {"super_admin"}`.
  - create/update/delete are gated by `_require_itam_admin_session_only` (`manage:assets`).
  - This is where D-18 lands; also find the ITAM LDAP group→role mapping path.
- `backend/bundle_endpoints.py` ~lines 120–225: three `require_permission("manage:tenants")` routes (D-06).
- `backend/database.py` ~line 26: `TENANT_ISOLATION_EXEMPT_COLLECTIONS` includes `"tenants"`.

### Established patterns
- Guards: `rbac_utils.require_permission(...)` / `require_super_admin` / `rbac_service.has_permission(...)` (with API-key `_scopes_allow` narrowing). Keep scope narrowing intact when delegating to the new resolver.
- Fail closed on role-store errors: `verify_permission` denies if the role lookup throws. Keep that behaviour in the resolver; `/login` should still succeed per D-19.

### Integration points
- Phase 76 consumes the single table and resolver for the catalogue manifest and route guards; Phase 77 consumes `/me` effective permissions and `/api/roles`.
- `tests/test_rbac.py` imports `role_endpoints`; expect to update it.

</code_context>

<specifics>
## Specific Ideas

- The planner must produce a reviewable **per-role gained/lost permission diff** (old effective set vs new) as part of the plan, since D-04's union plus the D-03/D-06 overrides change real access.
- Both security findings (D-06 cross-tenant bundle write, D-18 itam_admin → tenant admin escalation) come from code reading in this discussion. Each fix needs a regression test that would have failed before:
  - a Tenant Admin gets 403 on another tenant's `/tenant/{id}/assign`;
  - an `itam_admin` gets 403 assigning `admin`/`Tenant Admin` and when changing their own role.

</specifics>

<deferred>
## Deferred Ideas

- **Persisted role create/edit/delete.** `saveRole`/`deleteRole` in `services/apiService.ts` only change browser memory and no backend role-write endpoint exists. ACC-07 ("what can this role see") and ACC-08 ("a role-permission edit takes effect without re-login") in Phase 77 assume role edits exist. Phase 77 discussion must decide whether to add a minimal role-write API or scope ACC-08 to database/seed changes. Not in Phase 75.
- **Per-user permission grants** (an alternative to D-07). Rejected for this phase as a new capability.
- **Backend enforcement of tenant `enabledFeatures`.** Out of scope for v4.2 per REQUIREMENTS.md; noted again because Phase 75 keeps the client-side intersection.

</deferred>

---

*Phase: 75-permission-resolver-single-source-of-truth*
*Context gathered: 2026-10-12*
