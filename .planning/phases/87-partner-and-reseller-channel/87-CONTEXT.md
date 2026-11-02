# Phase 87: Partner and Reseller Channel - Context

**Gathered:** 2026-11-02
**Status:** Ready for planning

<domain>
## Phase Boundary

The platform sells through partners the way a vendor appoints dealers. A Super Admin appoints partner organizations and gives each a pool of agent seats. A partner admin creates the partner's own customer organizations and assigns seats to each from the pool. Partner staff see only their own customers, and only seats and usage, never customer security data. Usage rolls up per partner with a CSV export.

Out of scope for this phase: invoicing or billing per partner, monthly usage history, sub-dealers (a second partner level), customer-controlled partner access, partner access to customer security data, and customer self-sign-up with a partner code.

The user's own motivation (2026-11-02): appoint retailers and dealers, give each 100 or 1,000 licences, test several retailers at once and add more over time.
</domain>

<decisions>
## Implementation Decisions

### Partner reach
- **D-01:** Partner staff see only seats and usage for their customers: customer name, seats assigned and used, agent counts (online and total), licence expiry. They see no alerts, assets, findings, users or any other customer data, through any route. — **Reversibility:** costly — every partner-facing query and route is written against this boundary, and widening it later means a new consent model.
- **D-02:** The reach is the same for every partner and every customer. Customers cannot grant more and the Super Admin cannot widen it per partner in this phase.
- **D-03:** One level only: Super Admin, then partner, then customer. A partner cannot appoint sub-dealers.
- **D-04:** Two partner roles. A partner admin creates customers, moves seats and invites customer admins. A partner viewer only reads the partner's customer list, pool and usage. Partner roles hold no tenant permission and no platform permission. They must not pass `can_read_all_tenants` or `has_platform_permission`, and they must never be added to `SUPER_ROLES` or the platform-scope role sets.

### Seat pool rules
- **D-05:** A partner has a fixed pool, for example 1,000 seats, which it splits among customers. Each customer's allotment is its existing `license.maxAgents`. The sum of allotments can never exceed the pool, enforced atomically in the same style as `licensing.try_claim_seat` (conditional update, no read-then-write race). — **Reversibility:** one-way — the pool and allotment fields and their migration become the stored contract for every partner and customer.
- **D-06:** A partner can lower a customer's allotment only down to the seats that customer uses now. Running agents are never cut off by a partner.
- **D-07:** The Super Admin cannot shrink a partner's pool below the total already handed out. The refusal says how many seats are handed out, so the partner can be asked to take seats back first.
- **D-08:** A pool can carry an expiry date. After it, the partner can neither create customers nor hand out seats. Its customers' licences follow today's expiry rule in `license_rules.py`: new agents are held Pending, and agents already enrolled keep working. No trial pools in this phase.

### Customer onboarding
- **D-09:** The partner admin creates the customer organization, sets its seats from the pool, and invites the customer's first admin by email. From then on the customer admin runs the organization, with the same rights a directly created organization's admin has today.
- **D-10:** The Super Admin sets a screen ceiling per partner, the set of screens that partner may sell. The partner ticks screens for each customer within that ceiling, using the existing per-organization screen switches (`enabledFeatures`, spec C6). The server rejects any screen outside the ceiling.
- **D-11:** Only the Super Admin can move a customer to another partner or make it a direct customer. Its allotment returns to the old partner's pool, and the move is recorded in the audit ledger.
- **D-12:** Every existing organization stays a direct customer of the platform. The Super Admin can assign one to a partner later, through D-11.

### Partner identity
- **D-13:** A partner is its own organization, marked as type `partner`. It has its own users, login, MFA, sessions and audit trail, all reused unchanged. It has no endpoints, no seats for itself and no security screens. Its users see only a Partner portal. — **Reversibility:** costly — the organization type marker is read by the login, the sidebar and every tenant list.
- **D-14:** The Super Admin gets a new Partners screen. There it appoints a partner, sets its pool, expiry and screen ceiling, sees every partner's pool used and free, and can suspend or reinstate a partner.
- **D-15:** Suspending a partner locks the partner only. Its users cannot log in or move seats. Its customers keep running with the seats they hold, and nothing is taken away.
- **D-16:** The partner's usage roll-up shows the pool size, seats handed out and seats free. Per customer it shows seats assigned, seats used, agents online and licence expiry, with a CSV export. There is no invoicing and no monthly history.

### Claude's Discretion
- Field names, collection layout and the migration number, as long as D-05's atomic guarantee and D-12's "existing organizations untouched" hold.
- Whether the Partner portal is a new sidebar section or a separate view, as long as partner users reach nothing else.
- How an invited customer admin first signs in, reusing the existing invite or password-set flow where one exists.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Seats and enrollment (what the pool sits on)
- `backend/licensing.py`: per-organization seats `license.maxAgents` and `seatsUsed`, the atomic `try_claim_seat`, `MAX_AGENTS_CEILING`, reconcile.
- `backend/license_rules.py`: expiry and sub-limit rules at enrollment (D-08 reuses the expiry behaviour).
- `backend/enrollment_keys.py`: install keys with `maxUses`.
- `backend/tenant_endpoints.py`: tenant creation (`create_tenant` is Super Admin only today), `GET/PATCH /{tenant_id}/license`.
- `components/TenantLicensePanel.tsx`, `components/ManageTenantModal.tsx`, `components/AddNewTenantModal.tsx`, `components/TenantManagementDashboard.tsx`: today's Super Admin tenant and seat screens.

### Roles and the tenant boundary
- `backend/rbac_defaults.py`: role permission table, `platform_support` and `platform_billing` (spec C1), `SUPER_ADMIN_ONLY_PERMISSIONS`, `PLATFORM_ONLY_PERMISSIONS`.
- `backend/database.py`: `TenantIsolatedDatabase` and `TENANT_ISOLATION_EXEMPT_COLLECTIONS`. Every query is scoped to the request's tenant; leaks come only from raw `mongodb.db`, exempt collections and platform-admin context.
- `backend/auth_roles.py`, `backend/rbac_utils.py`, `backend/tenant_middleware.py` (`PlatformReadOnlyMiddleware`): role sets, `can_read_all_tenants` and `has_platform_permission`.
- `shared/catalogue-access.json`: the screen catalogue the per-organization switches (spec C6) and the D-10 ceiling use.

### Roll-up pattern to reuse
- `backend/mssp_endpoints.py`, `components/MSSPDashboard.tsx`: an existing cross-tenant roll-up, Super Admin only. A partner version must be scoped to that partner's customers and carry only D-01's fields.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `licensing.try_claim_seat`: the atomic pattern D-05 must mirror for pool allotments.
- `TenantLicensePanel`: the seat form a partner admin's per-customer seat control can be modelled on.
- `MSSPDashboard` and `/api/mssp/overview`: the shape of a roll-up table across organizations.
- Spec C6 screen switches (`enabledFeatures`): what the partner ticks per customer within the ceiling.

### Established Patterns
- Organizations are documents in `tenants` with `license` embedded. Tenant isolation relies on the request's tenant context, so partner routes need their own explicit, tested scoping. They must never borrow the platform-admin context.
- Platform roles are owner-assignable only and are pinned to the Platform tenant (`assert_role_fits_tenant`). Partner roles need the same pinning to a partner-type organization.
- Route guards come from the catalogue manifest (`catalogue_guard`, `catalogue_exempt`), with `test_route_auth_baseline.py` and `test_catalogue_route_parity.py` checking parity.

### Integration Points
- Login and session: partner users land on the Partner portal only.
- Tenant creation: a partner-created customer goes through the same creation path, with the partner link and an allotment drawn from the pool.
- Agent enrollment: unchanged. Customers keep using their own `license.maxAgents`.
- Audit ledger: appointing, suspending, pool changes, allotments and moves are all recorded.
</code_context>

<specifics>
## Specific Ideas

- The user's first use is testing several retailers at once with 100 or 1,000 seats each, and adding retailers over time.
- The model the user named is Microsoft appointing dealers to sell its products.
</specifics>

<deferred>
## Deferred Ideas

- Invoicing and billing per partner, and a monthly usage history to bill from.
- Sub-dealers: a distributor, then retailers, then customers.
- Customer opt-in to give its partner a read-only security view, and an MSSP-style managed service by partners.
- Customer self-sign-up with a partner code.
- Trial pools with automatic expiry.
</deferred>
