# Phase 75: Permission Resolver & Single Source of Truth - Pattern Map

**Mapped:** 2026-10-12
**Files analyzed:** 19 (new/modified)
**Analogs found:** 17 / 19

All analog paths below were checked as git-tracked source, except where stated. Paths are relative to the repo root. Line numbers refer to the working tree at mapping time.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/rbac_defaults.py` (NEW) | config (pure data table) | transform | literals in `backend/rbac_service.py` `default_roles` (L50-140) | role-match |
| `backend/rbac_service.py` (resolver, derived `default_roles`, `assert_can_assign_role`) | service | request-response + CRUD read | itself: `find_role_doc` (L8-31), `get_user_permissions` (L~190-210), `can_assign_role` | exact |
| `backend/rbac_utils.py` (`verify_permission` delegates) | utility / guard | request-response | itself (L195-214, `require_super_admin` L228) | exact |
| `backend/authentication_endpoints.py` (`/login`, `/me`, signup) | controller | request-response | itself (L223-231, L266-281) | exact |
| `backend/mfa_endpoints.py` (verify-login response) | controller | request-response | `authentication_endpoints.py` `/login` | role-match |
| `backend/role_endpoints.py` (real `GET /api/roles`) | controller | CRUD read | current stub + `ldap_endpoints.py` list route (L165-168) | role-match |
| `backend/app_startup.py` (seed loop over table) | service (startup seed) | batch / upsert | itself (L353-364, L414-425, L521-526) | exact |
| `backend/user_endpoints.py` (ceiling + self-change guard) | controller | CRUD | itself (L262-277, L349-352) | exact |
| `backend/ldap_endpoints.py`, `backend/sso_endpoints.py` (write-time ceiling) | controller | CRUD | `user_endpoints.create_user` guard | role-match |
| `backend/ldap_service.py`, `backend/saml_mapping.py` (apply-time super-admin block) | service | event-driven (login sync) | `LDAPUserSyncer.sync_user` L440-462 | exact |
| `backend/bundle_endpoints.py` (3 routes -> `require_super_admin`) | controller | request-response | `rbac_utils.require_super_admin` users elsewhere | exact |
| `archive/backend-rbac-oneoffs/` + `ARCHIVED.md` | archive | file-I/O (move) | `archive/agent-rust/ARCHIVED.md` | exact |
| `App.tsx` (delete fallback L1213-1230) | component (memo) | transform | itself (L1205-1245) | exact |
| `services/apiService.ts` (clear `omni_cache_roles` on logout; no cached roles after 403) | service | request-response | `logoutSession` L223-237, `fetchWithCache` L425-445 | exact |
| `utils/permissions.ts` (optional pure derivation fn) | utility | transform | `checkPermission` inside App.tsx memo | partial |
| `backend/tests/test_rbac_defaults_drift.py` (NEW, AST drift test) | test | transform | none exact (see No Analog) | none |
| `backend/tests/test_permission_resolver.py` (NEW, resolver + login/me parity) | test | request-response | `backend/tests/test_user_crud.py` | role-match |
| `backend/tests/test_role_assignment_ceiling.py` (NEW, matrix) | test | request-response | `backend/tests/test_user_crud.py` L129-153 | role-match |
| Updated: `test_rbac.py`, `test_seed_database_step_isolation.py`, `test_prod_hardening.py`, `test_bundles_and_reports.py`, `test_user_crud.py` | test | - | themselves | exact |

## Pattern Assignments

### `backend/rbac_service.py` - resolver (service, request-response)

**Analog:** same file, `find_role_doc` and `get_user_permissions`.

**Raw-handle sentinel lookup** (L8-31; this is the blessed wrapper bypass, copy `db._db` usage):
```python
own_tenant = await db.roles.find_one({"name": role_name, "tenantId": tenant_id}) if tenant_id else None
if own_tenant:
    return own_tenant
raw_db = db._db
return (
    await raw_db.roles.find_one({"name": role_name, "tenantId": "all"})
    or await raw_db.roles.find_one({"name": role_name, "tenantId": "platform"})
)
```
Change for D-23: the new `_role_docs` helper must use `db._db.roles.find_one({"name": n, "tenantId": X})` for X in `[tenant_id, "all", "platform"]` (own tenant too), because `/login` has no tenant ContextVar. Leave `find_role_doc` untouched (`tests/test_find_role_doc.py` asserts its wrapper call; `zero_trust_service.py:305` uses it).

**Normalization (the only normalizer, reuse)** `_normalize_role` L142-158:
```python
normalized = (name or "").lower().strip().replace(" ", "_").replace("-", "_")
if normalized in ("superadmin", "platform_admin"):
    return "super_admin"
return normalized
```

**Super-admin short circuit + raw/normalized doc try** (`get_user_permissions`):
```python
normalized = self._normalize_role(user.role)
if normalized == "super_admin":
    return ["*"]
role_doc = await find_role_doc(db, user.role, user.tenant_id) or await find_role_doc(db, normalized, user.tenant_id)
```
New resolver must instead UNION defaults and docs (defaults first, de-duplicated, order stable; RESEARCH Pattern 2 sketch). `get_user_permissions` and `has_permission` then call it; keep `_scopes_allow` and the `has_permission` ordering untouched (L203-250).

**Import-cycle rule:** `rbac_defaults.py` must import neither `database` nor `rbac_service`; the resolver lives in `rbac_service.py`.

**Ceiling helper:** extend `can_assign_role` (currently only blocks super_admin). Follow D-20 rule order. `is_super_admin` is in `rbac_utils.py` and wraps `_normalize_role`.

---

### `backend/rbac_utils.py` - `verify_permission` (utility, request-response)

**Analog:** same file L195-214 (keep the fail-closed behaviour and the cheap defaults-first path):
```python
perms = DEFAULT_PERMISSIONS.get(effective_role, [])
if "*" in perms or required_permission in perms:
    return True
...
try:
    role_doc = await get_database().roles.find_one({"name": user.role, "tenantId": user.tenant_id})
except Exception as exc:  # fail closed: no grant if the role store is unreachable
    logger.warning("Role lookup failed for %s (denying %s): %s", user.role, required_permission, exc)
    return False
role_perms = (role_doc or {}).get("permissions", [])
return "*" in role_perms or required_permission in role_perms
```
Keep: function name/signature, module attribute `rbac_utils.get_database` (tests patch it), `require_permission` (L216-226), `require_super_admin` (L228-235). Delete the inner `DEFAULT_PERMISSIONS` literal and `_CANONICAL_KEY_BY_NORMALIZED`.

---

### `backend/authentication_endpoints.py` - `/login`, `/me`, signup (controller, request-response)

**Analog:** same file. Replace the `find_role_doc` block in both handlers.

`/login` L223-231 (current):
```python
role_obj = await find_role_doc(db, role, tenant_id)
if role_obj:
    user_data['permissions'] = role_obj.get('permissions', [])
else:
    user_data['permissions'] = []
```
`/me` L266-281 uses the same shape with `role_name = user.get("role", "user")` and `user.get("tenantId")`.

New shape (D-19, RESEARCH Pattern 2): wrap resolver in `try/except`; on error fall back to defaults-only and `logger.warning`; at `/login` only, `logger.warning("role %r resolved to no permissions", role)` when the list is empty; never refuse the login. Extract one helper (e.g. `build_user_permissions(db, role, tenant_id)`) and call it from `/login`, `/me`, signup response (~L407, `user_data = _public_user_fields(user_doc)`) and `mfa_endpoints.py` verify-login. Delete `enterprise_permissions` (~L342) and stop writing the `permissions` field on the user record (D-07).

---

### `backend/mfa_endpoints.py` - verify-login (controller, request-response)

**Analog:** `authentication_endpoints.py` `/login`. Current response L222-234:
```python
user_data = _public_user_fields(user)
user_data["id"] = str(user.get("_id", ""))
...
return {"access_token": access_token, "token_type": "bearer", "success": True, "mfa_verified": True, "user": user_data}
```
Add `user_data["permissions"] = await <shared helper>(...)` before the return.

---

### `backend/role_endpoints.py` - real `GET /api/roles` (controller, CRUD read)

**Analog:** current stub (router + `Role` model, keep both) and gating style from `ldap_endpoints.py`:
```python
router = APIRouter(prefix="/api/roles", tags=["Role Management"])
class Role(BaseModel):
    id: str; name: str; description: str; permissions: List[str]
@router.get("", response_model=List[Role])
async def list_roles(current_user: dict = Depends(get_current_user)):
```
Replace the dependency with a manage:users OR manage:rbac check. Pattern for an OR-gate: call `verify_permission(user, "manage:users") or verify_permission(user, "manage:rbac")` inside the handler, raising 403 as `require_permission` does (rbac_utils L216-226). Build the list from `rbac_defaults` built-ins plus own-tenant docs (`db.roles.find({"tenantId": caller.tenant_id})` through the wrapper is fine in an authenticated request) with `permissions` from the resolver; omit Super Admin unless `is_super_admin`. Keep router registration in `router_registry.py`. `tests/test_rbac.py` imports `role_endpoints`; update.

---

### `backend/app_startup.py` - seed loop (service, batch upsert)

**Analog:** same file. Current standard-role loop (L521-526) and Tenant Admin (L414-425), both name-only on the wrapper:
```python
for role_def in standard_roles:
    await db.roles.update_one({"name": role_def["name"]}, {"$set": role_def}, upsert=True)
logger.info("Standard roles (...) seeded")
except Exception as e:
    logger.error("[Seed] Standard roles seeding failed: %s", e)
```
New (RESEARCH Pattern 3): `raw_roles = db._db.roles`; for each of the 11 docs `await raw_roles.update_one({"name": doc["name"], "tenantId": doc["tenantId"]}, {"$set": doc}, upsert=True)`, each in its own `try/except` (ARCH-018). Super Admin keeps `tenantId: "platform"` with `permissions: ["*"]` (D-25); others `"all"`. Doc shape: `id`, `name`, `description`, `permissions`, `isEditable`, `tenantId` (+ `display_name` on standard roles). Update `backend/tests/test_seed_database_step_isolation.py` (`_mock_db` mocks `db.roles.update_one`; must mock `db._db.roles.update_one` and expect 11 names).

---

### `backend/user_endpoints.py` - ceiling (controller, CRUD)

**Analog:** same file. Guard in `create_user` L262-277 and `update_user` L349-352:
```python
requested_role_key = _normalize_role(user.role)
if requested_role_key not in _VALID_ROLE_KEYS:
    raise HTTPException(status_code=400, detail=f"Invalid role '{user.role}'")
if requested_role_key in _ELEVATED_ROLE_KEYS and not caller_is_super_admin:
    raise HTTPException(status_code=403, detail=f"Not authorized to assign role '{user.role}'")
```
Keep the 400 validation (derive `_VALID_ROLE_KEYS`, L33, from the table so `Admin`/`tenant_admin` still validate) and replace the 403 branch with the shared `assert_can_assign_role(...)` call (self-change check needs `target_email == current_user.username`). Role change already calls `revoke_user_sessions` (~L391-402); leave.

---

### `backend/ldap_endpoints.py` L172-178, `backend/sso_endpoints.py` L372-378 (controller, CRUD)

**Analog:** the two handlers themselves:
```python
tenant_id = _config_scope(current_user)
try:
    return await LDAPGroupMapper.upsert_mapping(mapping.group_dn, mapping.role, tenant_id=tenant_id, priority=mapping.priority or 100)
except LDAPConfigError as exc:
    raise HTTPException(status_code=400, detail=str(exc))
```
Insert `await assert_can_assign_role(...)` before `upsert_mapping`; keep model-layer `upsert_mapping` signatures (tests call them directly: `tests/test_ldap_service.py`, `tests/test_sso_saml.py`).

### `backend/ldap_service.py` L440-462 and `backend/saml_mapping.py` L72-85 (apply-time block)

**Analog:** `LDAPUserSyncer.sync_user`:
```python
if existing:
    if role:
        doc["role"] = role
...
else:
    doc["role"] = role or default_role
```
Add before use: `if role and rbac_service._normalize_role(role) == "super_admin": logger.warning(...); role = None` so existing/default role is kept. Same in `SAMLUserProvisioner.provision_user`. Mapping validators (`ldap_service.py:563`, `saml_mapping.py:137`) derive from the table.

---

### `backend/bundle_endpoints.py` L120-225 (controller)

**Analog:** current signature and `rbac_utils.require_super_admin`:
```python
_=Depends(require_permission("manage:tenants")),
```
becomes `_=Depends(require_super_admin),` on PUT/PATCH/DELETE `/tenant/{tenant_id}/assign` (import from `rbac_utils`); fix the docstring at ~L131 that says "Super Admin / Tenant Admin". Update `backend/tests/test_bundles_and_reports.py` L153-215 (patches `verify_permission -> True`; needs explicit roles now).

---

### `archive/backend-rbac-oneoffs/` (archive, file-I/O)

**Analog:** `archive/agent-rust/ARCHIVED.md` (short prose: what it is, why not shipped, do not edit, moved on DATE). Use `git mv` for exactly: `backend/fix_rbac_integrations.py`, `update_sbom_roles.py`, `update_all_sbom_roles.py`, `enable_compliance_for_admin.py`, `reset_db_fresh.py`. Keep `fix_rbac.py`, `fix_all_rbac.py`, `unlock_enterprise_features.py`, `diagnose_rbac.py` in place (D-14). Drift test must skip `archive/`.

---

### `App.tsx` L1205-1245 (component memo, transform)

**Analog:** same file. Delete the `else { // Fallback to role-based lookup ... }` block (L1213-1230); leave `effectiveFeatures = []`. Keep `checkPermission` (super-admin name checks, `'all'` shortcut) and the tier intersection. After deletion, drop `roles` from the deps `[currentUser, roles, tenants]` (L1242). Optional: lift derivation into `utils/permissions.ts` so a vitest can cover it (App.tsx has no unit test).

### `services/apiService.ts` (service)

**Analog:** `logoutSession` L223-237 ends with:
```ts
sessionStorage.removeItem('token');
sessionStorage.removeItem('refresh_token');
```
Add `sessionStorage.removeItem('omni_cache_roles');` there (D-26). `fetchWithCache` (L425-445) falls back to `sessionStorage.getItem(\`omni_cache_${key}\`)` on any error; for the roles key a 403 must not serve the cache (either skip the fallback for `roles` on a 403 or remove the key on 403). Note `fetchWithCache` swallows errors via the catch, so verify how non-OK status reaches the catch before editing; also verify the App.tsx `Promise.all` load path (D-16).

---

## Shared Patterns

### Role-name normalization
**Source:** `backend/rbac_service.py` `_normalize_role` L142-158. **Apply to:** resolver, ceiling helper, `_VALID_ROLE_KEYS`, LDAP/SAML validators. Never add another super-admin literal set.

### Wrapper bypass for shared catalogue / pre-auth / startup
**Source:** `backend/rbac_service.py` L27-31 (`raw_db = db._db`). **Apply to:** resolver reads, seed upserts. Reason: ContextVar differs per call site (`None` at `/login`, `"platform-admin"` at seed, JWT tenant at `/me`); `backend/database.py` L51-55 shows the passthrough and the "NON_EXISTENT_TENANT" behaviours.

### Fail closed on enforcement, fail open (empty list) on delivery
**Source:** `rbac_utils.py` L205-212 (deny on exception). **Apply to:** `verify_permission` stays deny; `/login` and `/me` degrade to defaults-only and log (D-19).

### 403 style
**Source:** `rbac_utils.py` L216-235, `user_endpoints.py` L273-274:
```python
raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform super-admin access required")
```

### Per-step try/except in seeding
**Source:** `app_startup.py` L526-528 `except Exception as e: logger.error("[Seed] ... failed: %s", e)`. **Apply to:** every seeded doc.

## Test Patterns

- **In-memory Mongo fake over the real `TenantIsolatedDatabase`:** pattern in `backend/tests/test_sso_config_without_tenant_context.py` L14-60 (`_matches`, `_Cursor`, `_Collection.find_one/find/update_one`, `_RawDB.__getattr__`). NOTE: that file is untracked in git at mapping time (`git ls-files` empty). Copy the pattern but have the planner confirm it exists or re-create the fake in a shared `conftest`/helper; do not cite it as a dependency. `_Collection.update_one` there does not implement `upsert=True`; extend it for the seed test.
- **Mocked-db seed tests:** `backend/tests/test_seed_database_step_isolation.py` L17-27 (`_mock_db` with `db._db = MagicMock()` and `AsyncMock` methods).
- **User CRUD / route tests:** `backend/tests/test_user_crud.py` L129-153 monkeypatches `itam_asset_endpoints.verify_permission`; `FakeDB` there needs a `roles` collection (or the helper must tolerate a missing store) for the ceiling helper.
- **Existing assertions to update (from RESEARCH):** `tests/test_rbac.py` L188/199 (itam sets gain `view:profile`), L291-295 (`can_assign_role("itam_user","itam_admin")` now False), L406-414 (`manage:tenants` for `tenant_admin` flips to denied); `tests/test_prod_hardening.py` L157-160 uses `rbac_service.default_roles["Tenant Admin"]` (keep the derived dict key). Regression tests required by CONTEXT specifics: Tenant Admin 403 on another tenant's `/tenant/{id}/assign`; `itam_admin` 403 assigning `admin`/`Tenant Admin` and own-role change; LDAP/SAML mapping to `super_admin` refused at write and apply. Note the tests live under `backend/tests/` (CONTEXT/RESEARCH cite `tests/...` shorthand).
- **Frontend:** vitest (jsdom), tests in `src/__tests__` (per RESEARCH).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/tests/test_rbac_defaults_drift.py` | test | transform | No existing AST-based literal-drift test. Use `ast` walk over `backend/*.py` excluding `archive/` and `rbac_defaults.py`, flagging list/tuple literals of `view:`/`manage:` strings (RESEARCH Validation Architecture + Appendix A generator). |
| `backend/rbac_defaults.py` | config | transform | No pure-data permission module exists; build tuples with the Appendix A generator, do not retype. |
| Per-role gained/lost diff artifact | doc | transform | Appendix A of RESEARCH (lines 382+, not re-read here) holds the AST generator; planner should reuse it. |

## Metadata

**Analog search scope:** `backend/` (rbac_*, auth, mfa, user, ldap, sso, saml, bundle, app_startup, role endpoints), `backend/tests/`, `App.tsx`, `services/apiService.ts`, `archive/`.
**Files scanned:** ~20 targeted reads/greps.
**Pattern extraction date:** 2026-10-12
