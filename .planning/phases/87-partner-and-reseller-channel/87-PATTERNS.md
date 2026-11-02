# Phase 87: Partner and Reseller Channel - Pattern Map

**Mapped:** 2026-11-02
**Files analyzed:** 27 (new and modified)
**Analogs found:** 25 / 27 (all analog paths verified git-tracked)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/partner_pool.py` (new) | service | CRUD, atomic counter | `backend/licensing.py` (`try_claim_seat`, `release_seats`, `reconcile_all`) | exact |
| `backend/partner_service.py` (new) | service | CRUD, request-response | `backend/tenant_endpoints.py` (`create_tenant` 95-131) + `backend/mssp_endpoints.py` | role-match |
| `backend/partner_platform_endpoints.py` (new) | route | request-response | `backend/mssp_endpoints.py` + `catalogue_guard` | role-match |
| `backend/partner_endpoints.py` (new) | route | request-response | `backend/mssp_endpoints.py` (roll-up) | role-match |
| `backend/catalogue_mounts_partners.py` (new) | config | n/a | `backend/catalogue_mounts_billing_identity.py` | exact |
| `backend/migrations/029_partner_channel.py` (new) | migration | indexes only | `backend/migrations/028_security_response.py` | exact |
| `backend/rbac_defaults.py` (mod) | config | n/a | itself: `PLATFORM_*_KEY`, `BUILTIN_ROLES` (200-240) | exact |
| `backend/role_assignment.py` (mod) | utility | request-response | itself: `assert_role_fits_tenant` (58-71) | exact |
| `backend/tenant_middleware.py` (mod, or sibling) | middleware | request-response | itself: `platform_write_refusal` (20-41) | exact |
| `backend/authentication_service.py` (mod) | service | request-response | itself: `verify_token_async` (read before editing) | exact |
| `backend/licensing.py`, `pending_agents.py`, `tenant_endpoints.py`, `license_rules.py` (mod hooks) | service | CRUD | themselves | exact |
| `shared/catalogue-access.json` (mod) | config | n/a | entry for `tenantManagement` | exact |
| `backend/tests/test_partner_*.py` (new) | test | real-Mongo | `tests/test_licensing.py`, `tests/test_platform_role_isolation.py` | exact |
| `services/partnerApi.ts` (new) | service | request-response | `services/apiService.ts` 6305-6340 (`_licenseError`, `fetchTenantLicense`, `updateTenantLicense`) | exact |
| `components/PartnersDashboard.tsx` (new) | component | request-response | `components/MSSPDashboard.tsx` (table roll-up) | role-match |
| `components/PartnerPortal.tsx` (new) | component | request-response | `components/MSSPDashboard.tsx` + `utils/csvExport.ts` | role-match |
| `components/PartnerCustomerModals.tsx` (new) | component | CRUD | `components/TenantLicensePanel.tsx` | exact |
| `components/PartnerFormModal.tsx`, `PartnerStatusDialogs.tsx`, `PartnerMoveCustomerModal.tsx`, `PartnerTeamPanel.tsx` (new) | component | CRUD | `components/Modal.tsx` + `TenantLicensePanel.tsx` | role-match |
| `components/PartnerScreenPicker.tsx` (new) | component | CRUD | `components/ManageTenantModal.tsx` feature picker | role-match |
| `components/PartnerStatusChip.tsx` (new) | component | n/a | `components/AutonomousOpsActivityList.tsx` chips (copy constants) | role-match |
| `components/AcceptInvitePage.tsx` (new) | component | request-response | `components/ResetPasswordModal.tsx` (UNTRACKED in git: use only as a visual reference, planner should confirm it is committed first; rules text also in UI-SPEC line 327); `App.tsx` ~711 (`/sso-callback`) for public route | role-match |
| `App.tsx`, `components/Sidebar.tsx`, `utils/permissions.ts`, `utils/viewAccess.ts` (mod) | wiring | n/a | `/sso-callback` handling in `App.tsx` 709-725 | partial |

## Pattern Assignments

### `backend/partner_pool.py` (service, atomic counter)

**Analog:** `backend/licensing.py`

Conventions to copy: raw-handle helper, module docstring stating "every query names its tenant explicitly and runs on raw collections", `logger`, named constants.

```python
def _raw(db):
    return getattr(db, "_db", db)                     # licensing.py 28-29

async def try_claim_seat(db, tenant_id: str) -> bool:    # 91-98
    await ensure_license(db, tenant_id)
    res = await _raw(db).tenants.update_one(
        {"id": tenant_id, "$expr": {"$lt": ["$license.seatsUsed", "$license.maxAgents"]}},
        {"$inc": {"license.seatsUsed": 1}},
    )
    return res.modified_count == 1

async def release_seats(db, tenant_id, count=1):          # 101-111  never below zero
    res = await raw.tenants.update_one(
        {"id": tenant_id, "license.seatsUsed": {"$gte": count}},
        {"$inc": {"license.seatsUsed": -count}})
    if res.modified_count == 0:
        await recount_seats(db, tenant_id)               # self-repair fallback
```
Pool claim (RESEARCH Pattern 1) adapts this: filter `{"id", "type": "partner", "partner.status": "active", "$expr": {"$lte": [{"$add": ["$partner.allocated", n]}, "$partner.poolSize"]}}`, `$inc` `partner.allocated`. Customer write is a CAS on `license.maxAgents` with `$expr $gte [new, "$license.seatsUsed"]` (D-06). Writers must set both `license.maxAgents` and legacy `maxAgents` (as `update_license` does, licensing.py 147-149). Bounds: `licensing.MAX_AGENTS_CEILING`. Reconcile: mirror `licensing.reconcile_all` (lines ~196-233, read it before writing) and skip `type == "partner"` in `licensing` loops (196, 223). Use `license_of` defaults carefully: a partner doc must store `license.maxAgents: 0` or `DEFAULT_MAX_AGENTS=5` is invented (licensing.py 50-66).

### `backend/partner_service.py` (service)

**Analog:** `backend/tenant_endpoints.py` `create_tenant`, lines 95-131. Extract the document-building into a shared helper (do not copy; tenant_endpoints.py is 767 lines, keep new code in new modules).

```python
tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
registration_key = f"reg_{uuid.uuid4().hex}"
tenant_doc = {
    "id": tenant_id, "name": data.name, "subscriptionTier": data.subscriptionTier,
    "registrationKey": registration_key,
    "enabledFeatures": list(dict.fromkeys(data.enabledFeatures)),
    "agentCapabilities": agent_capabilities.every_capability(),
    "emailConfig": {}, "maxAgents": data.maxAgents,
    "license": {"maxAgents": data.maxAgents, "seatsUsed": 0,
                "inactiveReclaimDays": licensing.DEFAULT_RECLAIM_DAYS},
    "createdAt": ..., "updatedAt": ...}
await mongodb.db.tenants.insert_one(tenant_doc)
# then: autonomy_settings.ensure_tenant(mongodb.db, tenant_id) wrapped in try/except + logger.warning
```
Add `partnerId`. Replace the duplicate-name `HTTPException(400, "Tenant already exists")` with a generic "name unavailable" for partners (name oracle). Partner response omits `registrationKey`. Partner org doc layout is in RESEARCH "Partner and customer document layout".

Count-only agent reads: copy `tenant_endpoints.get_tenants` aggregation (lines 70-78: Pending counted apart, Rejected excluded) using the raw handle with `$match: {"tenantId": {"$in": customer_ids}}`.

### `backend/partner_platform_endpoints.py` and `backend/partner_endpoints.py` (routes)

**Analog:** `backend/mssp_endpoints.py` (router/imports) plus `catalogue_guard` from `catalogue_mounts_billing_identity.py`.

```python
from fastapi import APIRouter, Depends, HTTPException, Query     # mssp_endpoints.py 2-9
from authentication_service import get_current_user, TokenData
router = APIRouter(prefix="/api/mssp", tags=["MSSP"])
```
Do not copy its role check (`current_user.role not in ("super_admin", "Super Admin")`, line 20) or `db.tenants.find({})`; route guards come from the manifest. Partner routes: partner id is only `current_user.tenant_id` after confirming `type == "partner"` and `partner.status == "active"` on the raw `tenants` handle (`tenants` is EXEMPT from the DB wrapper); filter `{"partnerId": partner_id}`, 404 on foreign ids, build responses from an allowlist, never return docs. Use `{"_id": 0}` projections (`_strip_id` pattern, mssp 12-14).

### `backend/catalogue_mounts_partners.py` (config)

**Analog:** `backend/catalogue_mounts_billing_identity.py`

```python
from catalogue_guards import catalogue_exempt, catalogue_guard          # line 18
TENANT_MANAGEMENT_GUARD = catalogue_guard(                               # 56-58
    "tenantManagement", read=("manage:tenants",), write=("manage:tenants", "manage:settings"))
MOUNTS = {                                                               # 83-88
    ("finops_endpoints", "router"): FINOPS_GUARD,
}
```
New: `PARTNERS_GUARD = catalogue_guard("partners", read=("manage:partners",), write=("manage:partners",))`, `PARTNER_PORTAL_GUARD = catalogue_guard("partnerPortal", read=("view:partner_portal",), write=("manage:partner_customers",))`; keys `("partner_platform_endpoints", "router")`, `("partner_endpoints", "router")`. Module docstring states the drift test (`test_catalogue_slice_*`) that checks read/write strings against `shared/catalogue-access.json`. Public/self-service routes use `catalogue_exempt("reason")` (lines 49-51, 69-72). Also edit `tests/_catalogue_parity.py` `SLICES` and the pinned counts in `test_catalogue_manifest.py` (run first, per RESEARCH Wave 0).

### `backend/migrations/029_partner_channel.py` (migration)

**Analog:** `backend/migrations/028_security_response.py` (27 lines): docstring "Indexes only, nothing is backfilled", `DESCRIPTION`, `async def up(db)`, idempotent `create_index`.
```python
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
DESCRIPTION = "..."
logger = logging.getLogger(__name__)
async def up(db: AsyncIOMotorDatabase) -> None:
    ...; logger.info("migration 029: ...")
```
Indexes: `tenants {partnerId:1}` (partial, string), `tenants {type:1}`. No data change (D-12). 028 is the latest; confirm 029 is free.

### `backend/rbac_defaults.py` (mod)

**Analog:** itself.
```python
PLATFORM_BILLING_KEY = "platform_billing"                               # 25
PLATFORM_ROLE_KEYS = frozenset({SUPER_ADMIN_KEY, PLATFORM_SUPPORT_KEY, PLATFORM_BILLING_KEY})
BuiltinRole("platform_billing", "Platform Billing", "role-platform-billing", None,
            "Platform staff: ...", False, "platform"),                  # 238-240
```
Add `PARTNER_ADMIN_KEY/PARTNER_VIEWER_KEY`, `PARTNER_ROLE_KEYS`, `is_partner_role`, two `BuiltinRole(..., False, "platform")` rows, and permissions `view:partner_portal` / `manage:partner_customers`. Do NOT touch `PLATFORM_ROLE_KEYS`, `_PLATFORM_TIERS`, `SUPER_ROLES`. Add `manage:partner_customers` to `ADMIN_TIER_PERMISSIONS` (MFA, D-20); add `manage:partners` to `SUPER_ADMIN_ONLY_PERMISSIONS`; add `PARTNER_ONLY_PERMISSIONS` banned in `rbac_service.py` line ~103. This file is 349 lines; keep edits minimal. Pinned tests to edit deliberately: `test_rbac_defaults.py`, `test_custom_role_mfa.py::test_admin_tier_selects_exactly_the_builtin_admin_roles`.

### `backend/role_assignment.py` (mod)

**Analog:** `assert_role_fits_tenant` lines 58-71.
```python
def assert_role_fits_tenant(role, tenant_id) -> None:
    in_platform_tenant = tenant_id == rbac_defaults.PLATFORM_TENANT_ID
    if rbac_defaults.is_platform_role(role) and not in_platform_tenant:
        raise HTTPException(status_code=400, detail=f"Role '{role}' is a platform role and can only be held in the Platform tenant")
```
Add an async sibling `assert_role_fits_tenant_type(role, tenant_doc)` (partner roles only in `type == "partner"` orgs, any other role refused there); call at `user_endpoints.py:288` and `:413`; add `refuse_directory_partner_role` beside `refuse_directory_platform_role`.

### Partner viewer second wall (`backend/tenant_middleware.py`)

**Analog:** `platform_write_refusal` lines 20-41 and `PlatformReadOnlyMiddleware`.
```python
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_SELF_SERVICE_WRITES = (re.compile(r"^/api/(auth|mfa|passkey)/"), re.compile(r"^/api/users/me/"))
def platform_write_refusal(role, method, path) -> Optional[str]:
    ...
    if method.upper() in _SAFE_METHODS or not path.startswith("/api/"): return None
    if any(p.match(path) for p in _SELF_SERVICE_WRITES): return None
    return f"... read-only here ..."
```
Add `partner_write_refusal` for `partner_viewer` reusing the same constants, and mount it where `PlatformReadOnlyMiddleware` is mounted.

### `backend/authentication_service.py` suspension (mod)

Add the partner-role check in `verify_token_async`/`verify_token` (lines ~337-342, ~455-462 per RESEARCH) after the revocation check; fail closed on lookup error (the existing revocation check at ~445-448 fails open, do not copy that). On suspend call `revoke_user_sessions(email, "partner suspended")` for each partner user. Read the surrounding code before editing.

### License writers (mods)

`PATCH /api/tenants/{id}/license` (`tenant_endpoints.py` 730-755 calling `licensing.update_license`) and `pending_agents.py` 397-399 (`$inc license.maxAgents`/`maxAgents` by `raise_limit_by`) must branch to `partner_pool.change_allotment` when the tenant has `partnerId`. `license_rules.hold_reason` (110-128) adds the partner-pool expiry check using `expired()`.

### `backend/tests/test_partner_*.py` (tests)

**Analog:** `tests/test_licensing.py` and `tests/test_platform_role_isolation.py`.
```python
"""Value: protects=...; fails_when=...; no_claim=..."""          # docstring convention (licensing 1-10)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import licensing
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

async def test_twenty_concurrent_claims_take_exactly_the_free_seats(mongo_db):   # 56-60
    await _tenant(mongo_db, max_agents=5)
    results = await asyncio.gather(*(licensing.try_claim_seat(mongo_db, T) for _ in range(20)))
    assert results.count(True) == 5
```
Isolation tests hand code the RAW database and assert partner A gets none of B's rows (platform_role_isolation 1-10). Real-Mongo tests must run against a private mongod via `MONGO_TEST_URL`, never live 27017. Add `tests/_partner_fixtures.py` (two partners, customers, direct customer, tokens). Also update `test_route_auth_baseline.py` if a new public route is added.

### `services/partnerApi.ts` (service)

**Analog:** `services/apiService.ts` 6305-6340. Copy `_licenseError` (throws `Error` with `body.error || body.detail`), `authFetch(\`${API_BASE}/...\`)`, `method: 'PATCH'`, JSON headers, `if (!res.ok) return _licenseError(res, 'Failed to ...')`. Reuse `authFetch`/`API_BASE` from `apiService` (check exports). Note `MSSPDashboard` instead uses raw `fetch` with `sessionStorage.getItem('token')`: do not copy that.

### `components/PartnerCustomerModals.tsx`, `PartnerFormModal.tsx` (components)

**Analog:** `components/TenantLicensePanel.tsx`. Copy: `useState` string fields parsed with `Number(...)`, `valid`/`dirty` derivation (lines 48-59), `dateOf` (`iso.slice(0,10)`), expiry write `new Date(\`${expiresOn}T23:59:59Z\`).toISOString()` (70), error/saving/saved state with try/catch/finally (61-78), and input class (line 81), raised to `min-h-10` per UI-SPEC:
`'w-full min-h-10 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-white'`. Wrap in `components/Modal.tsx` (read its props first).

### `components/PartnersDashboard.tsx`, `PartnerPortal.tsx` (components)

**Analog:** `components/MSSPDashboard.tsx` for the table shape/state style only (it uses `lucide-react` icons; UI-SPEC mandates `components/icons.tsx` local icons, e.g. `BuildingIcon`, so do not copy its imports). CSV: `import { toCsv, downloadCsv } from '../utils/csvExport'` — `toCsv(headers, rows)`, `downloadCsv(filename, csv)`; `csvCell` already formula-guards (csvExport.ts 6-13). Header order and filename pattern are fixed in UI-SPEC line 301.

### `components/AcceptInvitePage.tsx` and `App.tsx` public route

**Analog:** `App.tsx` 709-725 (`/sso-callback` is handled in a `useEffect` reading `window.location.pathname` before `restoreSession`). Copy that precedent so `/accept-invite` is reachable without a session. Password rules list: mirror the rules list in UI-SPEC line 327 (`components/ResetPasswordModal.tsx` exists on disk but is untracked). Posts `{token, new_password}` to existing `POST /api/auth/reset-password/confirm`; no frontend consumer exists today.

## Shared Patterns

### Tenants collection is EXEMPT from the DB wrapper
**Source:** `backend/database.py` 28-38, 178-179. **Apply to:** all partner routes and `partner_pool.py`. Use raw handle with explicit `partnerId` filter; never set `platform-admin` context.

### Atomic conditional update (no read-then-write)
**Source:** `backend/licensing.py` 91-98. **Apply to:** `partner_pool.py` claim, CAS, pool shrink (`{"partner.allocated": {"$lte": new_pool}}`).

### Audit
**Source:** `backend/audit_ledger.py` `event(action, tenant_id, *, actor, outcome, **fields)` (failures spool, never raise). **Apply to:** appoint, suspend/reinstate, pool/ceiling/expiry change, allotment, create, move, invite. Platform actions under `"platform-admin"`, mirrored under the partner's own tenant id.

### Manifest + mounts + parity
**Source:** `shared/catalogue-access.json` entry shape:
`{"view": "tenantManagement", "label": "Tenants", "group": "mgmt", "nav": true, "permission": "manage:tenants", "write": [...], "routes": ["/api/tenants"]}`. **Apply to:** `partners` and `partnerPortal` entries, with `test_catalogue_route_parity.py`, `test_catalogue_manifest.py` updated.

### File size
CLAUDE.md: keep files under 500 lines. `tenant_endpoints.py` (767) and `rbac_defaults.py` (349) get minimal edits only; new logic lives in new modules.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| Invite creation in `partner_service.py` | service | event-driven | No invite flow exists; closest is `auth_password_reset_endpoints.py` (token row in `password_reset_tokens`, confirm endpoint) per RESEARCH section 4 |
| `PartnerReadOnly` role-scoped middleware tests | test | request-response | `platform_write_refusal` has tests to mirror (find via `grep -l platform_write_refusal backend/tests`), but none for a partner |

## Metadata

**Analog search scope:** `backend/`, `backend/migrations/`, `backend/tests/`, `components/`, `services/`, `utils/`, `App.tsx`
**Files read:** 12 (licensing, catalogue_mounts_billing_identity, migration 028, mssp_endpoints, TenantLicensePanel, test_licensing, tenant_endpoints/middleware/rbac_defaults/role_assignment excerpts, csvExport, apiService excerpt, App.tsx excerpt)
**Not read (planner must read before editing):** `authentication_service.py`, `rbac_service.py`, `database.py`, `Modal.tsx`, `ManageTenantModal.tsx`, `ResetPasswordModal.tsx`, `Sidebar.tsx`, `AutonomousOpsActivityList.tsx`, UI-SPEC body
**Pattern extraction date:** 2026-11-02
