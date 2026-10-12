# Phase 75: Permission Resolver & Single Source of Truth - Research

**Researched:** 2026-10-12
**Domain:** FastAPI/Motor RBAC consolidation (one defaults table + one resolver), startup role seeding under a tenant-isolation DB wrapper, role-assignment hardening, React permission fallback removal
**Confidence:** HIGH (everything below was read in the code or computed by script this session; the open items are product decisions, not unknowns)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Admin role sets**
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
- **D-06:** `manage:tenants` becomes **super-admin only**: remove it from all tenant-admin defaults. In addition, the three bundle-assignment routes in `backend/bundle_endpoints.py` (`PUT`/`PATCH`/`DELETE /tenant/{tenant_id}/assign`, lines ~120-225) require super-admin explicitly, as a second safeguard. Removing it from tenant admins also hides the Tenants and Feature Bundles pages from them.
  - **Reason (found by code reading during discussion, not live-tested):** the `tenants` collection is exempt from tenant isolation (`backend/database.py` `TENANT_ISOLATION_EXEMPT_COLLECTIONS`). That lets any `Tenant Admin` rewrite **any** tenant's feature bundles (cross-tenant write) or self-assign paid bundles.
  - **Reversibility:** reversible.
- **D-07:** Signup stops writing the per-user `permissions` array onto new user records (`backend/authentication_endpoints.py` ~line 342 `enterprise_permissions`). Existing user records keep the field untouched (no migration) and it is ignored. Per-user grants are NOT introduced.

**ITAM role reach**
- **D-08:** `itam_admin`, `itam_user` and `itam_viewer` all gain `view:profile`. That permission gates Profile (MFA/password), My Tasks and Notification Prefs. `view:profile` is already in the free tier's `enabledFeatures`, so the frontend tier intersection won't hide it.
- **D-09:** The ITAM roles do **not** get `view:dashboard`. They land in the ITAM console; Phase 77 guarantees a valid landing view, so Phase 75 must not paper over this by granting the dashboard.
- **D-10:** The ITAM roles **keep** `view:assets`, so the main Assets page stays visible to them. ITAM and Assets share one asset store, and the Phase 78 endpoint cost view joins `agents.assetId`.
- **D-11:** The existing ITAM grants carry over unchanged:
  - `itam_admin`: `manage:assets`, `manage:licenses`, `manage:users`, `view:itam`, `manage:procurement`, `manage:finance`;
  - `itam_user`: `view:assets`, `view:licenses`, `view:itam`, `request:assets`;
  - `itam_viewer`: `view:assets`, `view:licenses`, `view:itam`.

**Seeded role documents**
- **D-12:** Startup **mirrors the single table** into the shared role documents (`tenantId: "all"`) on every startup, so the table is the only truth.
  - The seed upsert must match on `{name, tenantId: "all"}`, not name alone. Today `app_startup.py` lines ~353/414/522 match on `{"name": ...}` only, which could overwrite a tenant's own same-named role document.
  - Manual database edits to shared documents are reverted on restart, as they are today. Tenant-scoped documents are never touched.
- **D-13:** **Every** built-in role gets a seeded shared document: the existing seven (Super Admin, Tenant Admin, analyst, security_analyst, incident_responder, user, viewer) **plus** `admin`, `itam_admin`, `itam_user` and `itam_viewer`. This satisfies ACC-02 and success criterion 4.
- **D-14:** **Archive** (move, never delete) the one-off backend scripts that write role permission lists directly, so nobody re-runs one and re-creates drift.
  - Candidates: `fix_rbac.py`, `fix_all_rbac.py`, `fix_rbac_integrations.py`, `update_sbom_roles.py`, `update_all_sbom_roles.py`, `unlock_enterprise_features.py`, `enable_compliance_for_admin.py`, `reset_db_fresh.py`.
  - The planner must confirm each one actually writes role permissions before moving it; `diagnose_rbac.py` is read-only and stays.
  - The single-table drift test (success criterion 3) ignores the archive folder.
  - Follows the project's archive-not-delete rule.

**Role list & fallback**
- **D-15:** `GET /api/roles` (`backend/role_endpoints.py`, currently a hardcoded 3-role stub) returns:
  - all built-in roles from the single table;
  - plus role documents belonging to the **caller's own tenant**;
  - each with its **effective** permissions computed by the same resolver as `/me`.
  - `Super Admin` is listed only to super-admins.
- **D-16:** `GET /api/roles` requires `manage:users` **or** `manage:rbac`, which covers tenant admins and `itam_admin`. The frontend `fetchWithCache` already tolerates a 403 (falls back to an empty or cached list), so the app must not break for other roles. The planner should verify the App.tsx `Promise.all` load path.
- **D-17:** Remove the frontend fallback in `App.tsx` (~lines 1213-1229). When `currentUser.permissions` is empty it looks the role up in the role list, where the stub "Admin" is `all`. Empty now means no catalogue access (fail closed).

**Role assignment & unknown roles**
- **D-18:** **Role-assignment ceiling: nobody can assign a role above their own.** A caller can only assign a role whose effective permissions are a subset of the caller's own.
  - So `itam_admin` can assign the ITAM roles but not `admin`/`Tenant Admin`.
  - Tenant admins can assign everything except super-admin.
  - Super-admin can assign anything.
  - Nobody can change their **own** role.
  - Applies to user create/update in `backend/user_endpoints.py` (today only `_ELEVATED_ROLE_KEYS = {"super_admin"}` is blocked) **and** to the ITAM LDAP group->role mapping path.
  - **Reason (found by code reading, not live-tested):** user CRUD is gated by `manage:assets` via `_require_itam_admin_session_only`, so an `itam_admin` could create or promote a user, including themselves, to `admin`/`Tenant Admin`. With D-01 that set includes `manage:rbac` and `control:remote_access`.
- **D-19:** **A user whose role resolves to no permissions can still log in.** That covers a custom or legacy role with no defaults and no document. Login succeeds with an empty list, and the server logs a warning naming the role (not refused). Phase 77 renders the no-access screen with sign-out.

**Locked before this discussion (carried forward)**
- ACC-01: effective permissions = role-document permissions ∪ that role's defaults, from one resolver used by `/login` and `/me`. This matches `rbac_utils.verify_permission`'s current enforcement semantics; `/login`/`/me` and `RBACService.get_user_permissions` currently differ and must be aligned to it.
- Phase 74 D-06: `control:remote_access` stays distinct from `view:remote_access`, and neither implies the other.
- v4.2 out-of-scope: no new permission model; no OPA/Casbin/CASL; no backend enforcement of tenant `enabledFeatures`.

### Claude's Discretion
- Where the single table lives. Research suggested a new `backend/rbac_defaults.py` imported by `rbac_utils` and `rbac_service`; the exact module layout is the planner's call.
- Resolver placement and signature, e.g. `rbac_utils.effective_permissions(user)`. Also whether `verify_permission` and `RBACService.has_permission`/`get_user_permissions` are rewritten to delegate to it; they should, so enforcement and delivery cannot diverge again.
- `itam_admin` may also receive `manage:itam` for parity with tenant admins (`manage:itam` is currently only an API-key scope name). Harmless, so the planner decides.
- The frontend still intersects permissions with the tenant's `enabledFeatures` client-side. Keep that as-is: `/me` returns the role-effective set (what the backend enforces), and tier gating stays a separate UI concern.
- The drift test's mechanism (import-time assertion vs a pytest that greps for permission-list literals) and the per-role gained/lost diff format.

### Deferred Ideas (OUT OF SCOPE)
- **Persisted role create/edit/delete.** `saveRole`/`deleteRole` in `services/apiService.ts` only change browser memory and no backend role-write endpoint exists. ACC-07 ("what can this role see") and ACC-08 ("a role-permission edit takes effect without re-login") in Phase 77 assume role edits exist. Phase 77 discussion must decide whether to add a minimal role-write API or scope ACC-08 to database/seed changes. Not in Phase 75.
- **Per-user permission grants** (an alternative to D-07). Rejected for this phase as a new capability.
- **Backend enforcement of tenant `enabledFeatures`.** Out of scope for v4.2 per REQUIREMENTS.md; noted again because Phase 75 keeps the client-side intersection.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ACC-01 | `/login` and `/me` return a server-evaluated *effective* permission set (role-doc permissions unioned with defaults) from a single resolver, so no role logs in with an empty permission list. | Sections "Resolver design", "Every reader/writer" (login/me/MFA-verify/signup all build `user.permissions`), "Per-role diff", "Super-admin wildcard"; the `/login` tenant-context trap (Pitfall 2) |
| ACC-02 | The drifted permission defaults (`rbac_utils.DEFAULT_PERMISSIONS` vs `rbac_service.default_roles`) are collapsed into one source of truth, and the missing `itam_admin/itam_user/itam_viewer` role documents are seeded. | Sections "Single table", "Seeding", "Role-writing scripts", drift-test mechanism, scripted per-role diff |
</phase_requirements>

## Summary

Phase 75 is a refactor of three drifting permission sources into one module, one async resolver, and a mirrored seed. The code reading turned up facts that change how it must be planned. (1) Today `verify_permission` never reads the shared `tenantId:"all"` role documents (it only looks for a document in the caller's own tenant), so "current effective set" is really three different sets depending on the path: enforcement, `RBACService`, and what `/login` delivers. (2) `/login` is a public path with no tenant ContextVar, so its own-tenant role lookup through the isolation wrapper can never match; `/login` and `/me` can already disagree for any tenant-scoped role document. The resolver therefore must read role documents through the raw handle with an explicit `tenantId`. (3) The startup seed runs with `set_tenant_id("platform-admin")`, which makes the wrapper pass `{"name": X}` through unchanged; I reproduced on a throwaway Mongo database that this overwrites a tenant's own same-named document and re-labels it `tenantId:"all"`. (4) Both security findings are confirmed from code, and the LDAP/SAML path is worse than D-18 states: the mapping validator accepts `super_admin`.

One decision the CONTEXT cannot satisfy as written: D-18's strict subset rule combined with D-11's "ITAM grants unchanged" means a Tenant Admin could no longer assign `itam_admin`/`itam_user`/`itam_viewer` and `itam_admin` could not assign `itam_user`/`itam_viewer` (the scripted ceiling matrix below shows it). This needs a one-line product decision before plans lock (Open Question 1; recommended resolution given). Everything else is mechanical.

**Primary recommendation:** Create `backend/rbac_defaults.py` (pure data, no imports of `database`/`fastapi`/`rbac_service`), put the resolver in `rbac_service.py` (so `_normalize_role` stays the only normalizer and there is no import cycle), make `rbac_utils.verify_permission` / `RBACService.get_user_permissions` / `/login` / `/me` / MFA-verify / signup / `GET /api/roles` all call it, seed with raw-handle `{name, tenantId}` upserts, and land the two security fixes (bundle routes, shared `assert_can_assign_role` helper) in the same phase with regression tests that fail on the pre-fix code.

## Key Findings That Change Planning (read first)

| # | Finding | Evidence | Planner impact |
|---|---------|----------|----------------|
| 1 | `verify_permission` ignores shared `"all"`/`"platform"` role docs; it queries only the caller's own tenant. | `[VERIFIED: backend/rbac_utils.py:209]` `role_doc = await get_database().roles.find_one({"name": user.role, "tenantId": user.tenant_id})` | The "current set" for the diff must be computed per path (done below). The union semantics ACC-01 locks are "defaults ∪ own-tenant doc"; the new resolver additionally reads the shared doc (harmless once the doc mirrors the table). |
| 2 | `/login` cannot see tenant-scoped role docs; `/me` can. | `[VERIFIED: backend/tenant_middleware.py:15-18]` `_PUBLIC_PATHS = [ "/health", "/api/health", "/api/auth/login",` (middleware skips ctx for public paths); `[VERIFIED: backend/database.py:55]` `effective_tenant_id = tenant_id if tenant_id else "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"` | Resolver must use `db._db.roles.find_one({"name":..., "tenantId": <explicit>})`. Do not rely on `find_role_doc`'s wrapper call for the own-tenant step. Also removes the `[SECURITY ALERT] DB Access without tenant context` log noise on every login. |
| 3 | Seed `{"name": X}` upserts can clobber a tenant's own role doc. Reproduced. | `[VERIFIED: backend/app.py:31-32]` `set_tenant_id("platform-admin")` then `await seed_database()`; `[VERIFIED: backend/database.py:51-52]` `if tenant_id == "platform-admin": return filter_query ...`; `[VERIFIED: throwaway Mongo db, dropped]` name-only upsert: `matched 1 upserted None` and the tenant's `viewer` doc became `('viewer','all',['view:dashboard'])`; proposed `{name, tenantId:"all"}` filter: run 0 `upserted`, run 1 `matched 1`, tenant doc `('viewer','tenant_x',['custom:only'])` untouched | D-12 is a real data-integrity fix, not cosmetic. Use the raw handle (`db._db.roles`) with explicit tenantId. Without any ctx the wrapper would instead insert a duplicate every boot (verified: 2 docs after 2 runs). |
| 4 | D-18 subset rule conflicts with D-11 + "TA can assign everything but super-admin". | Scripted ceiling matrix (see "Role-assignment ceiling") | Open Question 1. |
| 5 | LDAP/SAML mapping accepts `super_admin`. | `[VERIFIED: backend/ldap_service.py:563-564]` `valid_roles = {rbac_service._normalize_role(k) for k in rbac_service.default_roles.keys()}` / `if normalized not in valid_roles:`; `[VERIFIED: backend/rbac_service.py:51]` `"super_admin": ["*"], # All permissions`; mapping routes gated by `_require_itam_admin` (`manage:assets`); applied at `ldap_service.py:447-448` `if role:` / `doc["role"] = role` and `saml_mapping.py:72-73` | Strictly worse than D-18's tenant-admin escalation: an `itam_admin` can map a directory group to `super_admin` (needs LDAP/SAML config, which the same guard also controls). Enforce the ceiling at mapping-write time AND hard-block super-admin-tier at apply time. |
| 6 | `D-14` candidate list is partly wrong. | Section "Role-writing scripts" | Archive 5 scripts, not 8. `unlock_enterprise_features.py` is invoked by deploy scripts. |
| 7 | Super Admin's shared doc lives at `tenantId:"platform"`, not `"all"`. | `[VERIFIED: backend/app_startup.py:353-363]` `{"name": "Super Admin"},` ... `"tenantId": "platform",`; live DB inventory below | D-12/D-13 say `tenantId:"all"`. Seeding `{name:"Super Admin", tenantId:"all"}` would add a second doc. Open Question 2. |
| 8 | `/login` is not the only session mint that builds `user.permissions`. | `[VERIFIED: backend/mfa_endpoints.py:222-234]` `user_data = _public_user_fields(user)` ... `"user": user_data` (no permissions key); signup `user_data = _public_user_fields(user_doc)` at `authentication_endpoints.py:407`; LDAP/SAML return no user object | Add the resolver to MFA verify-login and signup responses (cheap, and signup would otherwise lose permissions entirely once D-07 drops the stored array). Passkey/LDAP/SAML/MFA flows end in `window.location.reload()` -> `/me`, so `/me` is the authoritative path. |
| 9 | `rbac_service.get_user_permissions` returns `[]` for role `tenant_admin`. | `[VERIFIED: backend/rbac_service.py:195-199]` `self.default_roles.get(user.role) or self.default_roles.get(normalized) or []` with the table keyed `"Tenant Admin"` only (line 72) | A latent bug the single resolver fixes; add a regression test (role `"tenant_admin"` and `"Admin"` non-empty via every path). |
| 10 | Live DB is tiny and safe. | `[VERIFIED: read-only pymongo query this session]` 7 role docs: `'Tenant Admin' 'all' 113`, `'analyst' 'all' 19`, `'incident_responder' 'all' 12`, `'security_analyst' 'all' 17`, `'user' 'all' 22`, `'viewer' 'all' 8`, `'Super Admin' 'platform' 96`; users by role `{'Super Admin': 1, 'Tenant Admin': 7, 'viewer': 1}` | No tenant-scoped custom role docs and no `admin`/ITAM users exist live: zero migration risk; "pre-existing custom roles still resolve" is proven by tests only. The `Tenant Admin` doc (113) equals the code list (113), so the live "delivered" set equals the code. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Defaults table (role -> permissions) | API / Backend (`rbac_defaults.py`) | Database (mirrored docs) | Backend is the source of truth; DB docs are a projection reseeded each boot (D-12). |
| Effective-permission resolution | API / Backend | Database (role docs) | Server-evaluated; the browser never computes role semantics except tier intersection. |
| `/login` `/me` MFA-verify signup delivery | API / Backend | Browser (stores `currentUser.permissions`) | One helper builds `user.permissions` for every session-minting response. |
| Request-time enforcement (`verify_permission`, `has_permission`) | API / Backend | — | Must delegate to the same resolver as delivery. |
| Role-assignment ceiling | API / Backend | — | Shared helper used by user CRUD and LDAP/SAML mapping writes. |
| Cross-tenant write guard (bundle routes) | API / Backend | — | `tenants` is isolation-exempt, so the route itself must enforce super-admin. |
| Startup seeding of shared role docs | Database / Storage (via raw handle in `app_startup`) | API / Backend (table) | Idempotent upsert on `{name, tenantId}`; never touches tenant-scoped docs. |
| `GET /api/roles` | API / Backend | Browser (Settings > Roles list, Add/Edit user dropdowns) | Replaces the static stub. |
| Fail-closed permission derivation | Browser / Client (`App.tsx` memo) | — | D-17 removes the roles-list fallback; tier intersection stays client-side. |

## Standard Stack

No new dependencies. `[VERIFIED: git status --short]` shows `backend/requirements.txt` and `package.json` already modified in the working tree by unrelated work, so the milestone check `git diff --stat -- backend/requirements.txt package.json package-lock.json` must be compared against `HEAD` at phase start, not against zero.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | routes/dependencies | already used |
| Motor / pymongo | existing | role docs, raw-handle upserts | `db._db` raw access is the established bypass (`find_role_doc`) |
| pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode=auto`) | installed | backend tests | `[VERIFIED: pytest run output this session]` |
| vitest 5.0.0 (jsdom) | installed | frontend tests | `[VERIFIED: vitest run output this session]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled in-memory fake collection (existing pattern) | `mongomock_motor` | `[VERIFIED: venv import this session]` `ModuleNotFoundError: No module named 'mongomock_motor'` (database.py optionally imports it only for demo mode). Do not add a dependency; reuse the in-memory `_Collection` pattern from `backend/tests/test_sso_config_without_tenant_context.py` (real `TenantIsolatedDatabase` over a fake raw db). |
| OPA/Casbin/CASL | — | Explicitly out of scope for v4.2. |

**Installation:** none.

## Package Legitimacy Audit

No external packages are installed or recommended in this phase. Nothing to audit.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                     STARTUP (app.py lifespan: ctx = "platform-admin")
 rbac_defaults.ROLE_DEFAULTS ──► seed_database ──raw db._db.roles.update_one({name, tenantId}, $set, upsert)──► roles (11 shared docs)
        │  (single table, pure data)                                                                              ▲
        │                                                                                                        │ read (explicit tenantId, raw handle)
        ▼                                                                                                        │
 rbac_service.effective_permissions(db, role, tenant_id) ──► defaults(role) ∪ doc(own tenant) ∪ doc("all") ∪ doc("platform")
        ▲        ▲          ▲            ▲              ▲               ▲
        │        │          │            │              │               │
   /login    /me     MFA verify-login  signup resp.  verify_permission  RBACService.has_permission / get_user_permissions
 (public,  (ctx =                                    (defaults first,    (scope narrowing for API keys stays)
 no ctx)   JWT tenant)                                doc only on miss)
        │        │
        └──► user.permissions ──► browser currentUser.permissions ──► App.tsx memo (tier ∩ enabledFeatures; empty => no access, D-17)

 GET /api/roles ──► built-ins from table + caller-tenant docs, each via effective_permissions ──► Settings > Roles, Add/Edit User dropdowns
 User create/update, LDAP & SAML mapping upsert ──► assert_can_assign_role(caller, target) ──► 403 above ceiling / self / super_admin tier
 bundle PUT/PATCH/DELETE /tenant/{id}/assign ──► require_super_admin (second safeguard) 
```

### Recommended Project Structure
```
backend/
├── rbac_defaults.py        # NEW: pure data + tiny pure helpers (no db/fastapi/rbac_service imports)
├── rbac_service.py         # resolver + default_roles (derived) + ceiling helper live here (owns _normalize_role)
├── rbac_utils.py           # verify_permission delegates; DEFAULT_PERMISSIONS literal deleted
├── role_endpoints.py       # real GET /api/roles
├── app_startup.py          # seed loop over the table; three literal blocks deleted
├── authentication_endpoints.py  # /login, /me, signup use the resolver; enterprise_permissions deleted
├── mfa_endpoints.py        # verify-login response gets permissions
├── user_endpoints.py       # ceiling + self-change guard; _VALID_ROLE_KEYS derived from the table
├── ldap_endpoints.py / sso_endpoints.py / ldap_service.py / saml_mapping.py  # ceiling at write, super-admin block at apply
└── bundle_endpoints.py     # 3 routes -> require_super_admin
archive/backend-rbac-oneoffs/   # NEW (see scripts section), with ARCHIVED.md like archive/agent-rust/ARCHIVED.md
backend/tests/…                 # new + updated tests (Validation Architecture)
```

Import-cycle rule `[VERIFIED: backend/rbac_utils.py:8, backend/rbac_service.py:1-4]`: `rbac_utils` imports `rbac_service`; `rbac_service` imports `authentication_service` and `database`. Therefore `rbac_defaults.py` must import neither, and normalization (`RBACService._normalize_role`, a `@staticmethod`, `rbac_service.py:142-158`) stays in `rbac_service`, called by the resolver before indexing the table. This satisfies D-05 ("normalization stays in `_normalize_role`") with no second literal set.

### Pattern 1: Single table keyed by normalized role key
**What:** `ROLE_DEFAULTS: dict[str, tuple[str, ...]]` keyed by the `_normalize_role` output (`super_admin`, `tenant_admin`, `analyst`, `security_analyst`, `incident_responder`, `user`, `viewer`, `itam_admin`, `itam_user`, `itam_viewer`) plus `ROLE_ALIASES = {"admin": "tenant_admin"}` (D-01) and `SEED_ROLE_DOCS` metadata (doc `name`, `id`, `description`, `isEditable`, doc `tenantId`). Drop the `"Analyst": []`, `"tenant_admin": []` alias stubs and the `_CANONICAL_KEY_BY_NORMALIZED` redirect in `verify_permission` (they exist only because the old table was keyed by display names).
**Content rule:** build the tuples mechanically with the generator in Appendix A and paste the output; do not retype. Expected sizes (computed): `tenant_admin`/`admin` 121, `user` 22, `analyst` 19, `security_analyst` 17, `incident_responder` 12, `viewer` 8, `itam_admin` 7, `itam_user` 5, `itam_viewer` 4 `[VERIFIED: script output this session]` (+4 to +6 for the tenant-admin set if Open Question 1 option A is chosen).
**Back-compat:** keep `RBACService.default_roles` as a derived read-only dict (so `test_prod_hardening.py:159` `rbac_service.default_roles[role]` for `"admin"`/`"Tenant Admin"`/`"viewer"` and `user_endpoints._VALID_ROLE_KEYS` keep working): build it from the table with both normalized keys and the legacy display key `"Tenant Admin"`. A derived dict is not a literal list, so the drift test is unaffected.

### Pattern 2: One async resolver, defaults-first enforcement
```python
# Sketch only. Names are proposals; values in quotes come from the verified citations in this file.
# rbac_service.py
async def effective_permissions(db, role: str | None, tenant_id: str | None) -> list[str]:
    key = RBACService._normalize_role(role or "")
    if key == "super_admin":
        return ["*"]                                   # D-05
    base = default_permissions_for_key(key)             # from rbac_defaults, [] if unknown
    docs: list[dict] = []
    for name in dict.fromkeys([role or "", key]):       # raw then normalized, like get_user_permissions
        docs += await _role_docs(db, name, tenant_id)   # own tenant, "all", "platform" via db._db, explicit tenantId
    extra = [p for d in docs for p in d.get("permissions", [])]
    return list(dict.fromkeys([*base, *extra]))         # defaults first, de-duplicated, order stable
```
- `_role_docs` reads `db._db.roles.find_one({"name": name, "tenantId": X})` for X in `[tenant_id, "all", "platform"]` (skip a falsy `tenant_id`). Reads of the user's OWN tenant id are not a cross-tenant read; the `"all"/"platform"` sentinels are the documented shared catalogue (`rbac_service.py:8-31`).
- Order stability matters: existing `test_db_role_doc_takes_precedence_over_defaults` asserts `perms == ["view:threats", "view:security"]` for a role with no defaults. "Defaults first, then doc extras, de-duplicated in order" keeps it green; sorting would break it.
- `verify_permission` must keep its cheap path: check the synchronous defaults first (`"*" in perms or required in perms` -> True with no DB hit), then fall through to the doc union only on a miss; keep the current fail-closed `except` (deny when the role store throws). Keep the name, signature, and the module attribute `rbac_utils.get_database` (tests patch `rbac_utils.get_database` and `rbac_utils.verify_permission`).
- `/login` and `/me` wrap the resolver in `try/except`: on a role-store error return defaults-only (the table needs no DB) and log a warning; never fail the login (D-19). Log `warning("role %r resolved to no permissions")` at `/login` only (avoids per-`/me` log spam).
- API-key scope narrowing (`RBACService._scopes_allow`, `rbac_service.py:203-221`; `has_permission` order at 223-250) must stay exactly as is: delegate only the "what does the role grant" step.

### Pattern 3: Seed loop over the table, raw handle, explicit tenantId
```python
# app_startup.py (replaces the three literal blocks at ~313-529)
raw_roles = db._db.roles                                  # `_db` is the established wrapper bypass: backend/rbac_service.py:27 `raw_db = db._db`
for doc in seed_role_documents():                         # 11 docs from the table
    await raw_roles.update_one(
        {"name": doc["name"], "tenantId": doc["tenantId"]},   # "all" for every role except Super Admin (see Open Question 2)
        {"$set": doc},
        upsert=True,
    )
```
Each doc in its own `try/except` (ARCH-018 requires one broken step not to block the others, `app_startup.py:221-232` docstring). Verified on real Mongo that `$set` re-stating the filter's `tenantId` is accepted and the upsert is idempotent (run 0 upserts, run 1 matches).

### Pattern 4: Shared role-assignment helper (D-18)
One function used by `create_user`, `update_user`, `LDAPGroupMapper.upsert_mapping` callers (`ldap_endpoints.py:173`) and `SAMLGroupMapper.upsert_mapping` callers (`sso_endpoints.py:373`):
- `assert_can_assign_role(db, caller: TokenData, target_role: str, *, target_tenant_id, target_email=None)` raising `HTTPException(403)`.
- Rules in order: (1) target normalizes to `super_admin` -> only if `is_super_admin(caller.role)` (keeps `_ELEVATED_ROLE_KEYS` semantics, never decided by a `"*"` appearing in a document); (2) caller assigning to their own account (`target_email == caller.username`) with a role that differs from the current one -> 403; (3) super-admin caller -> allow; (4) otherwise `set(effective(target_role, target_tenant_id)) ⊆ set(effective(caller.role, caller.tenant_id))` using the SAME resolver (so a tenant-scoped doc that widens a built-in is counted).
- Keep a pure function `ceiling_allows(caller_perms, target_perms, *, implied=...)` for unit tests; keep `RBACService.can_assign_role` as a thin wrapper or retire it (it is referenced only by `tests/test_rbac.py:273-295`; no production caller `[VERIFIED: grep this session]`).
- Apply-time defence in depth: `LDAPUserSyncer.sync_user` (`ldap_service.py:447-448`, `460`) and `SAMLUserProvisioner.provision_user` (`saml_mapping.py:72-73`, `85`) must refuse a mapping that resolves to the super-admin tier (log a warning, keep the existing role / default role). No data migration; existing mappings stay readable.

### Pattern 5: Frontend fail-closed
Delete `App.tsx` `} else { // Fallback to role-based lookup ... }` (lines 1213-1230, comment at 1214, closing comment at 1229). Leave `effectiveFeatures = []` when `currentUser.permissions` is empty. Keep the tier intersection and `checkPermission` as is. `roles` stays in the `useMemo` deps only if still used; after deletion the memo no longer reads `roles`, so remove it from the dependency array `[currentUser, roles, tenants]` (line 1242) to avoid needless recomputes. Recommended (small): extract the derivation into a pure function in `utils/permissions.ts` so a vitest can assert "empty permissions -> hasPermission false for everything except super-admin names" (App.tsx itself has no unit test `[VERIFIED: grep src/__tests__]`).

### Anti-Patterns to Avoid
- **Two writers for the same list:** any new role->permission literal outside `rbac_defaults.py` (drift test fails the build).
- **Relying on the wrapper for role reads/writes in a pre-auth or startup context:** the ContextVar differs per call site (`None` at `/login`, `"platform-admin"` at seed, JWT tenant at `/me`).
- **Computing the ceiling from raw default lists only:** a tenant-scoped doc can widen a built-in; compare resolver outputs.
- **Deciding "is super-admin" from the presence of `"*"` in a document** (a tenant doc with `"*"` is honoured by `verify_permission` at line 214; do not let it satisfy the assignment rule).
- **Changing `find_role_doc`'s wrapper call** without updating `tests/test_find_role_doc.py:30-35` (asserts `db.roles.find_one.assert_awaited_with({"name": "Custom Role", "tenantId": "tenant-a"})`); simpler: leave `find_role_doc` untouched for `zero_trust_service.py:305` and add the new raw-handle helper.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Role name normalization | a new literal set of super-admin variants | `RBACService._normalize_role` (`rbac_service.py:142-158`) and `rbac_utils.is_super_admin` | `[VERIFIED: rbac_service.py:156-157]` `if normalized in ("superadmin", "platform_admin"): return "super_admin"`; D-05 mandates it |
| Shared-role catalogue lookup | another bypass around the wrapper | the `db._db` pattern already blessed in `find_role_doc` (DB-F10) | one documented exception to tenant isolation |
| Session revocation after a role change | a new token-invalidation scheme | existing `revoke_user_sessions` (`user_endpoints.py:391-402`, `authentication_service.py:110`) | stale-role-in-token is already handled; LDAP/SAML also call it |
| In-memory Mongo for tests | `mongomock_motor` | the in-repo `_Collection`/`_RawDB` fake over the real `TenantIsolatedDatabase` | package not installed; pattern exists (`test_sso_config_without_tenant_context.py`) |
| Per-role diff review | manual comparison | the generator in Appendix A (AST-based, reads the three source files) | the three sources are literals inside functions; import cannot reach them |
| Permission-literal drift detection | grep with regexes | `ast` walk over `backend/*.py` (see Validation Architecture) | lists span lines; AST sees list/tuple literals exactly |

**Key insight:** the bug class here is "same fact written in N places"; every fix is to make N=1 and add a test that fails when N becomes 2.

## Per-Role Permission Diff (Question 1)

Method: Appendix A parses the literals with `ast` from `backend/rbac_utils.py` (`DEFAULT_PERMISSIONS`), `backend/rbac_service.py` (`default_roles`), `backend/app_startup.py` (`all_permissions`, `tenant_admin_permissions`, `standard_roles`). NEW = union of all sources per role (D-04) with: `admin` and `Tenant Admin` merged (D-01); minus `manage:tenants` (D-06); minus the six D-03 strings; plus `view:profile` on the three ITAM roles (D-08). Three "old" baselines because the three live paths differ today:
- **ENF** = `rbac_utils.verify_permission` for shared roles (defaults only; shared docs are not read, finding 1).
- **RBACSVC** = `RBACService.get_user_permissions` (seeded doc REPLACES defaults if a doc exists, else `rbac_service.default_roles`; `admin` and ITAM roles have no doc).
- **DELIVERED** = `/login` and `/me` today (seeded doc permissions or `[]`).

Sizes `[VERIFIED: script output this session]`: sources contain duplicates (e.g. `Tenant Admin` in `rbac_utils` is 78 entries / 77 unique); counts below are unique.

| Role | NEW | vs ENF (enforcement) | vs RBACSVC | vs DELIVERED (what the UI sees today) |
|------|-----|----------------------|------------|----------------------------------------|
| `admin` | 121 | **+62**, -0 | +68, **-3** (`view:federated_learning`, `view:vector_db`, `view:webgpu_inference`) | +121 (delivered `[]` today) |
| `Tenant Admin` | 121 | +45, **-1** (`manage:tenants`) | +8, -0 | +8, -0 |
| `user` | 22 | 0 / 0 | 0 / 0 | 0 / 0 |
| `analyst` | 19 | 0 / 0 | 0 / 0 | 0 / 0 |
| `security_analyst` | 17 | 0 / 0 | 0 / 0 | 0 / 0 |
| `incident_responder` | 12 | 0 / 0 | 0 / 0 | 0 / 0 |
| `viewer` | 8 | 0 / 0 | 0 / 0 | 0 / 0 |
| `itam_admin` | 7 | +1 (`view:profile`) | +1 | +7 (delivered `[]` today) |
| `itam_user` | 5 | +1 (`view:profile`) | +1 | +5 (delivered `[]` today) |
| `itam_viewer` | 4 | +1 (`view:profile`) | +1 | +4 (delivered `[]` today) |
| `Super Admin` variants | `["*"]` | unchanged (wildcard bypass) | unchanged | was a 96-string list (live doc), becomes `["*"]` (D-05) |

**`Tenant Admin` gained vs ENF (45)** = exactly the D-02 set: 26 `view:*` (`advanced_hunting agent_groups analytics android_enterprise app_catalog asset_intelligence attack_timeline autopilot branch_sites conditional_access config_drift connectors_hub detection_rules device_config_profiles fim firmware_drivers geographic_map mam mdm mssp persistence retention_policies sca security_copilot web_monitoring zero_trust`) + 19 `manage:*` (`advanced_hunting agent_groups android_enterprise app_catalog asset_intelligence autopilot branch_sites conditional_access config_drift connectors_hub detection_rules device_config_profiles fim firmware_drivers mam mdm mssp retention_policies sca`). No surprises.

**`Tenant Admin` gained vs DELIVERED (8):** `control:remote_access`, `manage:approvals`, `manage:assets`, `manage:compliance`, `manage:secrets`, `view:approvals`, `view:remote_access`, `view:secrets`. Enforcement already granted all of these via `rbac_utils` (so no new backend power); the effect is that the UI will now show Remote Access control, Secrets, and Approvals to tenant admins who could previously only reach them by URL. Flag for review. Via the `RBACService.has_permission` path the gain is real backend power (`manage:assets` is checked by `has_permission` at 2 sites, `manage:compliance` is newly granted there).

**`admin` gained vs ENF (62), all by D-01 alignment to the `Tenant Admin` set** — sensitive ones to eyeball: `manage:secrets` (new; `view:secrets` was already in `admin`'s `rbac_utils` list), `manage:approvals`, `manage:devsecops`, `manage:experiments`, plus all 19 D-02 `manage:*` and 26 D-02 `view:*`, plus `view:integrations view:mlops view:llmops view:automl view:xai view:governance view:swarm view:unified_ops view:advanced_bi view:sustainability view:threat_intel view:vulnerabilities view:security_audit`. Full list: `manage:advanced_hunting manage:agent_groups manage:android_enterprise manage:app_catalog manage:approvals manage:asset_intelligence manage:autopilot manage:branch_sites manage:conditional_access manage:config_drift manage:connectors_hub manage:detection_rules manage:device_config_profiles manage:devsecops manage:experiments manage:fim manage:firmware_drivers manage:mam manage:mdm manage:mssp manage:retention_policies manage:sca manage:secrets` + `view:` {advanced_bi advanced_hunting agent_groups analytics android_enterprise app_catalog asset_intelligence attack_timeline automl autopilot branch_sites conditional_access config_drift connectors_hub detection_rules device_config_profiles fim firmware_drivers geographic_map governance integrations llmops mam mdm mlops mssp persistence retention_policies sca security_audit security_copilot sustainability swarm threat_intel unified_ops vulnerabilities web_monitoring xai zero_trust}. `admin` already had `control:remote_access`, `view:remote_access`, `manage:rbac`, `manage:api_keys`, `manage:settings` in ENF; none of those change.

**Things that LOSE a permission (surprising):**
1. `Tenant Admin` and `admin` lose `manage:tenants` (D-06, intended).
2. `admin` loses `view:vector_db`, `view:federated_learning`, `view:webgpu_inference` on the `RBACService` path (D-03 override of the D-04 union). Impact: `[VERIFIED: grep this session]` 17 routes use `rbac_service.has_permission("view:vector_db")` (all in `backend/customer_vector_db_endpoints.py`); `Tenant Admin` already cannot reach them today because its seeded doc replaces defaults and lacks the string, and no live user has role `admin`. Net: only a hypothetical `admin` user loses `/api/vector/*`. Add an explicit test so the loss is deliberate.
3. Nothing else loses anything.

**The six D-03 strings today:** `view:federated_learning`, `view:vector_db`, `view:webgpu_inference` appear only in `rbac_service.default_roles` (`admin` and `Tenant Admin`); `view:goal_system`, `view:jobs`, `view:predictive_health` appear in no table `[VERIFIED: script output]`.

**Super-admin docs:** live `Super Admin` doc has 96 permissions incl. `admin:*` (`app_startup.py:351`); with D-05 `/login`/`/me` return `["*"]`. The frontend ignores the list for super-admin names (see Question 9).

## Every Reader/Writer of Role Permissions (Question 2)

**Role->permission literals (writers of the truth) — all must collapse into `rbac_defaults.py`** `[VERIFIED: ast scan of backend/*.py, this session]`:
- `app_startup.py:314` (`all_permissions`, 96), `:370` (`tenant_admin_permissions`, 113), `:453/468/483/497/513` (five `standard_roles`)
- `rbac_service.py:52/72/92/100/105/114/122/130` (`default_roles`)
- `rbac_utils.py:81/102/130/139/148/155/162/174` (`DEFAULT_PERMISSIONS`)
- `authentication_endpoints.py:342` (`enterprise_permissions`, 63; signup, D-07)
- Not role->permission (different concept or archived): `authentication_endpoints.py:318` (`free_features`, tier), `tenant_endpoints.py:33` (`TenantCreate.enabledFeatures`, tier), `unlock_enterprise_features.py:14` (tier), `seed_demo_data.py:18/25` (tier) and `:34` (`admin_permissions`, a per-user array written by the docker-compose seed `docker-compose.yml:119`; ignored by all code, see below), `reset_db_fresh.py:29/41` (archived by D-14).

**Consumers to switch**
| Consumer | Where | Action |
|----------|-------|--------|
| `verify_permission` | `rbac_utils.py:62-214`; ~25 callers (mcp_rest, native_security_ops, stream_processing, deployment_result, remediation_*, webhook, itam_* incl. `_require_itam_admin` / `_require_itam_admin_session_only` at `itam_asset_endpoints.py:96-115`, remote_endpoints, graphql_api/resolvers, response, swarm, alert, agent_metrics) | delegate; keep name/signature; many tests patch it by module-bound name |
| `RBACService.get_user_permissions` / `has_permission` / `get_permissions_for_role` / `default_roles` | `rbac_service.py:50-250` | delegate to resolver / derive from table |
| `/login`, `/me` | `authentication_endpoints.py:223-231`, `266-281` | call resolver |
| MFA verify-login, signup response | `mfa_endpoints.py:222-234`, `authentication_endpoints.py:407-425` | attach resolver output (finding 8) |
| `_VALID_ROLE_KEYS` | `user_endpoints.py:33` | derive from the table (keeps accepting `Admin`, `tenant_admin`) |
| LDAP/SAML mapping validators | `ldap_service.py:563`, `saml_mapping.py:137` | derive from the table; add ceiling (Question 3) |
| `zero_trust_service` | `zero_trust_service.py:305-312` | reads a raw doc's `permissions` (`"all" not in permissions` — a string no table uses). Optional: switch to the resolver; otherwise leave (it only affects a risk score) |
| API-key path | `api_key_auth.py` builds `TokenData(role=owner_role, scopes=...)` (`:227,:247-249`); `_scopes_allow` narrowing in `has_permission` and `itam_asset_endpoints._require_itam_admin` | no change; keep narrowing intact |
| GraphQL / MCP | `graphql_api/resolvers.py:32`, `mcp_rest_endpoints.py:43` call `verify_permission` | free once `verify_permission` delegates |
| Role-name allowlists (NOT permission tables) | 13 `require_role([...])` sites (`["admin"]` ×3, `["itam_admin"]` ×1, …), `auth_roles.SUPER_AND_ADMIN_ROLES`, `tenant_endpoints.py:18` `_TENANT_ADMIN_ROLES = {"Admin", "Tenant Admin", "tenant_admin"}` and `:323` `{"Admin","Tenant Admin","tenant_admin","admin"}`, `trust_endpoints.py:16` | out of scope; record as Phase 76 input (note the two `tenant_endpoints` sets disagree on lowercase `admin`) |
| Per-user `permissions` array | no backend code reads it `[VERIFIED: grep for get("permissions") / ["permissions"] this session]` (only role docs are read) | D-07 safe: drop the write at signup; leave existing records |
| Frontend | `App.tsx` memo (Question 7); `constants.ts`/`data.ts` hold a frontend copy of the permission vocabulary and a static `Tenant Admin` role (`ALL_PERMISSIONS.filter(p => p !== 'manage:tenants')`), not consumed by the derivation | leave |

Existing tests that encode the OLD behaviour and must be updated (exhaustive for the files run in the baseline):
- `tests/test_rbac.py:188` `assert set(perms) == {"view:assets", "view:licenses", "view:itam", "request:assets"}` (itam_user, now +`view:profile`); `:199` itam_viewer likewise.
- `tests/test_rbac.py:406-414` `test_tenant_admin_snake_case_still_redirects_to_canonical_entry` asserts `manage:tenants` is allowed for `tenant_admin` -> flip to denied (D-06 regression).
- `tests/test_rbac.py:291-295` `can_assign_role("itam_user", "itam_admin") is True` -> now False (D-18).
- `tests/test_seed_database_step_isolation.py`: mocks `db.roles.update_one` and expects exactly 7 names; must mock `db._db.roles.update_one` and expect 11.
- `tests/test_prod_hardening.py:157-160` indexes `rbac_service.default_roles["Tenant Admin"]` (keep the derived dict's `"Tenant Admin"` key or edit the test).
- `tests/test_ldap_service.py:392-402`, `tests/test_sso_saml.py:361-371`: `upsert_mapping(group, role, tenant_id=...)` has no caller argument; keep the model-layer signature and enforce the ceiling in the endpoint layer so these keep passing.
- `tests/test_bundles_and_reports.py:153-215` patches `rbac_utils.verify_permission -> True` for the bundle routes; the new super-admin guard needs an explicit role in those tests.
- `tests/test_user_crud.py:129-153` monkeypatches `itam_asset_endpoints.verify_permission` with a fixed role set; the ceiling helper will call the resolver against `FakeDB` which has no `roles`; give `FakeDB` a `roles` collection or have the helper tolerate a missing store (fall back to table-only) and add cases.

## ITAM LDAP/SAML Group->Role Path (Question 3)

- **Mapping write:** `POST /api/admin/ldap/group-mapping` (`ldap_endpoints.py:173`) and `POST /api/admin/sso/saml/attribute-mapping` (`sso_endpoints.py:373`), both gated by `_require_itam_admin` = `_require_itam_admin_session_only` (`manage:assets`, `itam_asset_endpoints.py:96-115`). The caller's role is available in the handler (`current_user`).
- **Mapping validation today:** only "normalizes to a key of `default_roles`", which includes `super_admin` (finding 5).
- **Mapping apply:** at LDAP login (`ldap_service.py:647` `role = await group_mapper.resolve_role(...)` then `sync_user`) and admin-triggered `sync_all` (`:493`), and at SAML ACS (`saml_service.py:415`). `sync_user`/`provision_user` set `doc["role"] = role` for existing and new users, then `revoke_user_sessions` on change.
- **Enforcement design (one shared helper):** (a) write time: call `assert_can_assign_role` from both endpoints with `target_tenant_id = _config_scope(...)` result or caller tenant; (b) apply time: refuse the super-admin tier unconditionally and log; (c) optionally store `created_by` / `created_by_role` on new mapping docs for audit (additive, no migration). The two mapper classes' `upsert_mapping` static methods keep their signatures (tests call them directly).
- **Not covered by a ceiling, noted:** an LDAP/SAML mapping can overwrite an existing user's role (including demoting a tenant admin) because `if role: doc["role"] = role` has no guard; the docstring calls it intended. Leave as is; mention to Phase 77 / backlog.

## `manage:tenants` Consumers and the Bundle Finding (Question 4)

**Backend** `[VERIFIED by grep this session]`: `rbac_utils.py:112` (`Tenant Admin` default), `rbac_service.py:82` (`Tenant Admin` default), `app_startup.py:320` (Super Admin doc `all_permissions`), `bundle_endpoints.py:127/177/220` (`_=Depends(require_permission("manage:tenants")),`), plus archived scripts. No other backend route checks the string. `tenant_endpoints.py` never uses `manage:tenants`: its writes are guarded by `is_super_admin` or own-tenant checks (`update_tenant` `:160-171`: non-super can only touch their own tenant and cannot change tier/features; `:323-325`, `:369-375`, `:599-605` own-tenant admin role checks).

**Frontend** `[VERIFIED by grep]`: `App.tsx:263` (`tenantManagement: 'manage:tenants'`), `App.tsx:412` (`bundleManagement: 'manage:tenants'`), `components/Sidebar.tsx:430-431` (both nav items), `Sidebar.tsx:450` (hide when viewing a tenant), `components/BundleManagementDashboard.tsx:4` ("Only accessible to Super Admin (manage:tenants permission)"), `RoleEditorModal.tsx:133` and `constants.ts:80`/`data.ts:32` (already strip `manage:tenants` from tenant roles: the frontend intent already was super-admin only). Label maps only: `TenantFeatureManagement.tsx:33`, `ManageTenantModal.tsx:37`, `RoleEditorModal.tsx:35,60`.

**Finding D-06 CONFIRMED from code (not live-tested):** `[VERIFIED: bundle_endpoints.py:120-153]` `@router.put("/tenant/{tenant_id}/assign")` ... `_=Depends(require_permission("manage:tenants")),` ... `tenant = await db.tenants.find_one({"id": tenant_id})` ... `await db.tenants.update_one(\n        {"id": tenant_id},` with `"assignedBundles": body.assigned_bundles,`; there is no check that `tenant_id` equals the caller's tenant. `[VERIFIED: database.py:31,148-149]` `"tenants",` is in the exempt set and `if name in TENANT_ISOLATION_EXEMPT_COLLECTIONS:\n            return collection`. `[VERIFIED: rbac_utils.py:112]` the default `Tenant Admin` set grants `manage:tenants`. So any Tenant Admin can overwrite any tenant's bundle assignment (PATCH and DELETE equally, `:170-231`).
**Are the three routes the only cross-tenant write surface on `tenants`?** Among `db.tenants.update_*` writers keyed by a request-supplied tenant id, yes: `payment_billing_endpoints.py` (`tenant_id = current_user.tenant_id`), `trust_endpoints.py:70-75` (own tenant), `finops_endpoints.py:80` (`caller_tenant`), and `tenant_endpoints.py` writes are each super-admin or own-tenant guarded. One read-side observation (not in scope, record for Phase 76): `GET /api/bundles/tenant/{tenant_id}/features` (`bundle_endpoints.py:83-117`) lets any authenticated user read any tenant's bundle/feature configuration.
**Fix:** replace the three `require_permission("manage:tenants")` with `require_super_admin` (`rbac_utils.py:228`, which already exists), and remove the string from the tenant-admin defaults. Fix the docstring at `:131` ("Super Admin / Tenant Admin"). Regression tests (must fail on pre-fix code): a Tenant Admin token for tenant A gets 403 on PUT/PATCH/DELETE `/api/bundles/tenant/B/assign` and on its own tenant; a Super Admin token gets 200.

## Seeding (Question 5)

- **How it seeds today:** `seed_database()` takes `db = get_database()` (the wrapper, `app_startup.py:233`) and does `update_one({"name": ...}, {"$set": {...}}, upsert=True)` three times: Super Admin `:353-364` (`"tenantId": "platform"`), Tenant Admin `:414-425` (`"tenantId": "all"`), five standard roles `:521-526` (`"tenantId": "all"`).
- **ContextVar at that moment:** `[VERIFIED: backend/app.py:31-32]` `set_tenant_id("platform-admin")` / `await seed_database()` -> the wrapper returns `filter_query` unchanged for `"platform-admin"` (`database.py:51-52`). So the filter is `{"name": X}` across ALL tenants. **Yes, it can currently match a tenant-scoped doc** (reproduced, finding 3).
- **Correct form:** raw handle with an explicit tenantId: `db._db.roles.update_one({"name": n, "tenantId": t}, {"$set": doc}, upsert=True)` where `t` is `"all"` for every role except Super Admin (Open Question 2). `find_role_doc` already uses `db._db` for exactly these two sentinels (`rbac_service.py:27-30`).
- **Idempotency/no duplicates:** verified: second run `matched 1`, no new doc. No unique index on `roles` is created anywhere (`database_migrations.py` has no roles entry `[VERIFIED: grep]`), so the filter is the only uniqueness guard; consider an optional `roles` compound unique index on `(tenantId, name)` only if a migration step already exists for such things (not required).
- **Doc shape to keep:** the seven live docs carry `id`, `name`, `description`, `permissions`, `isEditable`, `tenantId` (plus `display_name` on the five standard roles). Keep `isEditable: False` for Super Admin / Tenant Admin / `admin`, and decide `isEditable` for the ITAM docs (recommend `False`: they are table-owned and reset on restart, so "editable" would be a lie — and the Roles tab disables Edit when false, `SettingsRolesTab.tsx:46`).
- **Compliance heuristics:** `compliance_service.py:30` and the `frameworks/*` checks call `roles.count_documents({})` as an "RBAC configured" heuristic; going from 7 to 11 docs cannot flip a >0 check `[ASSUMED]` (not opened individually).

## Role-Writing One-Off Scripts (Question 6)

`[VERIFIED: head/grep of each file and a repo-wide grep for references, this session]`

| Script | Writes role permissions? | Referenced/invoked elsewhere? | Disposition |
|--------|--------------------------|-------------------------------|-------------|
| `fix_rbac.py` | **No** (regex-strips `@rbac_service...` decorator lines out of `app.py`) | none | **Do not archive under D-14's criterion** (not a role writer). Optional separate cleanup. |
| `fix_all_rbac.py` | **No** (rewrites endpoint source files) | none | same |
| `fix_rbac_integrations.py` | **Yes** (`db.roles.update_one` -> `Tenant Admin` += `view:integrations`) | none | archive |
| `update_sbom_roles.py` | **Yes** (`$addToSet` view/manage:sbom on roles) | none | archive |
| `update_all_sbom_roles.py` | **Yes** (`update_many`; even adds `"*"` to Super Admin variants) | none | archive |
| `enable_compliance_for_admin.py` | **Yes** (`db.roles.update_one` `$addToSet view:compliance`; also `users.permissions.*`) | none | archive |
| `reset_db_fresh.py` | **Yes** (`db.roles.insert_one` for Tenant Admin / Super Admin, `"permissions": enterprise_permissions + ["manage:tenants"]`; also drops/reseeds data) | none | archive |
| `unlock_enterprise_features.py` | **No** (writes `tenants.enabledFeatures` tier list) | **YES**: `deploy-ubuntu.sh:366` and `run-on-ubuntu.sh:429` run `python3 unlock_enterprise_features.py` | **Do NOT move** (would break both deploy scripts; it is a tier tool, out of scope) |
| `diagnose_rbac.py` | read-only | — | stays (calls `rbac_service.get_user_permissions`, keep that name) |

A repo-wide search for any other role writers found only these plus `app_startup.py` (`grep -rlE "roles\.(update_one|update_many|insert_one|insert_many|replace_one|find_one_and_update)"` over `backend/` and `scripts/`). **Archive location:** the project convention is a top-level `archive/<name>/` folder each with an `ARCHIVED.md` explaining why `[VERIFIED: archive/agent-rust/ARCHIVED.md, archive/backend-nested-copy/ARCHIVED.md exist]`; CLAUDE.md's "scripts under /scripts" is for new files, not for retired ones. Use `archive/backend-rbac-oneoffs/` (use `git mv` to preserve history) and write an `ARCHIVED.md` (why: they hand-write role permission lists that drift from `rbac_defaults.py`, what replaces them: the startup seed). The drift test scans only top-level `backend/*.py`, so the archive is excluded automatically.

## Frontend (Question 7)

- **Fallback to delete:** `App.tsx:1213-1230` (branch starts at `} else {` + comment `// Fallback to role-based lookup (case-insensitive)` at 1214, looks up `roles.find(...)`, treats `role.permissions.includes('all')` as everything, and closes with `// If no role found, effectiveFeatures stays [] ...` at 1229).
- **`fetchRoles`/`roles` consumers** `[VERIFIED: grep]`: `App.tsx:564` state, `:695` `api.fetchRoles()`, `:724` `setRoles(getResult(1, []))`, `:1242` memo deps, `:1618/1628` `handleSaveRole`/`handleDeleteRole` (client-memory only), `:1861` passes `roles` to `SettingsDashboard`; components `AddUserModal.tsx:24,77` (default `roles.find(r => r.name === 'Tenant Admin')?.name || roles[0]?.name`, dropdown value = `r.name`), `EditUserModal.tsx:62` (dropdown value = `r.name`), `SettingsRolesTab.tsx:33,46` (uses `role.isEditable`). Therefore `GET /api/roles` must return `name` values the backend accepts (`_normalize_role(name)` in the valid set), plus `id`, `description`, `permissions`, `isEditable`, `tenantId` (`types.ts:361-368` `Role` type) so no field is `undefined`. `Super Admin` entry shown only to super-admins. The live user-role strings are `Tenant Admin` / `viewer` / `Super Admin`, so keep display names `Tenant Admin`, `Super Admin` for those entries and canonical keys for the rest.
- **Does a 403 from `/api/roles` break loading?** No. `[VERIFIED: App.tsx:693-695]` (`const results = await Promise.allSettled([` / `api.fetchUsers(), api.fetchRoles(), ...`) the load uses `Promise.allSettled([...])` (not `Promise.all`) with `getResult(index, fallback)` (`:709-717`), and `[VERIFIED: apiService.ts:421-446]` `fetchWithCache` throws on `!res.ok`, then catches, reads `sessionStorage` `omni_cache_roles`, else returns `[]`. One subtlety: the cache survives logout within a tab (logout only reloads the page, `App.tsx:871-876`; sessionStorage persists), so a non-admin user logging in after an admin in the same tab would be shown the previous admin's cached role list. After D-17 the list no longer drives permissions, but to avoid leaking it either clear `omni_cache_roles` on logout/login or skip the cache fallback when the status is 403. Small, recommended.
- **Login double-call (FYI):** `LoginPage.handleLogin` calls `api.login`, then `onLogin` -> `App.handleLogin` calls `api.login` again (`LoginPage.tsx:153-176`, `App.tsx:791-793`); harmless but it doubles the lockout counters on failure. Not in scope.

## Super-Admin Wildcard (Question 9)

`[VERIFIED: grep for '*' / "*" in App.tsx, components/Sidebar.tsx, services/ this session]`: no frontend code treats `"*"` specially; the only wildcard-ish token is `'all'` (`App.tsx:1220` in the branch D-17 deletes, and `:1236`). Super-admins are short-circuited by NAME before any permission list is read: memo `:1189` (`Super Admin`/`superadmin`/`super_admin` -> `hasPermission: () => true`) and `checkPermission` `:1232-1238` (adds `platform-admin`). A `platform-admin` user falls through the first check, gets `["*"]`, intersects it with tenant `enabledFeatures` (-> `[]`), and then `checkPermission`'s name check returns true. Therefore returning `["*"]` for all four variants cannot break the UI before Phase 77. No component reads `currentUser.permissions` directly (`App.tsx:1202-1204` is the only reader). Sidebar uses the context `hasPermission`. Tests: no existing vitest touches this derivation.

## Test Infrastructure (Question 8)

- **Backend runner:** `backend/venv/bin/python -m pytest backend/tests/<file> -q -p no:cacheprovider` from the repo root (rootdir resolves to `backend/` via `backend/pyproject.toml`; root `pytest.ini` sets `asyncio_mode = auto`, `addopts = -v`). `backend/tests/conftest.py` pins `MONGODB_DB_NAME` to a throwaway `omni_test_<pid>` database and drops it at session end; a real MongoDB is reachable on localhost (some tests, e.g. `test_000_router_smoke.py`, use it and skip when it is down).
- **How RBAC/auth tests are written:** (a) `test_rbac.py` builds a `MagicMock` db with `db._db = db` and `db.roles.find_one = AsyncMock(...)`, patches `rbac_service.get_database` / `rbac_utils.get_database`, calls `asyncio.run(...)` and uses `TestClient` with `app.dependency_overrides[get_current_user]`; (b) `test_auth_mfa.py` `_make_db_mock` gives separate `raw_db` (`db._db`) and wrapper objects, mounts `authentication_endpoints.router` on a minimal app with a fresh slowapi limiter, and resets the shared limiter storage in an autouse fixture (needed for any new `/login` test); (c) `test_find_role_doc.py` asserts the wrapper vs raw split; (d) `test_user_crud.py` uses a `FakeDB` + `httpx.AsyncClient` + `make_token_data`, patching `itam_asset_endpoints.verify_permission`; (e) `test_sso_config_without_tenant_context.py` runs the REAL `TenantIsolatedDatabase` over an in-memory `_Collection` in a fresh `contextvars.Context` (the right model for the `/login`-vs-`/me` and seed tests; its `_Collection.update_one` does not implement upsert, extend it).
- **Existing helpers to reuse:** `tests/conftest.py` `make_token_data(...)`; ITAM `*_test_support.py` modules (convention: put a new `tests/rbac_test_support.py` with the in-memory roles/users store and `login`/`me` app builder).
- **Baselines (this session):** `test_rbac.py test_find_role_doc.py test_user_crud.py test_seed_database_step_isolation.py test_auth_mfa.py test_admin_mfa_required.py` -> **120 passed** (5.9 s). `test_ldap_service.py test_sso_saml.py test_bundles_and_reports.py test_prod_hardening.py test_tenant_boundary_hardening.py test_tenant_isolation.py test_route_auth_baseline.py test_remote_access.py test_api_key.py test_session_revocation.py` -> **315 passed, 1 skipped** (19.7 s). Frontend `npx vitest run src/__tests__` -> **26 files / 186 tests passed** (6.4 s). Full-suite baseline: see Validation Architecture.
- **Frontend runner:** `npx vitest run src/__tests__` (config `test_command` in `.planning/config.json`; vite config include also covers `servers/**`), build `npm run build` (`vite build`), lint `npm run lint` is `eslint . --max-warnings 0` (bulk lint is deferred per project memory; lint only changed files).
- **`test_route_auth_baseline.py`** walks every mounted route in a fresh interpreter. A new `GET /api/roles` must carry `Depends(get_current_user)`-family auth (it will). Its permission dependency name should start with `require_`/`_require_` so the baseline's `PERM_DEP` regex recognises it (only matters for mutating routes today, but keeps the pattern).

## Common Pitfalls

### Pitfall 1: Enforcement and delivery diverge again
**What goes wrong:** the resolver is used by `/login` but `verify_permission` keeps its own literal.
**How to avoid:** `DEFAULT_PERMISSIONS` literal is deleted in the same plan; drift test fails if any role->permission literal reappears outside `rbac_defaults.py`.
**Warning signs:** `grep -n "\"view:" backend/rbac_utils.py` returns hits.

### Pitfall 2: `/login` own-tenant doc lookup silently never matches
**What goes wrong:** copy `find_role_doc(db, role, tenant_id)` into the new resolver and `/login` ignores tenant-scoped docs while `/me` honours them.
**Why:** `/api/auth/login` is a public path (no ContextVar); the wrapper then rewrites the filter's `tenantId` to the "NON_EXISTENT..." sentinel.
**How to avoid:** raw handle + explicit tenantId; test `/login` == `/me` with a tenant-scoped doc present (the test the success criterion asks for must include this case, not only shared docs).

### Pitfall 3: Seed overwrites a tenant's role / duplicates docs
**How to avoid:** `{name, tenantId}` filter on the raw handle; test with a tenant doc named `viewer` present before seeding and assert it is untouched and run seeding twice and assert 11 shared docs.

### Pitfall 4: Order-sensitive and set-sensitive existing assertions
**What goes wrong:** sorted/set outputs break `perms == [...]` tests; adding `view:profile` breaks the two ITAM `set(perms) ==` tests.
**How to avoid:** stable "defaults then doc extras" order; update the two ITAM tests deliberately (D-08).

### Pitfall 5: Ceiling blocks legitimate flows
**What goes wrong:** with a strict subset rule a Tenant Admin can no longer create an `itam_admin` user (they can today) and `itam_admin` cannot create `itam_user`.
**How to avoid:** resolve Open Question 1 before coding; unit-test the full caller x target matrix.

### Pitfall 6: Cached or stale tokens after role change
Already handled (`revoke_user_sessions` on role change in `user_endpoints.py:393-402` and in LDAP/SAML sync). Do not add new session logic; make sure the new self-change guard does not break the "role change revokes sessions" test (`tests/test_session_revocation.py`).

### Pitfall 7: Super-admin tier decided by wildcard presence
Keep the super-admin-tier rule name-based (`is_super_admin`), never "role has `*`".

### Pitfall 8: Drift test false positives
The AST scan will flag `seed_demo_data.py:34` (8 per-user permission strings) and the tier lists. Maintain an explicit allowlist file-and-reason map in the test (see Validation Architecture) rather than loosening the thresholds.

## Code Examples

### Drift test (AST, no grep)
```python
# backend/tests/test_rbac_defaults.py  (sketch; thresholds verified against current tree, see Appendix B)
import ast, glob, os, re
PERM = re.compile(r'^(view|manage|export|remediate|investigate|request|control|admin|read|write|delete):[A-Za-z_*:.\-]+$')
BACKEND = os.path.join(os.path.dirname(__file__), "..")
ALLOWED = {  # file -> reason (tier lists / per-user arrays are a different concept)
    "rbac_defaults.py": "the single table",
    "authentication_endpoints.py": "free_features is a tenant tier list (line ~318)",
    "tenant_endpoints.py": "TenantCreate.enabledFeatures tier list",
    "seed_demo_data.py": "tenant tiers + ignored per-user permissions array",
    "unlock_enterprise_features.py": "tenant tier list (deploy scripts run it)",
}
def test_no_second_role_permission_table():
    offenders = []
    for path in sorted(glob.glob(os.path.join(BACKEND, "*.py"))):      # top level only: skips tests/, venv*/, archive
        name = os.path.basename(path)
        if name in ALLOWED:
            continue
        for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
            if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                strs = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if len(strs) >= 5 and sum(bool(PERM.match(s)) for s in strs) / len(strs) >= 0.8:
                    offenders.append(f"{name}:{node.lineno}")
    assert not offenders, f"permission-list literals outside rbac_defaults.py: {offenders}"
```
Note: `authentication_endpoints.py` and `tenant_endpoints.py` are allowlisted wholesale for their tier lists; to avoid hiding a new role list there, prefer allowlisting by `(file, lineno-range)` or by variable name (`free_features`, `enabledFeatures`) instead of by file.

### Seed test skeleton (real wrapper, platform-admin ctx, in-memory raw db)
```python
# Build TenantIsolatedDatabase(_RawDB(roles=_Collection([{"name":"viewer","tenantId":"tenant_x","permissions":["custom:only"]}])))
# with a fresh contextvars.Context where set_tenant_id("platform-admin") is called, run seed_database() twice,
# assert: 11 docs with tenantId in {"all","platform"}; tenant_x doc unchanged; second run adds nothing.
```
(Extend the fake `update_one` to implement `upsert=True` with `$set`.)

### Bundle regression test skeleton
```python
# Tenant Admin token (role="Tenant Admin", tenant_id="tenant-a") against PUT/PATCH/DELETE /api/bundles/tenant/tenant-b/assign
# -> expect 403 using the REAL rbac_utils.require_super_admin (do not patch verify_permission to True as test_bundles_and_reports.py does today).
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Three literal tables + three seed lists | One table, mirrored to shared docs each boot | this phase | single source; drift test |
| `/login`,`/me` return raw doc perms or `[]` | resolver (defaults ∪ docs) | this phase | no empty ITAM sidebars |
| `{"name": X}` seed upserts via wrapper | `{name, tenantId}` raw-handle upserts | this phase | no tenant-doc hijack |
| Only `super_admin` blocked from assignment | subset ceiling + no self-change | this phase | closes the itam_admin -> admin/super_admin paths |

**Deprecated/outdated:** the `/api/roles` static stub (`role_endpoints.py`, 39 lines, `Admin` = `["all"]`); `'all'` handling in `App.tsx` (the branch that creates it is deleted; the `checkPermission` `'all'` line can remain until Phase 77).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Going from 7 to 11 role docs cannot flip the `roles.count_documents({}) > 0` compliance heuristics (`compliance_service.py:30`, `frameworks/*`); individual checks not opened | Seeding | Low: a compliance score could shift if a check uses `==` or a threshold |
| A2 | Option A for Open Question 1 (tenant-admin set gains `manage:licenses`, `manage:users`, `manage:procurement`, `manage:finance`, and ceiling closure `manage:X -> view:X, request:X`) is acceptable product behaviour | Open Question 1 | Medium: changes real tenant-admin power (ITAM procurement/finance/licenses) — needs user confirmation before plans lock |
| A3 | `isEditable: False` for the four new docs (`admin`, `itam_*`) is the right display behaviour | Seeding | Low: UI-only |
| A4 | Keeping the `Super Admin` doc at `tenantId:"platform"` (rather than `"all"`) is preferred | Open Question 2 | Low: either works; "all" leaves an orphan "platform" doc |
| A5 | Live behaviour of `GET /api/bundles/...` cross-tenant write is as read in code (not exercised live per instructions) | Key Findings | Low: code path is unambiguous; regression test proves it |

## Open Questions

1. **D-18 ceiling vs D-11 / "tenant admins can assign everything but super-admin" (BLOCKING for plan lock).**
   - What we know (scripted matrix, NEW sets, row = target, column = caller; `True` = target ⊆ caller): `admin`/`Tenant Admin`/`user`/`analyst`/`security_analyst`/`incident_responder`/`viewer` are all ⊆ `Tenant Admin` (good). But `itam_admin` ⊄ `Tenant Admin` (missing `manage:finance manage:licenses manage:procurement manage:users`), `itam_user` ⊄ `Tenant Admin` (missing `request:assets view:licenses`), `itam_viewer` ⊄ `Tenant Admin` (missing `view:licenses`); `itam_user` ⊄ `itam_admin` (missing `request:assets view:assets view:licenses`) and `itam_viewer` ⊄ `itam_admin` (missing `view:assets view:licenses`). Only `itam_viewer ⊆ itam_user`. Literal D-18 therefore forbids tenant admins from assigning any ITAM role and itam_admin from assigning itam_user/itam_viewer, contradicting D-18's own examples.
   - Options: **A (recommended):** (i) ceiling comparison treats `manage:X` as implying `view:X` and `request:X` (closure applied to the caller's set only); (ii) add the four ITAM manage strings plus `view:licenses` and `request:assets` to the tenant-admin defaults (6 strings; note tenant admins currently get 403 on `itam_procurement_endpoints` because `manage:procurement` is in no tenant-admin table — this also fixes that). Needs user sign-off because D-02 said "no other role gains anything from this step" and this changes tenant-admin ITAM power. **B:** a rank/`ASSIGNABLE_BY` field in the single table (super_admin > tenant_admin/admin > itam_admin > everything else) with subset checks used only as a sanity invariant; no permission changes. **C:** ceiling over privilege verbs only (`manage:*`, `control:*`, `remediate:*`, `investigate:*`, `export:*`, `admin:*`), ignoring `view:*`/`request:*`; still needs the 4 manage strings on tenant admins.
   - Recommendation: take A (or B if the user does not want tenant-admin power changed); implement the helper so the rule is data-driven and the matrix is a parametrized test.
2. **Super Admin doc location.** Keep `tenantId:"platform"` (matches live data and `find_role_doc`'s sentinel list) and seed `{name:"Super Admin", tenantId:"platform"}`, or move to `"all"` per the literal D-12/D-13 wording (creates a second doc; the old one stays until manually removed)? Recommendation: keep `"platform"`; give each seed entry its own doc tenantId.
3. **Super-admin doc contents.** Mirror `["*"]` into the Super Admin doc, or keep the 96-string list incl. `admin:*`? `["*"]` makes the table the only truth; the Roles tab would show `*`. Recommendation: `["*"]`.
4. **`itam_admin` + `manage:itam`** (Claude's discretion in CONTEXT): recommend yes (harmless; matches API-key scope naming `rbac_service._ROLE_ADMIN_GATING_SCOPE` -> `admin:itam`). If added, update the ITAM sizes in the golden test (itam_admin 8).
5. **Self-role-change strictness:** reject any `role` field targeting self, or only a differing role? `EditUserModal` only sends a role when it changed (`EditUserModal.tsx:24-26`), so "differing role" is safe. Recommend "differs after normalization".

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv (`backend/venv`) | all backend work/tests | yes | 3.12.3 | — |
| pytest + pytest-asyncio | tests | yes | 9.1.1 / 1.4.0 | — |
| MongoDB (localhost) | optional real-DB tests, seed semantics check | yes (read-only inventory and a throwaway-DB upsert check succeeded) | server reachable | in-memory fakes |
| `mongomock_motor` | in-memory Motor | **no** | — | hand-rolled `_Collection` fake (existing pattern) |
| Node / npm / vitest | frontend build + tests | yes | node v24.21.0, vitest 5.0.0 | — |
| `graphify` knowledge graph | graph context step | not consulted (no `gsd_run` shim needed; direct code reading used) | — | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `mongomock_motor` (use fakes).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`) |
| Backend config | root `pytest.ini`; `backend/pyproject.toml` (rootdir); `backend/tests/conftest.py` |
| Frontend framework | vitest 5.0.0 + jsdom + @testing-library/react (`src/__tests__/setup.ts`) |
| Quick run (backend) | `backend/venv/bin/python -m pytest backend/tests/test_rbac_defaults.py backend/tests/test_effective_permissions.py backend/tests/test_login_me_permissions.py backend/tests/test_role_seeding.py backend/tests/test_roles_endpoint.py backend/tests/test_role_assignment_ceiling.py backend/tests/test_rbac.py backend/tests/test_find_role_doc.py -q -p no:cacheprovider` |
| Phase-affected suite | `backend/venv/bin/python -m pytest backend/tests/test_rbac.py backend/tests/test_find_role_doc.py backend/tests/test_user_crud.py backend/tests/test_seed_database_step_isolation.py backend/tests/test_auth_mfa.py backend/tests/test_admin_mfa_required.py backend/tests/test_ldap_service.py backend/tests/test_sso_saml.py backend/tests/test_bundles_and_reports.py backend/tests/test_prod_hardening.py backend/tests/test_tenant_boundary_hardening.py backend/tests/test_tenant_isolation.py backend/tests/test_route_auth_baseline.py backend/tests/test_remote_access.py backend/tests/test_api_key.py backend/tests/test_session_revocation.py -q -p no:cacheprovider` (baseline 435 passed / 1 skipped across the two batches, ~28 s) |
| Full backend suite | `backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` (baseline `[VERIFIED: run this session]`: **2878 passed, 47 skipped, 0 failed, 141.8 s**; no pre-existing failures to exclude) |
| Frontend | `npx vitest run src/__tests__` (baseline 26 files / 186 tests); `npm run build` |

### Phase Requirements -> Test Map
| Req ID | Behavior (success criterion) | Test Type | Automated Command | File Exists? |
|--------|------------------------------|-----------|-------------------|-------------|
| ACC-01 | SC1: each of `itam_admin/itam_user/itam_viewer` gets a non-empty list from BOTH `/login` and `/me` | integration (real wrapper over in-memory store) | `pytest backend/tests/test_login_me_permissions.py -q` | Wave 0 |
| ACC-01 | SC2: `/login` == `/me` for the same user, for every built-in role, with and without a tenant-scoped doc, super-admin -> `["*"]` | integration | same file | Wave 0 |
| ACC-01 | resolver unit: union, order stability, normalization (`Admin`, `tenant_admin`, `platform-admin`), unknown role -> `[]` + warning, role-store error -> defaults only (login) / deny (verify_permission), custom doc passthrough | unit | `pytest backend/tests/test_effective_permissions.py -q` | Wave 0 |
| ACC-01 | MFA verify-login and signup responses carry resolver permissions; signup no longer stores `permissions` on the user record (D-07) | integration | `pytest backend/tests/test_login_me_permissions.py -k "mfa or signup" -q` | Wave 0 |
| ACC-02 | SC3: exactly one table; AST drift test; `control:remote_access` != `view:remote_access` and a doc granting only `view:remote_access` does NOT pass `verify_permission(..., "control:remote_access")`; D-03 six absent from every tenant role; `manage:tenants` absent from all non-super roles; `admin` == `tenant_admin` set | unit | `pytest backend/tests/test_rbac_defaults.py -q` | Wave 0 |
| ACC-02 | per-role gained/lost golden (sizes 121/121/22/19/17/12/8/7/5/4 and the lists above) | unit | same file | Wave 0 |
| ACC-02 | SC4: after `seed_database()` the 11 shared docs exist (Super Admin at its sentinel), `isEditable`/ids set, idempotent on 2nd run, tenant-scoped same-name doc untouched; an admin's role list contains the ITAM roles | integration | `pytest backend/tests/test_role_seeding.py backend/tests/test_roles_endpoint.py -q` | Wave 0 |
| ACC-02 | pre-existing custom role (no defaults) still resolves from its doc; no migration | unit | `test_effective_permissions.py::test_custom_role_unchanged` | Wave 0 |
| D-06 | Tenant Admin 403 on PUT/PATCH/DELETE `/api/bundles/tenant/{other}/assign`; Super Admin 200 | integration | `pytest backend/tests/test_bundles_and_reports.py -q` (extended) | updated |
| D-18 | caller x target matrix; itam_admin 403 assigning `admin`/`Tenant Admin`; self role change 403; LDAP and SAML `group-mapping` writes obey the ceiling; `super_admin` mapping refused; apply-time super-admin block | integration | `pytest backend/tests/test_role_assignment_ceiling.py backend/tests/test_user_crud.py backend/tests/test_ldap_service.py backend/tests/test_sso_saml.py -q` | Wave 0 + updated |
| D-15/16 | `GET /api/roles`: built-ins + own-tenant docs only, effective perms equal `/me`, `Super Admin` hidden from non-super, 403 for `viewer`/`itam_viewer`, 200 for `manage:users` OR `manage:rbac` | integration | `pytest backend/tests/test_roles_endpoint.py -q` | Wave 0 |
| D-17 | empty `currentUser.permissions` -> every non-super `hasPermission` false (no roles fallback) | unit (vitest, needs the small pure-function extraction) or build-only | `npx vitest run src/__tests__/permissions.test.ts` ; `npm run build` | Wave 0 (optional extraction) |
| existing | route auth baseline still green with the real `/api/roles` | integration | `pytest backend/tests/test_route_auth_baseline.py -q` | exists |

### Sampling Rate
- **Per task commit:** the Quick run command (backend) for the task's files, `< 30 s`.
- **Per wave merge:** the Phase-affected suite + `npx vitest run src/__tests__` + `npm run build` after any frontend change.
- **Phase gate:** full backend suite and full vitest suite green before `/gsd-verify-work`, compared against the baselines recorded here.

### Wave 0 Gaps
- [ ] `backend/tests/rbac_test_support.py` — in-memory roles/users/tenants store (with `update_one` upsert + `$set`), `login`/`me` app builder, token factory
- [ ] `backend/tests/test_rbac_defaults.py` — drift AST test, invariants, golden per-role sets
- [ ] `backend/tests/test_effective_permissions.py`
- [ ] `backend/tests/test_login_me_permissions.py`
- [ ] `backend/tests/test_role_seeding.py` (and edit `test_seed_database_step_isolation.py` to the raw handle + 11 names)
- [ ] `backend/tests/test_roles_endpoint.py`
- [ ] `backend/tests/test_role_assignment_ceiling.py`
- [ ] Edits to existing tests listed in "Existing tests that encode the OLD behaviour"
- [ ] Optional: `utils/permissions.ts` + `src/__tests__/permissions.test.ts`
- Framework install: none.

## Security Domain

`security_enforcement` is enabled (`.planning/config.json`: `"security_enforcement": true`, `"security_asvs_level": 1`, `"security_block_on": "high"`).

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (session mint paths) | existing JWT + MFA flows; only the permission payload changes |
| V3 Session Management | yes | existing `revoke_user_sessions` on role change; no new session logic |
| V4 Access Control | **yes (primary)** | single resolver; `require_super_admin`; subset-ceiling helper; deny-by-default frontend |
| V5 Input Validation | yes | role strings normalized via `_normalize_role` and validated against the table (Pydantic models already present) |
| V7 Error Handling & Logging | yes | D-19 warning naming the role; log mapping rejections; no secrets in logs |
| V8/V13 API & Web Service | yes | `GET /api/roles` gated by `manage:users` OR `manage:rbac` |
| V6 Cryptography | no | none touched |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Tenant Admin rewrites another tenant's bundles (D-06) — **CONFIRMED by code** (`bundle_endpoints.py:120-153`, `database.py:31,148-149`, `rbac_utils.py:112`) | Tampering / Elevation | `require_super_admin` on the 3 routes + remove `manage:tenants` from tenant defaults; regression tests |
| itam_admin promotes self/others to admin/Tenant Admin (D-18) — **CONFIRMED by code** (`user_endpoints.py:269-274` and `:347-353` block only `super_admin`; `itam_admin` holds `manage:assets` -> `_require_itam_admin_session_only`; no self-change check) | Elevation | shared `assert_can_assign_role` (subset ceiling, no self change) |
| itam_admin maps a directory group to `super_admin` (new, stronger) — **CONFIRMED by code** (finding 5) | Elevation | ceiling at write + hard block at apply |
| Seed upsert overwrites/re-labels a tenant's role doc | Tampering | `{name, tenantId}` raw-handle filter; test |
| Wildcard in a tenant doc used as super-admin signal | Elevation | name-based super-admin rule only |
| Role-store outage grants access | Elevation | keep fail-closed in `verify_permission`; `/login` degrades to defaults (never grants more than the table) |
| Stale cached role list shown to another user in the same tab | Information disclosure (low) | clear `omni_cache_roles` on logout/403 |
| `GET /api/bundles/tenant/{id}/features` reads any tenant | Information disclosure (low, out of scope) | record for Phase 76 |

No exploitation was performed against live services. The only live-system interactions were a read-only `find` on `roles`/`users` and an insert/update/drop confined to a uniquely named throwaway database that was dropped.

## Project Constraints (from CLAUDE.md)

- Do what has been asked; prefer editing existing files; no documentation files unless requested; never save working files/tests to repo root — use `/src`, `/tests`, `/docs`, `/config`, `/scripts` (backend tests live in `backend/tests/`; the archive folder follows the existing `archive/` convention).
- Always read a file before editing; never commit secrets; keep files under 500 lines (`app_startup.py` is 834 lines and `rbac_utils.py` 247: deleting the three literal blocks and the `DEFAULT_PERMISSIONS` literal shrinks both; do not grow `app_startup.py`; put new code in `rbac_defaults.py` / `rbac_service.py`).
- Validate input at system boundaries (role strings on user CRUD/mappings, `/api/roles` query-less).
- Always run tests after code changes; `npm run build && npm test` before committing.
- Commit trailer: the system reminder in this session specifies the `Co-Authored-By: Claude Sonnet 5.5` trailer for commits; CLAUDE.md says not to add one unless `.claude/settings.json` sets `attribution.commit` — resolve per the project's actual setting at commit time.
- Memory-derived constraints: secrets and service restarts are the user's; archive, never delete; bulk lint/tests deferred (run only the touched files); the seed and role changes take effect only after a backend restart by the user; Oct-2026 fail-closed prod mode on restart and tenant DB-wrapper behaviour (`admin` is a tenant role) apply.

## Sources

### Primary (HIGH confidence) — files read in full or in the cited ranges this session
- `backend/rbac_utils.py` (1-247), `backend/rbac_service.py` (1-285), `backend/app_startup.py` (215-575), `backend/database.py` (1-462), `backend/authentication_endpoints.py` (1-552), `backend/user_endpoints.py` (1-443), `backend/bundle_endpoints.py` (1-230), `backend/role_endpoints.py` (1-39), `backend/ldap_service.py` (405-660), `backend/ldap_endpoints.py`, `backend/sso_endpoints.py` (340-400), `backend/saml_mapping.py` (30-200), `backend/saml_service.py` (395-470), `backend/mfa_endpoints.py` (210-240), `backend/tenant_endpoints.py`, `backend/tenant_middleware.py`, `backend/tenant_context.py`, `backend/app.py` (15-50), `backend/itam_asset_endpoints.py` (30-120), `backend/api_key_auth.py`, `backend/auth_roles.py`, `backend/zero_trust_service.py` (285-340)
- Frontend: `App.tsx` (680-735, 788-870, 930-960, 1175-1250, 1605-1635), `services/apiService.ts` (405-470, 585-720, 2680-2710), `types.ts` (Role, permissions), `components/AddUserModal.tsx`, `EditUserModal.tsx`, `SettingsRolesTab.tsx`, `LoginPage.tsx`
- Tests read: `backend/tests/test_rbac.py`, `test_find_role_doc.py`, `test_seed_database_step_isolation.py`, `test_auth_mfa.py` (1-140, 315-380), `test_user_crud.py` (1-215), `test_route_auth_baseline.py` (1-140), `test_sso_config_without_tenant_context.py`, `test_000_router_smoke.py`, `conftest.py`
- Scripts: all eight D-14 candidates plus `diagnose_rbac.py`, `seed_demo_data.py`; `archive/agent-rust/ARCHIVED.md`
- Executed this session: AST diff generator (Appendix A), AST literal scan (Appendix B), read-only role/user inventory on the local MongoDB, throwaway-database upsert experiment (dropped), the baseline test runs listed above.

### Secondary / Tertiary
- None. No web sources were needed; all claims are in-repo.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies.
- Architecture: HIGH — every integration point read; the only open item is the ceiling rule (Open Question 1).
- Pitfalls: HIGH — two of them were reproduced (seed hijack) or derived from verified middleware/wrapper behaviour (`/login` ctx).

**Research date:** 2026-10-12
**Valid until:** 2026-11-12 (stable internal code; re-check if `app_startup.py`, `rbac_*`, or `authentication_endpoints.py` change before planning)

## Appendix A: Per-role diff generator (AST; reads literals from the three source files)

```python
import ast
B = "/home/azureuser/enterprise-omni-agent-ai-platform/backend/"
def assign(path, name=None, attr=None):
    for n in ast.walk(ast.parse(open(B + path).read())):
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            tg = n.targets[0] if isinstance(n, ast.Assign) else n.target
            if (name and isinstance(tg, ast.Name) and tg.id == name) or (attr and isinstance(tg, ast.Attribute) and tg.attr == attr):
                return ast.literal_eval(n.value)
U   = assign("rbac_utils.py", name="DEFAULT_PERMISSIONS")
S   = assign("rbac_service.py", attr="default_roles")
TAD = assign("app_startup.py", name="tenant_admin_permissions")
STD = {r["name"]: r["permissions"] for r in assign("app_startup.py", name="standard_roles")}
D03 = {"view:federated_learning","view:goal_system","view:jobs","view:predictive_health","view:vector_db","view:webgpu_inference"}
DOCS = {"Tenant Admin": set(TAD), **{k: set(v) for k, v in STD.items()}}
ROLES = ["admin","Tenant Admin","user","analyst","security_analyst","incident_responder","viewer","itam_admin","itam_user","itam_viewer"]
ENF = {r: set(U[r]) for r in ROLES}                                            # verify_permission defaults
RBS = {r: (DOCS[r] if r in DOCS else set(S.get(r, []))) for r in ROLES}        # get_user_permissions
DEL = {r: DOCS.get(r, set()) for r in ROLES}                                   # /login today
NEW = {r: ENF[r] | set(S.get(r, [])) | DOCS.get(r, set()) for r in ROLES}      # D-04 union
ta = (NEW["admin"] | NEW["Tenant Admin"]) - {"manage:tenants"} - D03           # D-01, D-06, D-03
NEW["admin"] = NEW["Tenant Admin"] = ta
for r in ("itam_admin", "itam_user", "itam_viewer"):
    NEW[r] |= {"view:profile"}                                                 # D-08
# print sorted(NEW[r]-base), sorted(base-NEW[r]) for base in (ENF, RBS, DEL)
```
Output for this tree: sizes `admin 121, Tenant Admin 121, user 22, analyst 19, security_analyst 17, incident_responder 12, viewer 8, itam_admin 7, itam_user 5, itam_viewer 4`.

## Appendix B: AST scan thresholds (what the drift test sees today)

Threshold "list/tuple/set literal with >= 5 string constants, >= 80% matching `^(view|manage|export|remediate|investigate|request|control|admin|read|write|delete):...`" currently flags only: `app_startup.py` (314, 370, 453, 468, 483, 497, 513), `authentication_endpoints.py` (318 tier, 342 role list), `rbac_service.py` (8 lists), `rbac_utils.py` (8 lists), `reset_db_fresh.py` (29, 41; archived), `seed_demo_data.py` (18, 25, 34), `tenant_endpoints.py` (33 tier), `unlock_enterprise_features.py` (14 tier) `[VERIFIED: script output this session]`. After the phase only `rbac_defaults.py` plus the allowlisted tier/per-user lists should remain.
