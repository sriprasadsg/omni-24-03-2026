# Phase 87: Partner and Reseller Channel - Research

**Researched:** 2026-11-02
**Domain:** Multi-tenant authorization (a third kind of cross-organization reach), atomic seat-pool accounting on standalone MongoDB, invite onboarding, FastAPI/React.
**Confidence:** HIGH on the codebase map and the pool design; MEDIUM on test-suite pinned counts (not run) and on frontend wiring (App.tsx, Sidebar, types not read in full).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Partner staff see only seats and usage for their customers: customer name, seats assigned and used, agent counts (online and total), licence expiry. They see no alerts, assets, findings, users or any other customer data, through any route. (costly to reverse)
- **D-02:** The reach is the same for every partner and every customer. Customers cannot grant more and the Super Admin cannot widen it per partner in this phase.
- **D-03:** One level only: Super Admin, then partner, then customer. A partner cannot appoint sub-dealers.
- **D-04:** Two partner roles. A partner admin creates customers, moves seats and invites customer admins. A partner viewer only reads the partner's customer list, pool and usage. Partner roles hold no tenant permission and no platform permission. They must not pass `can_read_all_tenants` or `has_platform_permission`, and they must never be added to `SUPER_ROLES` or the platform-scope role sets.
- **D-05:** A partner has a fixed pool, for example 1,000 seats, which it splits among customers. Each customer's allotment is its existing `license.maxAgents`. The sum of allotments can never exceed the pool, enforced atomically in the same style as `licensing.try_claim_seat` (conditional update, no read-then-write race). (one-way)
- **D-06:** A partner can lower a customer's allotment only down to the seats that customer uses now. Running agents are never cut off by a partner.
- **D-07:** The Super Admin cannot shrink a partner's pool below the total already handed out. The refusal says how many seats are handed out, so the partner can be asked to take seats back first.
- **D-08:** A pool can carry an expiry date. After it, the partner can neither create customers nor hand out seats. Its customers' licences follow today's expiry rule in `license_rules.py`: new agents are held Pending, and agents already enrolled keep working. No trial pools in this phase.
- **D-09:** The partner admin creates the customer organization, sets its seats from the pool, and invites the customer's first admin by email. From then on the customer admin runs the organization, with the same rights a directly created organization's admin has today.
- **D-10:** The Super Admin sets a screen ceiling per partner, the set of screens that partner may sell. The partner ticks screens for each customer within that ceiling, using the existing per-organization screen switches (`enabledFeatures`, spec C6). The server rejects any screen outside the ceiling.
- **D-11:** Only the Super Admin can move a customer to another partner or make it a direct customer. Its allotment returns to the old partner's pool, and the move is recorded in the audit ledger.
- **D-12:** Every existing organization stays a direct customer of the platform. The Super Admin can assign one to a partner later, through D-11.
- **D-13:** A partner is its own organization, marked as type `partner`. It has its own users, login, MFA, sessions and audit trail, all reused unchanged. It has no endpoints, no seats for itself and no security screens. Its users see only a Partner portal. (costly to reverse)
- **D-14:** The Super Admin gets a new Partners screen. There it appoints a partner, sets its pool, expiry and screen ceiling, sees every partner's pool used and free, and can suspend or reinstate a partner.
- **D-15:** Suspending a partner locks the partner only. Its users cannot log in or move seats. Its customers keep running with the seats they hold, and nothing is taken away.
- **D-16:** The partner's usage roll-up shows the pool size, seats handed out and seats free. Per customer it shows seats assigned, seats used, agents online and licence expiry, with a CSV export. There is no invoicing and no monthly history.

### Claude's Discretion
- Field names, collection layout and the migration number, as long as D-05's atomic guarantee and D-12's "existing organizations untouched" hold.
- Whether the Partner portal is a new sidebar section or a separate view, as long as partner users reach nothing else.
- How an invited customer admin first signs in, reusing the existing invite or password-set flow where one exists.

### Deferred Ideas (OUT OF SCOPE)
- Invoicing and billing per partner, and a monthly usage history to bill from.
- Sub-dealers: a distributor, then retailers, then customers.
- Customer opt-in to give its partner a read-only security view, and an MSSP-style managed service by partners.
- Customer self-sign-up with a partner code.
- Trial pools with automatic expiry.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PART-01 | Super Admin appoints partner, pool, expiry, ceiling, suspend/reinstate | Partner org doc layout; `/api/platform/partners` routes; suspension chokepoint in `verify_token_async` + `revoke_user_sessions` (sections 3, 7) |
| PART-02 | Partner admin creates customer, seats from pool, invites first admin | Shared tenant-creation helper; pool claim; invite via `password_reset_tokens` + new accept page (sections 4, 6) |
| PART-03 | Pool never exceeded under concurrency; lower only to used; pool shrink guard | `partner_pool.py` conditional `$expr` claim, CAS on customer, reconcile (section 5) |
| PART-04 | Pool expiry blocks creation/hand-out; customers follow existing expiry rule | Python expiry check in pool ops; `license_rules.hold_reason` consults partner expiry (section 5) |
| PART-05 | Partners reach only own customers, only seats+usage, every route; viewer read-only | Partner identity from token tenant only; allowlisted projection; partner perms outside tenant/platform sets; second-wall middleware; route-walk test (sections 1, 2, 9) |
| PART-06 | Ceiling enforced server-side on customer screens | `screenCeiling` on partner doc, subset check against `tenant_features` vocabulary (section 6) |
| PART-07 | Only Super Admin moves customers; seats return; audit; existing orgs stay direct | `partnerId` absent = direct (no backfill); move operation; audit (sections 5, 8) |
| PART-08 | Usage roll-up and CSV | MSSP analog; aggregation on counts only; client-side `toCsv` (section 10) |
</phase_requirements>

## Summary

This phase is mostly a new, narrow authorization surface, not a new data model. The tenant boundary is enforced by `TenantIsolatedDatabase` scoping every non-exempt collection to the request's tenant context, but **`tenants` is itself an exempt collection**, so the wrapper will NOT scope reads of `tenants` for a partner user. Every partner route must therefore filter `tenants` explicitly by `partnerId == <partner id taken from the verified token's tenant>`, project only the D-01 fields, and rebuild the response from an allowlist. That, plus giving partner roles permissions that exist in no tenant or platform set, is the whole isolation story; everything else (login, MFA, sessions, audit chain) is reused.

The seat pool is best built as a counter on the partner document (`partner.allocated`) advanced with a conditional `$expr` update, mirroring `try_claim_seat`, plus a compare-and-swap on the customer's current `license.maxAgents`, plus a reconcile that recomputes the counter from the customers. The invariant "counter >= true sum at all times" holds if increases claim the pool first and decreases write the customer first, so a crash can only leak free seats (repaired by reconcile), never over-allocate. No multi-document transaction is needed, which matters because the local mongod appears to be standalone.

Three existing facts change the plan: (1) there is **no invite flow and no frontend page that consumes the password-reset token**, and the reset email link is hardcoded to `http://localhost:5173`; (2) there are **three existing writers of a customer's `license.maxAgents`** (PATCH license, Pending-approval `raise_limit_by`, tenant creation) that must all become pool-aware; (3) the **MFA, role and manifest tests pin exact sets**, so adding two roles and two catalogue entries needs deliberate test edits.

**Primary recommendation:** Add `partner_admin`/`partner_viewer` as built-in roles holding only new partner-only permissions (`view:partner_portal`, `manage:partner_customers`), put partners and customers in `tenants` (`type: "partner"` / `partnerId`), route all partner reads/writes through one module (`partner_service.py` + `partner_pool.py`) that derives the partner from the token and projects an allowlist, enforce suspension in `verify_token_async`, and prove isolation with a real-Mongo two-partner test plus a role-matrix test.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Partner identity and scoping (partner = token tenant, type partner) | API / Backend | Database | `tenants` is exempt from the DB wrapper, so scoping must be explicit in route code |
| Seat pool atomicity | Database (conditional update) | API / Backend | Only a single-document conditional write is race-free on standalone Mongo |
| Suspension lock-out | API / Backend (`verify_token_async`) | Database (`revoked_tokens` cutoff) | One chokepoint covers every token issuer (login, MFA, passkey, SSO, refresh) |
| Screen ceiling enforcement | API / Backend | -- | UI is advisory; server must reject (D-10) |
| Invite / first sign-in | API / Backend | Browser (accept-invite page) | Token store exists; page does not |
| Partners screen, Partner portal | Browser / Client | API / Backend | UI contract written separately; data from new routes |
| CSV export | Browser / Client | -- | `utils/csvExport.ts` already does RFC 4180 + formula guard |
| Audit of appoint/suspend/pool/allot/move | API / Backend | Database (`audit_logs` chain) | `audit_ledger.event` |

## Standard Stack

No new external packages. This phase uses only what is already installed. `gsd-tools query package-legitimacy check` was not run because nothing is installed. [VERIFIED: codebase read; no new dependency is required by any design below]

### Core (all in-repo, verified this session)
| Module | Purpose | Why |
|--------|---------|-----|
| `backend/licensing.py` | `try_claim_seat`, `license_of`, `ensure_license`, `update_license`, `reconcile_all` | Pool code mirrors and calls it |
| `backend/license_rules.py` | `expired`, `hold_reason` | D-08 reuse |
| `backend/rbac_defaults.py` | role table, `PLATFORM_ONLY_PERMISSIONS`, `SUPER_ADMIN_ONLY_PERMISSIONS`, `ADMIN_TIER_PERMISSIONS` | Where partner roles/permissions live |
| `backend/audit_ledger.py` | `event(action, tenant_id, *, actor, outcome, **fields)` | Hash-chained audit |
| `backend/authentication_service.py` | `verify_token_async`, `revoke_user_sessions` | Suspension |
| `backend/migrations/runner.py` | startup migrations, next free number 029 | Indexes |
| `motor` / `pymongo` | conditional updates | already used |
| `utils/csvExport.ts` | `toCsv`, `downloadCsv` | CSV export |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Counter on partner doc + reconcile | Sum customers on every claim (aggregation) | Aggregation + write is a read-then-write race; rejected |
| Counter | Mongo multi-doc transaction | Needs a replica set; mongod looks standalone (A2); rejected |
| Pool expiry checked in `hold_reason` | Copy pool expiry into every customer `license.expiresAt` | Copy drifts when the pool date changes and clobbers a customer's own earlier date; rejected |

## Package Legitimacy Audit

No external packages are installed by this phase. Packages removed due to [SLOP] verdict: none. Packages flagged [SUS]: none.

## Architecture Patterns

### System Architecture Diagram

```
Super Admin (tenant platform-admin)                      Partner user (tenant = partner org, role partner_admin|partner_viewer)
        |                                                          |
        | /api/platform/partners/*  (guard: manage:partners,       | /api/partner/*  (guard: view:partner_portal / manage:partner_customers)
        |   SUPER_ADMIN_ONLY)                                      |
        v                                                          v
   TenantMiddleware sets ContextVar tenant (X-Tenant-ID owner-only)    TenantMiddleware sets ContextVar tenant = partner org
        |                                                          |
        |                                      verify_token_async: JWT ok? cutoff? --> partner role? --> look up partner doc:
        |                                         suspended / missing --> 403 (fail closed)
        |                                                          |
        v                                                          v
  partner_platform_endpoints.py                         partner_endpoints.py  (partner_id := current_user.tenant_id, never path/body/header)
        |                                                          |
        +-----------------> partner_service.py / partner_pool.py <-+
                                   |
        +--------------------------+----------------------------------------+
        v                          v                                        v
  tenants (EXEMPT from wrapper)   agents (count-only aggregation,         audit_logs (audit_ledger.event,
  partner doc {type:partner,       $match tenantId in partner's             hash chain per tenant)
  partner:{poolSize,allocated,     customer ids; returns counts only)
  expiresAt,screenCeiling,status}}
  customer doc {partnerId, license.maxAgents = allotment}
        |
        v
  licensing.try_claim_seat (unchanged, per customer)   license_rules.hold_reason (adds partner pool expiry)
```

### Recommended Project Structure
```
backend/
├── partner_pool.py               # claim/release/change_allotment/move/shrink_pool/reconcile (pure DB, raw handle)
├── partner_service.py            # appoint, suspend, create_customer, invite, usage rollup, ceiling check, projection allowlist
├── partner_platform_endpoints.py # /api/platform/partners  (Super Admin)
├── partner_endpoints.py          # /api/partner            (partner users)
├── catalogue_mounts_partners.py  # MOUNTS for the two routers
├── migrations/029_partner_channel.py  # indexes only, no backfill (D-12)
└── tests/test_partner_*.py
components/PartnersDashboard.tsx, PartnerPortal.tsx, AcceptInvitePage.tsx  # UI contract written separately
```

### Pattern 1: Pool claim mirroring `try_claim_seat`
**What:** conditional `$expr` update that only succeeds while the pool has room.
```python
# Source pattern: backend/licensing.py try_claim_seat (lines 91-98), adapted
async def claim_pool(raw, partner_id: str, n: int) -> bool:
    res = await raw.tenants.update_one(
        {"id": partner_id, "type": "partner", "partner.status": "active",
         "$expr": {"$lte": [{"$add": ["$partner.allocated", n]}, "$partner.poolSize"]}},
        {"$inc": {"partner.allocated": n}})
    return res.modified_count == 1
```
Check expiry in Python before calling (wall-clock, not a race). Customer write is a compare-and-swap:
```python
res = await raw.tenants.update_one(
    {"id": cust_id, "partnerId": partner_id, "license.maxAgents": current,
     "$expr": {"$gte": [new, "$license.seatsUsed"]}},   # D-06, atomic vs enrollment claims
    {"$set": {"license.maxAgents": new, "maxAgents": new}})
```
Order: increase = claim pool first, then CAS customer, compensate (`$inc` back) if CAS fails. Decrease = CAS customer first, then `$inc` pool negative. Invariant: `partner.allocated >= true sum` always. `reconcile_pools` recomputes `allocated` from an aggregation and logs drift (like `licensing.reconcile_all`, called from `app_background_tasks.py:338`).

Pool shrink (D-07): `update_one({"id": P, "partner.allocated": {"$lte": new_pool}}, {"$set": {"partner.poolSize": new_pool}})`; on 0 matches return 409 including `allocated`.

### Pattern 2: Partner route scoping
```python
async def current_partner(user=Depends(get_current_user)):
    if not rbac_defaults.is_partner_role(user.role):  # new helper
        raise HTTPException(403)
    doc = await raw.tenants.find_one({"id": user.tenant_id, "type": "partner"})
    if not doc or doc["partner"]["status"] != "active":
        raise HTTPException(403, "partner suspended")   # fail closed
    return doc
# every query: {"partnerId": doc["id"]}  -- never a path/body/query/X-Tenant-ID value
```
Response built from a fixed allowlist (D-01): `id, name, seatsAssigned, seatsUsed, agentsOnline, agentsTotal, licenseExpiresAt` (+ partner-level pool fields). Never `return doc`; never include `registrationKey`, `apiKeys`, `emailConfig`, `enabledFeatures` of other fields beyond what the portal needs.

### Anti-Patterns to Avoid
- **Borrowing platform-admin context** (`set_tenant_id("platform-admin")`) in partner code: it disables wrapper scoping for reads and writes. Use the raw handle with an explicit `partnerId` filter instead.
- **Reading `db.tenants` through the wrapper and assuming it is scoped:** it is exempt [VERIFIED below].
- **Returning the invite link/token to the partner admin:** it would let the partner set the customer admin's password and sign in as it (a D-01 breach).
- **Another writer of `license.maxAgents`** that skips the pool (see Pitfall 1).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sessions/lock-out | custom revoke store | `revoke_user_sessions(email, reason)` + chokepoint check | existing cutoff docs `user-cutoff:<email>` |
| MFA | partner MFA | existing admin-tier MFA via `ADMIN_TIER_PERMISSIONS` | D-13 reuse |
| Audit | new log | `audit_ledger.event` | hash chain, CAS head, spool |
| CSV | server CSV writer | `utils/csvExport.ts` `toCsv` | formula-injection guard already there |
| Password set | new password endpoint | `POST /api/auth/reset-password/confirm` + a token row in `password_reset_tokens` | complexity check, LDAP/SAML block, session revoke, single-use delete |
| Seat claim per customer | anything new | `licensing.try_claim_seat` unchanged | D-05 |
| Tenant creation | second copy | extract the doc-building from `create_tenant` into a shared helper | "same creation path" |

## Findings by Research Question

### 1. Tenant resolution and partner scoping
- Token claims: `TenantMiddleware.dispatch` decodes the JWT and sets the ContextVar from `payload.get("tenant_id")`. The override is owner-only. [VERIFIED: backend/tenant_middleware.py:185-200]
  `override_tenant = request.headers.get("X-Tenant-ID")` / `if override_tenant and rbac_defaults.platform_tier(role) == "owner":`
- `verify_token`/`verify_token_async` reject a token with no `tenant_id` and call `_set_tenant_id(tenant_id)`. [VERIFIED: backend/authentication_service.py:337-342, 455-462]
- The wrapper bypasses scoping only when the context is `"platform-admin"`. [VERIFIED: backend/database.py:69] `if tenant_id == "platform-admin":`
- **`tenants` is exempt.** [VERIFIED: backend/database.py:28-38] list contains `"tenants",` (also `"ip_bans"`, `"playbooks"`, `"response_policies"`, `"compliance_frameworks"`, `"compliance_controls"`, `"ai_governance_frameworks"`, `"system_features"`, `"crypto_inventory"`). `TenantIsolatedDatabase.__getitem__` returns `self._db[name]` raw for these (database.py:178-179).
- Existing code reads `tenants` through both `mongodb.db.tenants` (raw) and `db._db.tenants`; both are unscoped. A partner user's wrapper context is the partner org, so non-exempt collections return nothing of a customer's, but **any route that reads `tenants` (or other exempt collections) with only `get_current_user` returns other orgs' rows**. Known `tenants.find({})` readers are role-checked (`mssp_endpoints.py` Super Admin checks, `graphql_api/resolvers.py:128-131` super-admin check, `tenant_endpoints.get_tenants` platform staff). ~25 non-script call sites iterate all tenants (git grep list: app_background_tasks, audit_ledger:269, autonomous_ops/settings:147, retention_*, licensing:196/223, license_rules:160, finops_scheduler:50, ...). [VERIFIED: git grep this session]
- Partner id rule: partner id is **only** `current_user.tenant_id` (from the verified token) after confirming that org's doc has `type == "partner"`. Never take it from path, body, query or `X-Tenant-ID`. Customer ids from a path must be confirmed `{"id": cid, "partnerId": partner_id}` and return 404 (not 403) otherwise.
- A Super Admin using `X-Tenant-ID` = a partner org does not become a partner (the token's `tenant_id`/role are unchanged); partner routes require a partner role, so the owner is refused there. This is intentional; the Partners screen gives the Super Admin its own per-partner detail.
- The count-only agent read: `db.agents.aggregate` with `$match: {"tenantId": {"$in": customer_ids}}` and `$group` by tenant+status, as `get_tenants` does (tenant_endpoints.py:70-78), using the raw handle because the wrapper would add the partner's own tenant filter. Counting rule to reuse: Pending counted apart, Rejected excluded (tenant_endpoints.py:75-78). "Online" = `status == "Online"`. [VERIFIED: licensing.py:23-25 comment "Agents in these states hold no seat; every other status (Online, Offline, Degraded, ...) does."]
- Socket.IO fan-out is per connected tenant/sid (`websocket_manager.py` emits `room=sid`); a partner tenant has no emitters. Not read in full. [ASSUMED: A5]

### 2. Roles and where the partner roles fit
Verified facts:
- `SUPER_ROLES`, `platform_scope_roles()` (predicate `rbac_defaults.is_platform_role`), `platform_owner_roles`, `tenant_admin_roles` (predicate `is_tenant_admin`). [VERIFIED: backend/auth_roles.py:12-13, 47-71]
- `can_read_all_tenants`: `if is_super_admin(role): return True` / `return is_platform_role(role) and _tenant_of(user) == rbac_defaults.PLATFORM_TENANT_ID`; `has_platform_permission` requires `can_read_all_tenants`. [VERIFIED: backend/rbac_utils.py:38-54]
- `PLATFORM_ROLE_KEYS: FrozenSet[str] = frozenset({SUPER_ADMIN_KEY, PLATFORM_SUPPORT_KEY, PLATFORM_BILLING_KEY})`; `PLATFORM_TENANT_ID = "platform-admin"`. [VERIFIED: rbac_defaults.py:24-31]
- `effective_permissions` bans `SUPER_ADMIN_ONLY_PERMISSIONS | {"*"}` and (for non-platform roles) `PLATFORM_ONLY_PERMISSIONS` from role documents. [VERIFIED: rbac_service.py:100-104]
- `ADMIN_TIER_PERMISSIONS` drives MFA: `requires_mfa` returns True if `"*"` or any entry is held. [VERIFIED: rbac_defaults.py:184-197]
- `assert_role_fits_tenant(role, tenant_id)` is sync, keyed on the sentinel tenant id only; callers: `user_endpoints.py:288` and `:413`. [VERIFIED: role_assignment.py:58-71; git grep]
- Role documents can only add ordinary permissions; unknown role names resolve to `[]`. [VERIFIED: rbac_service.py:75-105]

Recommended design (Claude's discretion on names):
1. `rbac_defaults.py`: `PARTNER_ADMIN_KEY="partner_admin"`, `PARTNER_VIEWER_KEY="partner_viewer"`, `PARTNER_ROLE_KEYS`, `is_partner_role(role)`; **do not** touch `PLATFORM_ROLE_KEYS`, `_PLATFORM_TIERS` or `SUPER_ROLES`.
   - `partner_admin`: `("manage:partner_customers", "view:partner_portal")`; `partner_viewer`: `("view:partner_portal",)`. Omit `view:profile` (partner users need only `/api/auth`, `/api/mfa`, `/api/passkey`, which are manifest `unownedPrefixes`).
   - New `PARTNER_ONLY_PERMISSIONS` frozenset banned from every non-partner role document (extend the `banned` logic at rbac_service.py:103) and a new `manage:partners` in `SUPER_ADMIN_ONLY_PERMISSIONS` (Partners screen, like `manage:tenants`).
   - Add `manage:partner_customers` to `ADMIN_TIER_PERMISSIONS` so partner admins must enroll MFA (D-13). Partner viewer needs no MFA (A4).
   - New permissions must be named in the manifest or role table so `permission_vocabulary` (derived, "there is no literal permission list here") picks them up; `implied_closure` will also derive `view:partner_customers` from `manage:partner_customers` only if it is in the vocabulary (harmless).
   - Role doc metadata: `BuiltinRole(..., doc_tenant_id="platform")` so customer tenants' role lists are not offered partner roles (same as platform roles; role listing filter not read: A6).
2. Role-to-tenant fitting: add `assert_role_fits_tenant_type(role, tenant_doc)` (async lookup of the target tenant's `type`): partner roles only in `type == "partner"` orgs; any non-partner role refused in a partner org; call it at `user_endpoints.py:288` and `:413`. Add `refuse_directory_partner_role` beside `refuse_directory_platform_role` (LDAP/SAML mapping). `resolve_assignable_role`: custom roles never in a partner org.
3. Assignment: only the Super Admin assigns partner roles (mirror `assert_can_assign_role` rule 1 at role_assignment.py:145). The assignment ceiling already blocks a customer tenant admin from handing out a partner role (its perms are not a subset of the admin's closure), but add the explicit refusal.
4. Second wall for the viewer: generalize `platform_write_refusal` (tenant_middleware.py:32-41) or add a sibling `PartnerReadOnlyMiddleware` that refuses any non-safe `/api/` method for `partner_viewer` except self-service (`^/api/(auth|mfa|passkey)/`, `^/api/users/me/`, as `_SELF_SERVICE_WRITES` at tenant_middleware.py:23). Route guards (`manage:partner_customers` write) remain the first wall.
5. Frontend: `utils/permissions.ts` has `PLATFORM_TIERS` mirror and `isPlatformRoleName`; add partner role helpers without making a partner a platform tier. `evaluateViewAccess` lets Super Admin and any `*` holder into every view (viewAccess.ts:29-30), so the Partner portal entry would show for the Super Admin unless the UI contract hides it (`partnerOnly`/role gate). Partner users hold only the two partner permissions, so `landingView`/`NAV_GROUPS` filtering shows only the portal. Do **not** add the partner perms to `tenant-feature-switches.json`: non-switchable permissions are never removed by `narrow()` ("Permissions outside the catalogue are never removed", tenant_features.py docstring), so the partner org needs no `enabledFeatures`.
6. Manifest: add catalogues `partners` (`permission: "manage:partners"`, routes `["/api/platform/partners"]`, group `mgmt`) and `partnerPortal` (`permission: "view:partner_portal"`, `write: ["manage:partner_customers"]`, routes `["/api/partner"]`). Manifest entry shape [VERIFIED: shared/catalogue-access.json]: `{"view": "tenantManagement", "label": "Tenants", "group": "mgmt", "nav": true, "permission": "manage:tenants", "write": ["manage:tenants", "manage:settings"], "routes": ["/api/tenants"]}`. Guards via a new `catalogue_mounts_partners.py` (`MOUNTS` keyed `(module_name, attr)`; duplicates raise; catalogue_mounts.py:20-27). `/api/platform` is an `unownedPrefix`, but a catalogue claiming the longer prefix `/api/platform/partners` takes it in-scope; that is fine and keeps the guard uniform.

### 3. Seats, expiry, license writers
- `try_claim_seat`: `{"id": tenant_id, "$expr": {"$lt": ["$license.seatsUsed", "$license.maxAgents"]}}`, `{"$inc": {"license.seatsUsed": 1}}`. [VERIFIED: licensing.py:91-98]
- `license_of` defaults `maxAgents` to `DEFAULT_MAX_AGENTS = 5` when missing. A partner org must therefore store `license: {"maxAgents": 0, "seatsUsed": 0, "inactiveReclaimDays": 30}` explicitly, or background jobs (`ensure_license`, `reconcile_all`, `reclaim_inactive_agents` iterate every tenant, licensing.py:196, 223) will invent 5 seats for it. Better: skip `type == "partner"` in those two loops. [VERIFIED: licensing.py:18, 50-66]
- `MAX_AGENTS_CEILING = 1_000_000` bounds pool and allotments. [VERIFIED: licensing.py:21]
- `update_license` allows lowering below `seatsUsed` by design ("Lowering below seatsUsed is allowed"); D-06 applies only on the partner route. [VERIFIED: licensing.py:134-140]
- **Writers of `license.maxAgents` that must become pool-aware** (all verified):
  1. `PATCH /api/tenants/{id}/license` -> `licensing.update_license` (tenant_endpoints.py:730-755; allowed to platform owner and billing via `manage:tenant_license`).
  2. Pending approval `raise_limit_by`: `{"$inc": {"license.maxAgents": raise_limit_by, "maxAgents": raise_limit_by}}` (pending_agents.py:397-399).
  3. `create_tenant` (`"license": {"maxAgents": data.maxAgents, ...}`, tenant_endpoints.py:116-118) and signup (`"maxAgents": 5`, authentication_endpoints.py:346) which create direct customers (no `partnerId`) and are unaffected.
  Make 1 and 2 call `partner_pool.change_allotment` when the tenant has a `partnerId`; refuse with 409 and the free count when the pool lacks room. Add a drift test (like the Phase 75 role-literal drift test) that fails if any backend module outside `licensing.py`/`partner_pool.py` writes `license.maxAgents` (allowlist: migrations, pending_agents hook).
- `delete_tenant` deletes users and agents of the org (tenant_endpoints.py:292-358); add a pool release (or rely on reconcile as backstop) and refuse deleting a partner org that still has customers.
- Expiry: `expired(lic, now)` and `hold_reason` read a fresh tenant doc then `if expired(lic): return REASON_EXPIRED`. [VERIFIED: license_rules.py:110-128] Add: if `fresh.get("partnerId")`, fetch that partner doc and `return REASON_EXPIRED` when `expired({"expiresAt": partner["partner"].get("expiresAt")})`. One extra indexed `find_one` per enrollment; running agents are never re-checked (module docstring, license_rules.py:8-9), so D-08's "agents already enrolled keep working" holds without extra code. The partner-visible "licence expiry" is `min(license.expiresAt, pool expiresAt)`.
- Pool atomicity options and choice: see Pattern 1. mongod: `/etc/mongod.conf` (read) contains only `storage:`, `systemLog:`, `net:`, `processManagement:` blocks (no `replication:` key), and the binary is 8.0.34 (`mongod --version`); a standalone cannot run multi-document transactions. This is an absence-of-config inference; it was not confirmed by connecting (forbidden). [ASSUMED: A2] The design does not depend on it.
- Moves (D-11): returning the allotment to the old pool is `$inc` negative on the old partner; **moving to a different partner must claim the same allotment from the new partner's pool (and fail with 409 if it does not fit)**, or the sum can exceed the new pool. D-11 does not say this; see Open Question 2.
- Pool-expiry + suspension interplay in pool ops: claim filter includes `"partner.status": "active"`; Python check refuses when the pool is expired. Seat release (negative `$inc`) stays allowed while suspended/expired so the Super Admin can always unwind.

### 4. Invites (D-09)
- There is **no invite flow**. `create_user` needs a typed password (`UserCreate.password`), validates complexity, requires existing tenant, and inserts `hashed_password`, `status` (user_endpoints.py:100-106, 264-322).
- Reset flow: `POST /api/auth/reset-password/request` issues a uuid token, stores `{"token", "email", "expires_at"}` in `password_reset_tokens` with a 30-minute expiry, then emails `f"{base_url}/reset-password?token={reset_token}"` where `base_url = body.callback_url if hasattr(body, "callback_url") and body.callback_url else "http://localhost:5173"`; `PasswordResetRequest` has only `email`, so the link is **always `http://localhost:5173/...`**. [VERIFIED: auth_password_reset_endpoints.py:25-27, 103-123]
- `POST /api/auth/reset-password/confirm` validates the token (DB or in-memory), `expires_at`, password complexity, blocks LDAP/SAML users, consumes the token, sets `password`, and calls `revoke_user_sessions`. It is public (`/api/auth/reset-password` is in `TenantMiddleware._PUBLIC_PATHS`, tenant_middleware.py:124) and already on the reviewed-unauthenticated list. [VERIFIED: auth_password_reset_endpoints.py:184-248; test_route_auth_baseline.py:27-28]
- **No frontend page consumes the token.** `git grep` for `reset-password/confirm` / `new_password` in `*.ts`/`*.tsx` returns nothing; `services/apiService.ts:2773` only calls `/auth/reset-password/request`. [VERIFIED: git grep this session]
- SMTP is unconfigured on this VM (project memory: optional integrations). `_resolve_smtp_config` falls back from user tenant to the platform tenant's `emailConfig`. [VERIFIED: auth_password_reset_endpoints.py:46-76; CITED: memory optional-integrations-unconfigured]
- Login looks users up by email only (`find_one({"$or": [{"username": identifier}, {"email": identifier}]})`, authentication_endpoints.py:172-177) while the unique index is `(email, tenantId)` (migrations/001). So the same email in two orgs makes login ambiguous. [VERIFIED]

Recommended flow:
1. Partner admin submits customer name, seats, first-admin name+email. Server checks **global** email uniqueness on `users` (raw; return a generic refusal that does not say which org holds it).
2. Create the user in the new customer org: role `"Tenant Admin"`, `status: "Active"`, `hashed_password` = hash of `secrets.token_urlsafe(48)` (unusable). `account_is_active` requires status Active (authentication_service.py:187-195).
3. Insert a `password_reset_tokens` row with a **7-day** `expires_at` (confirm honors the row's `expires_at`); do not set `created_at` (the collection has a 1-hour TTL index on `created_at`, database.py:425, so a doc without that field is not purged early).
4. Email the link using a server-configured base URL (`FRONTEND_URL` is the repo's existing env name, e.g. sso_endpoints.py:49) via `email_service.send_email(smtp_config=..., ...)`. Never put the token or link in the API response. If SMTP is unavailable return `emailSent: false`; the Super Admin (existing set-password modal in User Management) is the fallback.
5. New frontend `AcceptInvitePage` (public) posts `{token, new_password}` to the existing confirm endpoint, then signs in; the first login forces MFA enrollment because `tenant_admin` is admin-tier (`mfa_action`), all unchanged.
6. "Resend invite" is allowed to the partner only while the invited user has never signed in (no `lastLogin`) and the token is unconsumed; afterwards only the customer admin or Super Admin can reset the password. This keeps D-01: a partner must not be able to take over an active customer admin.
Note the invitee's address is chosen by the partner (inherent to D-09).

### 5. Audit ledger (spec C5)
- `audit_ledger.event(action, tenant_id, *, actor=None, outcome="success", db=None, **fields)` records through `record`, hash-chained per tenant with a CAS chain head; failures spool and never raise. [VERIFIED: audit_ledger.py:1-18, 151-174, 203-206]
- Login events use `actor={"userId":..., "email":..., "role":...}`. [VERIFIED: authentication_endpoints.py:152-159]
- `audit_service.log_action_async(user_name=..., action=..., resource_type=..., resource_id=..., details=..., tenant_id=...)` is the legacy adapter, used by licensing and tenant routes (licensing.py:180-187; tenant_endpoints.py:757-764).
- Recommended: use `audit_ledger.event`. Action names (discretion): `partner.appointed`, `partner.suspended`, `partner.reinstated`, `partner.pool_changed`, `partner.ceiling_changed`, `partner.expiry_changed`, `partner.customer_created`, `partner.allotment_changed`, `partner.customer_moved`, `partner.invite_sent`. Record Super Admin actions under tenant `"platform-admin"` with `partnerId`/`customerId` fields, and mirror partner-facing ones (pool, suspend, ceiling, allotment, create, invite) under the partner org's own tenant id (the partner's "own audit trail", D-13). Moves: platform chain plus both partners' chains. Partner roles hold no `view:audit_log`, so the Super Admin reads partner trails (A7). Include before/after values (`poolSize`, `allocated`, old/new allotment) like the `license.changed` details.

### 6. Customer onboarding, ceiling (D-10)
- `TenantCreate.enabledFeatures` defaults to `tenant_features.START_FEATURES` = `("view:dashboard", "view:profile", f"{SCREEN_PREFIX}dashboard")` (tenant_features.py:97; tenant_endpoints.py:58). Always allow START_FEATURES for a partner-created customer regardless of the ceiling.
- Store `partner.screenCeiling` as a list of switch strings in the same vocabulary as `enabledFeatures` (validated against `tenant_features.SWITCHABLE` and `screen:` switches; reject unknown strings). A literal `"all"` in a ceiling means unrestricted (Super Admin's explicit choice); a partner can never write `"all"` into a customer unless the ceiling holds it.
- The partner route `PUT /api/partner/customers/{id}/features` validates: input is a list of known switch strings, each in `ceiling ∪ START_FEATURES`, parents present (`SWITCH_PARENTS`), customer belongs to this partner, then `$set enabledFeatures`. The existing `update_tenant` already refuses non-Super-Admin feature changes (tenant_endpoints.py:214-220) and stays that way.
- Customer creation: extract the document-building from `create_tenant` (tenant_endpoints.py:103-131: id `tenant_<hex12>`, `registrationKey`, `agentCapabilities: agent_capabilities.every_capability()`, `license`, autonomy settings `ensure_tenant`) into a shared helper; add `partnerId`. Partner create response omits `registrationKey`. Existing global duplicate-name check leaks other orgs' names; return a generic "name unavailable".
- Ceiling changes by the Super Admin do not strip screens already ticked for customers (A9/Open Question 3).

### 7. Login and suspension (D-15)
- Token issuers are several (login, MFA verify, passkey, LDAP/SAML/SSO exchange, refresh), so a login-only check is not enough. [VERIFIED: authentication_endpoints.py:162-273, 409-445; test_route_auth_baseline.py:20-27 lists mfa/passkey/ldap/saml/sso exchange]
- Single chokepoint: `verify_token_async` / `verify_token` run for every user API call (`get_current_user` -> `verify_token_async(token, allow_agent=False)`, authentication_service.py:473-476). Add: `if rbac_defaults.is_partner_role(role):` look up the partner org (`tenants.find_one({"id": tenant_id, "type": "partner"})`), raise 403 when missing or `partner.status != "active"`; **fail closed** on lookup error (unlike the fail-open revocation check at authentication_service.py:445-448). Applies only to partner roles, so no cost for others. Also check in `/login` and `/refresh` for a clear message (refresh reads `users` then `account_is_active`, authentication_endpoints.py:440-442).
- On suspend: `revoke_user_sessions(email, "partner suspended")` for every user of the partner org (cutoff docs `user-cutoff:<email>` in `revoked_tokens`; raises if the cutoff cannot be stored, authentication_service.py:198-224). Do **not** flip users' `status` (reinstatement would need to restore each user).
- Customers are untouched on suspend (D-15): nothing in the pool or customer docs changes; seat claims by customer agents keep working because they use `try_claim_seat` on the customer.
- `partner.status` is a new nested field; do not reuse the tenant top-level `status` (used for sign-up `pending`/`active`, tenant_signup_endpoints.py:30-60).

### 8. Existing roll-up analog (MSSP)
- `GET /api/mssp/overview` is Super Admin only by `current_user.role not in ("super_admin", "Super Admin")`, groups `db.agents.aggregate([{"$group": {"_id": "$tenantId", "n": {"$sum": 1}}}])` and loops `db.tenants.find({})`. [VERIFIED: mssp_endpoints.py:112-126]
- `MSSP_GUARD = catalogue_guard("msspMonitoring", read=("view:mssp",), write=("manage:mssp",))` and `tenant_admin` holds `view:mssp`/`manage:mssp` (rbac_defaults.py:63-64 region) so MSSP is also a customer screen. Partner portal must NOT reuse MSSP routes. MSSP lists will include partner orgs unless filtered: add `type != "partner"` filters to `mssp_endpoints.py:24,126,180`, `get_tenants` (or return `type` and let the UI filter), and other "every tenant" loops where a partner org is meaningless (licensing, retention, autonomy ensure: harmless but wasteful). Decision per loop is cheap; the list is above.
- Partner usage shape (recommended): `GET /api/partner/overview` -> `{pool: {size, handedOut, free, expiresAt}, customers: [{id, name, seatsAssigned, seatsUsed, agentsOnline, agentsTotal, licenseExpiresAt}]}`. CSV is generated client-side with `toCsv`/`downloadCsv` (`utils/csvExport.ts`: `csvCell` prefixes `'` for a leading `= + - @ \t \r`).

### 9. Tests
- Real-Mongo fixture `tests/_mongo_test_db.py::mongo_db` creates a throwaway DB named `omni_test_<hex>` and **defaults to the live mongod** (`MONGO_TEST_URL` default `mongodb://127.0.0.1:27017`); `tests/conftest.py:37` also defaults to `mongodb://localhost:27017`. Run DB tests only against a private mongod: `GLIBC_TUNABLES=glibc.pthread.rseq=1 /usr/bin/mongod --dbpath <tmp> --port 27998 --bind_ip 127.0.0.1 --fork ...` with `MONGO_TEST_URL`, `MONGODB_URL`, `MONGO_URI` set (`rseq=0` fails on kernel 7.0). [VERIFIED: _mongo_test_db.py:1-12; conftest.py:37; CITED: memory phase-82-execution-2026-10-31]
- Concurrency pattern to copy: `asyncio.gather(*(licensing.try_claim_seat(mongo_db, T) for _ in range(20)))` then assert exactly the free count succeeded (test_licensing.py:58). [VERIFIED]
- Isolation pattern: `test_platform_role_isolation.py` hands code the RAW database and asserts a tenant-A admin gets no tenant-B rows (docstring "every case hands the code the RAW database"). [VERIFIED lines 1-10]
- Route auth baseline: every route needs an auth dependency unless in `REVIEWED_UNAUTHENTICATED`; a new public accept-invite route (if not reusing confirm) must be added there. [VERIFIED: test_route_auth_baseline.py:1-12]
- Catalogue parity: `parity_offenders(records, manifest, modules=[...])`; `SLICES` in `tests/_catalogue_parity.py` partitions views across mount files ("98 in-scope sidebar catalogues ... plus twelve enforced views", comment lines 20-21) so two new views and a new mount file require editing `SLICES` and any pinned counts in `test_catalogue_manifest.py`/`test_catalogue_slice_*` (not read in full; run them first). [VERIFIED partial]
- Pinned sets that will fail and must be edited deliberately: `test_custom_role_mfa.py::test_admin_tier_selects_exactly_the_builtin_admin_roles` compares the MFA role set to `BUILTIN_ADMIN_TIER`; `test_rbac_defaults.py` keeps expected sets as literals; role-matrix tests iterate `rbac_defaults.ROLE_DEFAULTS` (test_catalogue_slice_billing_identity.py:126, 163, 178). [VERIFIED lines]
- Frontend tests: `vitest run` (`package.json` "test"), existing `src/__tests__/*.test.tsx`. [VERIFIED: package.json]

## Common Pitfalls

### Pitfall 1: A customer's seats change through a path that skips the pool
**What goes wrong:** Billing PATCH or Pending-approve `raise_limit_by` raises `license.maxAgents` and the sum exceeds the pool. **Why:** three writers exist (section 3). **Avoid:** hook both into `partner_pool.change_allotment`; drift test forbidding other writers. **Signs:** `reconcile_pools` reports `allocated < sum`.

### Pitfall 2: `tenants` looks scoped but is not
**What goes wrong:** a partner route does `db.tenants.find({})` or filters by a client-supplied id. **Avoid:** raw handle, explicit `partnerId` filter from the token, allowlist projection, 404 on foreign ids. **Signs:** a response containing a customer of another partner in the two-partner test.

### Pitfall 3: Partner org gets default seats and shows up in every tenant loop
**What goes wrong:** `license_of` invents `maxAgents = 5`; `reclaim`, `reconcile`, retention, autonomy loops process the partner org; MSSP/Tenants lists mix partners with customers. **Avoid:** explicit `license.maxAgents: 0`, skip `type == "partner"` in `licensing` loops, filter or label in lists.

### Pitfall 4: Invite takeover and broken link
**What goes wrong:** returning the link to the partner lets it set the customer admin's password; the existing email link is `localhost:5173`; no page consumes the token; an email already in another org makes login ambiguous. **Avoid:** section 4 rules.

### Pitfall 5: Suspension only at login
**What goes wrong:** existing 15-minute access tokens and refresh cookies keep working, and MFA/passkey/SSO issue tokens elsewhere. **Avoid:** chokepoint in `verify_token_async` + cutoff revocation.

### Pitfall 6: Partner role leaks into customer tenants or vice versa
**What goes wrong:** a customer admin assigns a partner role; a partner org gets a tenant role (so it would hold tenant permissions); role documents add permissions. **Avoid:** `assert_role_fits_tenant_type`, PARTNER_ONLY_PERMISSIONS banned from role docs, Super-Admin-only assignment, directory-mapping refusal.

### Pitfall 7: Super Admin sees "Partner portal" in the sidebar (or partner sees Super Admin items)
`evaluateViewAccess` allows everything for the owner (viewAccess.ts:29-30). The UI contract must gate the portal entry to partner roles. Partner users must hold only partner permissions so `NAV_GROUPS` hides the rest; also check `App.tsx` calls such as `api.fetchTenants()` gated by `_isSuperAdmin` (App.tsx:488, 502) do not run for partners (not read in full).

### Pitfall 8: Reconcile and expiry details
String-compare of ISO timestamps differs when one has microseconds; compare parsed datetimes (`license_rules.expired` does). Pool expiry is wall-clock: check in Python, not inside the `$expr`.

### Pitfall 9: Pinned tests and the 500-line rule
`tenant_endpoints.py` is 767 lines and `rbac_defaults.py` 349: new code goes in new modules (CLAUDE.md "Keep files under 500 lines"); edit existing files minimally.

## Code Examples

### Reconcile (mirrors `licensing.reconcile_all`)
```python
async def reconcile_pools(raw):
    sums = {r["_id"]: r["n"] async for r in raw.tenants.aggregate([
        {"$match": {"partnerId": {"$type": "string"}}},
        {"$group": {"_id": "$partnerId", "n": {"$sum": "$license.maxAgents"}}}])}
    async for p in raw.tenants.find({"type": "partner"}, {"_id": 0, "id": 1, "partner.allocated": 1}):
        true = sums.get(p["id"], 0)
        if p["partner"]["allocated"] != true:
            await raw.tenants.update_one({"id": p["id"]}, {"$set": {"partner.allocated": true}})
            # audit_ledger.event("partner.pool_reconciled", ...) and log WARNING
```
(Run it where `licensing.reconcile_all` runs, app_background_tasks.py:338; a concurrent claim between aggregate and set can briefly under-count: run it only on the periodic job and re-check, or use `$inc` by the difference.)

### Partner and customer document layout (recommended)
```
partner org: {id, name, type: "partner", partner: {poolSize, allocated, expiresAt|None, screenCeiling: [...], status: "active"|"suspended", suspendedAt, suspendedBy},
              license: {maxAgents: 0, seatsUsed: 0, inactiveReclaimDays: 30}, enabledFeatures: [], createdAt}   # no registrationKey, no agentCapabilities
customer:    existing tenant doc + partnerId: "<partner id>"   # field absent = direct customer (D-12, no backfill)
migration 029: tenants index {partnerId: 1} (partial: partnerId is a string), {type: 1}; no data change
```

## State of the Art

| Old | Current | Impact |
|-----|---------|--------|
| Role literals per endpoint | single table `rbac_defaults` + drift guard (Phase 75) | new roles go in the table, no literals elsewhere |
| Route guards ad hoc | manifest + `catalogue_guard` + parity test (Phase 76) | new routes need manifest entries and mounts |
| Audit via legacy writers | `audit_ledger` chain (C5) | use `audit_ledger.event` |

## Runtime State Inventory

Not a rename/refactor phase, but it adds a type marker to an existing collection.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Existing `tenants` docs have no `type`/`partnerId` | None: absent = direct customer (D-12). Migration 029 adds indexes only |
| Live service config | None | None |
| OS-registered state | None | None |
| Secrets/env vars | `FRONTEND_URL` (invite link base) not verified set on this VM; SMTP unset (memory) | Planner adds a config check; invite degrades to `emailSent:false` |
| Build artifacts | UI is published by the user (`/var/www`); backend runs from the checkout | UI publish and restart are the user's (memory git-push-needs-user) |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python3 | backend tests | yes | 3.12.3 | -- |
| node | vitest/build | yes | present (`/usr/bin/node`) | -- |
| mongod binary | real-Mongo tests | yes | 8.0.34 | private instance on a spare port (never the live 27017) |
| Live mongod 27017 | -- | not touched | -- | -- |
| SMTP | invite email | no (memory) | -- | `emailSent:false` + Super Admin set-password |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-asyncio) backend; vitest 5 frontend |
| Config file | `/home/azureuser/enterprise-omni-agent-ai-platform/pytest.ini`; `backend/tests/conftest.py` |
| Quick run command | `cd backend && python -m pytest tests/test_partner_pool.py -x -q` with `MONGO_TEST_URL` pointed at a private mongod |
| Full suite command | `npm run test:backend` and `npm test` (full backend suite takes about 24 min, memory) |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PART-03 | 20 concurrent allotments never exceed pool; CAS on same customer; lower to used only; pool shrink refused with handed-out count | integration (real Mongo) | `pytest tests/test_partner_pool.py -x` | Wave 0 |
| PART-03 | `license.maxAgents` writers all pool-aware; drift test | unit | `pytest tests/test_partner_license_writers.py` | Wave 0 |
| PART-04 | expired pool refuses create/hand-out; `hold_reason` returns `license_expired` for a partner customer; running agent unaffected | integration | `pytest tests/test_partner_expiry.py` | Wave 0 |
| PART-05 | two partners: A never sees B's or direct customers or partner orgs; response keys equal the D-01 allowlist exactly; foreign id is 404 | integration | `pytest tests/test_partner_isolation.py` | Wave 0 |
| PART-05 | role matrix: partner roles fail `can_read_all_tenants`, `has_platform_permission`, not in `SUPER_ROLES`/`platform_scope_roles`; hold no permission outside the two partner strings; viewer write refused by middleware and guard | unit | `pytest tests/test_partner_roles.py` | Wave 0 |
| PART-05 | route walk: with a partner token every mounted route outside the partner allowlist and self-service prefixes denies (guards) or is on a reviewed ledger of bare-`get_current_user` routes | contract | `pytest tests/test_partner_route_surface.py` | Wave 0 |
| PART-01 | suspend: next request 403 (existing access token), refresh refused, login refused, customers/seats untouched; reinstate restores | integration | `pytest tests/test_partner_suspension.py` | Wave 0 |
| PART-02 | create customer draws seats, invite row has 7-day expiry, response has no token/registrationKey, global email clash refused, accept via confirm endpoint then MFA enroll required | integration | `pytest tests/test_partner_onboarding.py` | Wave 0 |
| PART-06 | ceiling subset, START_FEATURES allowed, unknown string and `all` refused, parents required | unit | `pytest tests/test_partner_ceiling.py` | Wave 0 |
| PART-07 | move returns allotment, claims new pool or 409, audit entry chained, pre-existing orgs have no `partnerId` after migration 029 | integration | `pytest tests/test_partner_move.py` | Wave 0 |
| PART-08 | overview totals = pool size, handed out, free; per-customer counts; matches seat counters | integration | `pytest tests/test_partner_usage.py`; `npx vitest run` for CSV | Wave 0 |
| manifest/parity | new catalogues + mounts; existing parity/baseline/MFA/rbac_defaults tests updated | contract | `pytest tests/test_catalogue_route_parity.py tests/test_catalogue_manifest.py tests/test_route_auth_baseline.py tests/test_custom_role_mfa.py tests/test_rbac_defaults.py` | exist; edit |

### Sampling Rate
- **Per task commit:** the single new test file for that task plus `tests/test_rbac_defaults.py`.
- **Per wave merge:** all `test_partner_*`, parity, manifest, baseline, feature-switch tests, `test_licensing.py`, `test_tenant_license_api.py`.
- **Phase gate:** full backend suite on a private mongod (expect the known 5 failures from memory), plus `npm test`.

### Wave 0 Gaps
- [ ] Run (do not edit yet) `test_catalogue_manifest.py`, `test_catalogue_slice_*`, `test_tenant_feature_switches.py` to learn pinned counts that two new nav catalogues will trip.
- [ ] `tests/_partner_fixtures.py`: two partners, three customers each, direct customer, users of each role, tokens.
- [ ] private mongod recipe documented in the plan; `MONGO_TEST_URL` set in every test command.

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | existing login + MFA (admin tier); invite token single-use, 7-day, via `password_reset_tokens` |
| V3 Session Management | yes | `revoke_user_sessions` cutoff on suspend; chokepoint check |
| V4 Access Control | yes | partner id from token only, allowlist projection, partner-only permissions, role-to-tenant fitting, read-only second wall |
| V5 Input Validation | yes | pydantic bounds (`ge=0, le=MAX_AGENTS_CEILING`), switch-string validation vs `tenant_features`, email/name length limits, CSV formula guard |
| V6 Cryptography | no new | reuse `hash_password`; tokens via `uuid4`/`secrets` (prefer `secrets.token_urlsafe` for invites) |
| V8 Data Protection | yes | partner responses never carry registrationKey, apiKeys, emailConfig, users |
| V11 Business logic | yes | atomic pool, reconcile, pool-shrink guard |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Partner reads another partner's/direct customers via exempt `tenants` | Information disclosure | explicit `partnerId` filter, 404 on foreign ids, two-partner test |
| Partner reads customer security data through a bare-`get_current_user` route | Information disclosure | partner roles hold no permission; route-surface test with ledger of authenticated-only routes |
| Partner takes over customer admin via invite token/resend | Elevation of privilege | never return token; resend only before first sign-in |
| Concurrent hand-outs exceed pool | Tampering | conditional `$expr` claim + CAS + reconcile |
| Suspended partner keeps a live session | Elevation | chokepoint + cutoff |
| Partner role assigned in customer tenant / platform role in partner org | Elevation | `assert_role_fits_tenant_type`, Super-Admin-only assignment |
| Customer name oracle on create | Information disclosure | generic "name unavailable" |
| CSV formula injection in customer names | Tampering | `csvCell` guard |
| `X-Tenant-ID` abuse | Spoofing | owner-only [VERIFIED tenant_middleware.py:188-197]; partner routes ignore it |

## Open Questions

1. **Who creates partner staff (partner admin/viewer users)?** D-04/D-09 do not say. Recommendation: Super Admin invites the first partner admin when appointing; the partner admin invites its own colleagues (admin/viewer) through the same invite helper, restricted to partner roles in its own org. Needs user confirmation (A8).
2. **Moving a customer to another partner:** D-11 says the allotment returns to the old pool but not where it is drawn from on the new side. Recommendation: claim from the new partner's pool atomically and refuse with the free count if it does not fit; Super Admin can enlarge the pool first. A customer moved to direct keeps its seats as a direct licence.
3. **Ceiling shrink and moves vs screens already ticked:** do not strip customer screens when the ceiling is reduced or the customer is moved (running customers keep what they use); the partner can only add within the ceiling afterward. Needs confirmation.
4. **Does the Super Admin Partners screen need partner-user management inside it?** Likely yes for invite/disable; UI-SPEC decides.
5. **Pinned test counts** for manifest/slices/feature switches were not run; Wave 0 must read them.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No new packages are needed | Standard Stack | Low |
| A2 | The local mongod is a standalone (no `replication:` in `/etc/mongod.conf`); not confirmed by connecting | 3 | Low: design uses no transactions |
| A3 | Partner `view:profile` is unnecessary; `/api/auth`, `/api/mfa`, `/api/passkey` are enough for partner self-service | 2 | UI may need a profile page |
| A4 | Partner viewer does not need MFA | 2 | Product/security preference; one-line change to add |
| A5 | Socket.IO delivers per tenant/sid so a partner org receives nothing of customers (websocket_manager not read in full) | 1 | Medium: verify rooms before shipping |
| A6 | Role listing filters `doc_tenant_id="platform"` roles out of customer tenants (role_contents not read) | 2 | Customers could see partner role names (cosmetic) |
| A7 | Audit placement (platform chain + partner chain mirror) is acceptable | 5 | Low |
| A8 | Partner admin may invite its own partner colleagues | Open Q1 | Scope |
| A9 | Do not strip screens on ceiling shrink/move | Open Q3 | Product |
| A10 | `FRONTEND_URL` is the right invite base-URL setting and is set in production | 4 | Invite links wrong; add a config check |

## Sources

### Primary (HIGH, read this session)
- backend/database.py:28-38, 65-72, 157-180; tenant_middleware.py (all); auth_roles.py; rbac_utils.py; rbac_defaults.py; role_assignment.py; licensing.py; license_rules.py:1-60, 108-150; tenant_endpoints.py:1-160, 183-290, 700-767; mssp_endpoints.py; authentication_service.py:56-224, 300-484; authentication_endpoints.py:120-380, 409-460; auth_password_reset_endpoints.py:20-249; user_endpoints.py:1-125, 264-322; audit_ledger.py:1-60, 150-260; pending_agents.py:380-410; migrations/runner.py, 028; catalogue_guards.py:1-100; catalogue_mounts.py; catalogue_mounts_billing_identity.py; tenant_features.py:1-110, 205-225; tests heads (_mongo_test_db, test_licensing, test_platform_role_isolation, test_route_auth_baseline, test_catalogue_route_parity, test_custom_role_mfa, test_catalogue_manifest, _catalogue_parity); utils/permissions.ts:55-113; utils/viewAccess.ts; utils/csvExport.ts; shared/catalogue-access.json (parsed); /etc/mongod.conf.
### Secondary
- Project memory: phase-82-execution (private mongod recipe), optional-integrations-unconfigured, git-push-needs-user.

### Not read (planner should read before editing)
`rbac_service.py` beyond lines 75-125, `role_contents.py`, `mfa_service.py`, `websocket_manager.py`, `router_registry.py`, `app_startup.py`, `app_background_tasks.py` (only line refs), `tenant_endpoints.py` 292-700 (delete_tenant body only skimmed via grep), `catalogue_guards.py` 100-194, `tenant_features.py` 110-205, `tests/_route_walk.py`, `test_rbac_defaults.py`, `test_tenant_feature_switches.py`, `App.tsx`, `components/Sidebar.tsx`, `types.ts`, `utils/catalogueAccess.ts`, `components/MSSPDashboard.tsx`, `TenantLicensePanel.tsx`, `ManageTenantModal.tsx`, `AddNewTenantModal.tsx`, `TenantManagementDashboard.tsx`, `enrollment_keys.py`.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH (no new packages)
- Architecture and pool design: HIGH (patterns verified in code), A2 low impact
- Pitfalls: HIGH for items cited with lines; MEDIUM for frontend wiring and pinned test counts
- Frontend surfaces: MEDIUM (App/Sidebar not read); a UI design contract is being written separately. Needed surfaces: (1) Super Admin **Partners** screen: appoint form (name, pool, expiry, ceiling picker, first admin invite), table with pool size/handed out/free/expiry/status, suspend/reinstate, change pool (shows the handed-out count on refusal), move customer, per-partner customer list; (2) **Partner portal**: pool summary, customer table (name, seats assigned/used, agents online/total, licence expiry), create-customer + invite form, seat +/- control modelled on `TenantLicensePanel`, per-customer screen ticker limited to the ceiling, CSV export button, viewer variant with all controls hidden; (3) public **Accept invite** page (set password, then MFA enrollment); (4) sidebar/landing: partner users see only the portal, Super Admin sees Partners and not the portal.

**Research date:** 2026-11-02
**Valid until:** 2026-12-02 (internal codebase; re-check if phases 83-86 touch `rbac_defaults`, `licensing` or the manifest)
