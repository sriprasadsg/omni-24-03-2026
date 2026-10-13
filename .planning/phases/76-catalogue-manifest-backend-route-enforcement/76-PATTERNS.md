# Phase 76: Catalogue Manifest & Backend Route Enforcement - Pattern Map

**Mapped:** 2026-10-13
**Files analyzed:** 14 (new/modified) plus ~108 in-scope endpoint modules (guard pattern mapped once)
**Analogs found:** 12 / 14

All analog paths are git-tracked source. `shared/` does not exist yet (new directory).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/catalogue_guards.py` (new) | middleware (dependency factory) | request-response | `backend/itam_asset_endpoints.py` `_require_itam_viewer/_admin` (lines 38-93) | exact |
| `backend/router_registry.py` (mod) | config (mount) | request-response | itself, `_load(**kwargs)` lines 51-61 | exact |
| `backend/itam_asset_endpoints.py` (mod) | middleware | request-response | itself (rewrite two guards to call `check_catalogue_access`, keep `get_current_user_or_api_key`) | exact |
| ~108 in-scope `*_endpoints.py` | route | request-response | see Shared Patterns: guard application | role-match |
| `backend/asset_endpoints.py` (mod, D-04/D-10 strip) | route | CRUD | itself: `get_assets` L61-63, `search_assets` L105-107, `get_asset_details` L158 | exact |
| `backend/tests/_route_walk.py` (new) | test util | batch | `backend/tests/test_route_auth_baseline.py` `_WALK` lines 66-150 | exact (extract) |
| `backend/tests/test_route_auth_baseline.py` (mod) | test | batch | itself (import walker from `_route_walk`) | exact |
| `backend/tests/test_catalogue_route_parity.py` (new) | test | batch | `test_route_auth_baseline.py` (`route_walk` fixture L142-150, set-diff assertion L157-158) | role-match |
| `backend/tests/test_catalogue_guards.py` (new) | test | request-response | `backend/tests/conftest.py` `make_test_app`, `make_token_data` | role-match |
| `backend/tests/test_asset_finance_fields.py` (new) | test | CRUD | same conftest helpers | role-match |
| `backend/tests/test_catalogue_manifest.py` (new) | test | transform | `backend/tests/test_rbac_defaults.py` | role-match |
| `shared/catalogue-access.json`, `shared/catalogue-gaps.json` (new) | config | static data | none | no analog |
| `utils/catalogueAccess.ts` (new) | utility | transform | `utils/permissions.ts` | role-match |
| `src/__tests__/catalogueAccess.test.ts` (new) | test | transform | `src/__tests__/*.test.tsx` (vitest, setup `src/__tests__/setup.ts`) | role-match |
| `components/Sidebar.tsx`, `App.tsx` (mod) | component | request-response | themselves (`navGroups` ~208-440, `visibleGroups` 441-466; `viewPermissionMap` L243, read L646, L1337) | exact |

## Pattern Assignments

### `backend/catalogue_guards.py` (middleware, request-response)

**Analog:** `backend/itam_asset_endpoints.py` lines 38-93. Order is mandatory: role check first (`verify_permission`), then API-key scope (`_rbac_service._scopes_allow`).

```python
async def _require_itam_viewer(current_user: TokenData = Depends(get_current_user_or_api_key)):
    has_view = await verify_permission(current_user, "view:itam")
    has_manage = await verify_permission(current_user, "manage:assets")
    if not (has_view or has_manage):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have permission to view ITAM assets.")
    if not (_rbac_service._scopes_allow(current_user, "view:itam")
            or _rbac_service._scopes_allow(current_user, "manage:assets")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key scope does not permit: view:itam")
    return current_user
```

Factory shape: use RESEARCH.md "Pattern 1" sketch (76-RESEARCH.md lines 173-190). `SAFE` methods check `view` or its `manage:` twin (D-03/D-07); writes check `write`. Stamp `dependency.__catalogue_guard__ = {"catalogue","view","write"}`. Super-admin bypass lives inside `verify_permission` (rbac_utils.py:63-85).

### `backend/router_registry.py` (mount)

```python
def _load(app: FastAPI, module_name: str, attr: str = "router", **kwargs) -> None:
    ...
    app.include_router(getattr(mod, attr), **kwargs)   # L56: dependencies=[...] flows through
```
Call sites look like `_load(app, "itam_asset_endpoints", "router")` (L92-95). Never use `_REQUIRED_ROUTERS` modules (authentication_endpoints) for guards.

### Guard application (~108 modules): one pattern, two placements

- **Mount-level (pure routers, every route user-authenticated):**
  `_load(app, "mdm_endpoints", "router", dependencies=[Depends(catalogue_guard("mobileDeviceManagement", view="view:mdm", write="manage:assets"))])`
  Representative analogs: `mdm_endpoints`, `siem_endpoints`, `billing_endpoints` (each is login-only today per RESEARCH L391).
- **Route-level (mixed routers: agent/public/credential-in-handler beside user routes; ~20, e.g. `agent_core_endpoints`, `agent_endpoints`, `trust_endpoints`, deployments result route):**
  `@router.get("/x", dependencies=[Depends(catalogue_guard(...))])` only on user routes. Keep `get_current_user_or_agent` routes untouched (D-02). Generate the pure/mixed split from the walk, not by filename. Same router mounted twice (`itam_component_endpoints`) needs a guard on each `_load`.
- D-08: payments/billing routes use `manage:settings`; FinOps reads `view:finops`. D-09: `/api/users` and `/api/roles` keep existing guards, only tagged.

### `backend/asset_endpoints.py` (D-04/D-10 strip)

Handlers: `get_assets` (`@cached(ttl=60, key_prefix="assets")`), `search_assets` (`ttl=30`), `get_asset_details`. Imports already include `get_current_user`, `cached`, `is_super_admin`. Add a helper that builds a NEW dict per item (cache returns shared objects) dropping purchase cost, book value, warranty fields, `supplierId` unless caller passes `verify_permission(user, "view:itam")` (or manage:itam). Field names: derive from `itam_models.py` lines 120-157, 284-292. Cache key includes `current_user`, so per-user caching is safe, but never mutate in place.

### `backend/tests/_route_walk.py` and `test_catalogue_route_parity.py`

**Analog:** `test_route_auth_baseline.py`. Extract `_WALK` (66-150) verbatim, keep the fresh-interpreter subprocess (other tests reload `authentication_service`), and extend to emit per route `tags` (`getattr(c, "__catalogue_guard__", None)` over `dep_calls(route.dependant, [])` plus `include_deps`), `has_known_guard` (`PERM_DEP` match), `agent_only`, `public`. Key excerpts:

```python
def walk(routes, include_deps=()):
    for route in routes:
        if isinstance(route, _IncludedRouter):
            deps = include_deps + tuple(route.include_context.dependencies or ())
            ...
@pytest.fixture(scope="module")
def route_walk():
    proc = subprocess.run([sys.executable, "-c", _WALK], cwd=backend, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["total"] > 1000
```
Assertion style (L157-158): `unexpected = sorted(found - REVIEWED_...)`, assert empty with the list in the message. Parity messages must name router/route and expected permission (CONTEXT specifics). Keep `REVIEWED_UNAUTHENTICATED` semantics; add injected-offender fixtures for ACC-05.

### `backend/tests/test_catalogue_guards.py` / `test_asset_finance_fields.py`

Use `conftest.py` `make_test_app(*routers, current_user_override=None, db_override=None)` (L159) and `make_token_data(...)` (L58). Matrix: 403 without view, 200 with `view:X`, `manage:X` satisfies read, write needs write perm, API-key scope narrowing, agent token unaffected. `asyncio_mode = auto`.

### `utils/catalogueAccess.ts` / `src/__tests__/catalogueAccess.test.ts`

**Analog:** `utils/permissions.ts` (header imports `import type { Permission, ... } from '../types';`, small pure exported functions). JSON import `import m from '../shared/catalogue-access.json'` works under vitest and `tsc` without `resolveJsonModule` (RESEARCH L64). Test must live in `src/__tests__/` (vite glob). Manifest: ordered groups/items, `nav:false` entries for the 14 App-only views so `viewPermissionMap` is deleted; icons/`minTier`/`featureKey` stay in Sidebar as `Record<AppView,...>`. Nine mismatches: Sidebar string wins (D-11).

## Shared Patterns

### Role-then-scope enforcement
**Source:** `backend/itam_asset_endpoints.py` 38-93. Apply to every guard; `_require_itam_viewer/_admin` rewritten to call `check_catalogue_access` and stamp the tag, keeping `get_current_user_or_api_key`.

### Test app construction
**Source:** `backend/tests/conftest.py` `make_test_app`. Mount-level guards leave the dominant direct-router tests unaffected; only real-app tests see new 403s. Run the full backend suite after each guard wave and fix tests by giving users the permission, not loosening guards.

### Agent routes
**Source:** `REVIEWED_UNAUTHENTICATED` in `test_route_auth_baseline.py` L20-61 (e.g. `POST /api/deployments/{job_id}/result`, `GET /api/agent/download/{tenant_id}`). Never wrap these.

## No Analog Found

| File | Reason |
|---|---|
| `shared/catalogue-access.json`, `shared/catalogue-gaps.json` | `shared/` does not exist; use RESEARCH.md manifest shape (L150-170) and Appendix A/B |

## Metadata

**Analog search scope:** `backend/` (router_registry, itam_asset_endpoints, asset_endpoints, tests), `utils/`, `src/__tests__/`
**Pattern extraction date:** 2026-10-13
