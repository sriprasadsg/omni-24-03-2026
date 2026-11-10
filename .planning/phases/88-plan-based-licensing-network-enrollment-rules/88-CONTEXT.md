# Phase 88: Plan-Based Licensing & Network Enrollment Rules - Context

**Gathered:** 2026-11-10
**Status:** Ready for planning

<domain>
## Phase Boundary

A tenant's subscription plan (Free / Pro / Enterprise / Custom) decides what it may enroll and use: its agent
seat limit, which screens can be switched on for it, and a 14-day trial on Free. Every tenant also gets an
allowed-network rule: its first agent's public IP is learned automatically, and a NEW machine enrolling from
any other public IP is held Pending until the Super Admin allows that network. A machine whose hardware is
live in another tenant is held Pending for the Super Admin instead of enrolling twice. Machines already
enrolled are never cut off by any of these rules.

Not in this phase: payments, invoices, prices or self-service upgrades (billing stays out of scope per
`.planning/PROJECT.md`); enforcing the data/API/AI usage figures in `billing_service.SUBSCRIPTION_LIMITS`
(they stay warnings).

</domain>

<decisions>
## Implementation Decisions

### Before the discussion (user, 2026-11-10)
- **D-01:** The network rule holds NEW machines only: a machine enrolling from a network that is not allowed is held Pending for approval, the same pattern as the C4 hardware allowlist (`license_rules.hold_reason`). Agents already enrolled are never re-checked or cut off, so laptops at home or travelling keep working.
- **D-02:** Cross-tenant duplicate hold: a machine whose hardware belongs to a live seat-holding agent in another tenant is held Pending for platform (Super Admin) approval instead of enrolling a second time. Details in D-31..D-36.

### Plan limits table
- **D-03:** Seats per plan: Free 5, Pro 50, Enterprise 500, Custom set per tenant by contract.
- **D-04:** No OS or server-class restriction by plan: every plan may enroll every OS class. (The existing C4 OS-class sub-limits stay as they are, set per tenant.)
- **D-05:** Free is a 14-day trial. After it ends, new machines are held Pending (the existing licence-expiry rule) and running agents keep working. Nothing else stops: every screen stays on (see D-21).
- **D-06:** Allowed networks are the same on every plan: one network by default, learned automatically from the public IP the tenant's first agent enrolls from. Any further network is decided only by the Super Admin (allow or refuse). Plans do not change the network count.
- **D-07:** When the Super Admin allows a machine held for a new network, the network is allowed: it joins the tenant's allowed networks, so later machines from it enroll without a hold.
- **D-08:** Today's Free tenants (ABC, shieldforgetech) start their 14-day trial when Phase 88 goes live, not from their creation date. — **Reversibility:** costly — the trial start stored per tenant at go-live is what every later trial check and reminder reads.

### Plan vs overrides, partners and downgrades
- **D-09:** The plan sets the seat limit. The Super Admin may override one tenant's number (any number, above or below the plan); the override is shown as such, and removing it returns the tenant to its plan's number.
- **D-10:** A seat override stays when the tenant changes plan, until someone removes it.
- **D-11:** For a partner's customer the partner's allotment (Phase 87 D-05, `license.maxAgents` from the pool) decides the seats, not the plan. The plan still decides the customer's screens and the Free trial.
- **D-12:** A tenant that moves to a plan it already exceeds keeps every running agent; new machines are held Pending until it is under its limit (same rule as expiry and partner seat cuts).
- **D-13:** The Super Admin and partners change plans. A partner changes plans only for its own customers, and only among the plans the Super Admin allows that partner (a per-partner plan ceiling, like its screen ceiling). The existing payment-subscription route that sets `subscriptionTier` keeps working and goes through the same plan-change rules.
- **D-14:** The Super Admin edits the plan table on a Plans screen. Changing a plan's numbers (e.g. Pro 50 to 60 seats) applies at once to every tenant on that plan that has no override. — **Reversibility:** costly — plan limits become stored data read by enrollment, the licence panels and the partner portal instead of constants.
- **D-15:** A Free trial can be extended by the Super Admin, or by the partner for its own customers; each extension is recorded in the audit ledger.
- **D-16:** Tenant admins are reminded 7 days and 1 day before their trial ends (reusing the licence-expiry reminders, today 30/7/1 days); for a partner's customer the partner is told too.
- **D-17:** Custom has no defaults: the Super Admin (or the partner) sets seats and screens per tenant by contract. Custom has no trial and no screen ceiling of its own.
- **D-18:** At go-live today's hand-set seat limits (5 on every tenant) are replaced by the plan's number: Exafluence (Pro) to 50, Platform (Enterprise) to 500, ABC and shieldforgetech (Free) stay at 5. Partner customers keep their allotments. — **Reversibility:** one-way — the migration overwrites `license.maxAgents` on every direct tenant; the old numbers survive only if the migration records them.
- **D-19:** Tenant admins see on their licence panel: plan name, seats used of the limit (marked when it is an override), allowed networks, and days left in a Free trial.
- **D-20:** A machine held because the trial ended can be approved by the Super Admin like any Pending hold; the trial itself stays ended.
- **D-21:** After a Free trial ends nothing stops except enrolling new machines: running agents and every screen keep working.
- **D-22:** One trial per tenant: a tenant that already had its trial or a paid plan returns to Free (for example when its paid subscription is cancelled) with the trial already ended. — **Reversibility:** costly — the per-tenant trial record must persist across plan changes for this to hold.
- **D-23:** A new organization's trial starts when it is created; for a self sign-up, when the Super Admin approves the sign-up.
- **D-24:** Every new organization starts on the Free trial: self sign-ups and the Super Admin's Add Tenant both default to Free (the Add Tenant form defaults to Enterprise today). The creator may pick another plan.
- **D-25:** When a tenant's plan or seat limit changes, its admins get an in-app notice and the change (who, from, to) is recorded in the audit ledger.
- **D-26:** The Platform organization (`platform-admin`) is exempt: no plan, trial or network limits.

### Screens by plan
- **D-27:** The plan is a screen ceiling: each plan lists the screens it may have, and the Super Admin or partner still ticks screens one by one (spec C6 `enabledFeatures`), but only within the plan. Same model as the Phase 87 partner screen ceiling (D-10 there). The server refuses a screen outside the ceiling.
- **D-28:** Moving to a smaller plan leaves screens already on switched on; the smaller plan only limits what can be ticked from then on (as Phase 87 D-19). During and after a Free trial the trial's ceiling is Free's list.
- **D-29:** Each plan's screen list starts from the `minTier` already in `backend/feature_catalog.py` (cumulative: Free within Pro within Enterprise) and is editable by the Super Admin on the Plans screen. Switchable screens with no `minTier` (the C6 switches outnumber the 59 catalogue features; the planner counts them) go into the plan of the catalogue feature they belong to (e.g. a Compliance sub-screen follows Compliance); anything left over starts on Enterprise.
- **D-30:** For a partner's customer, a screen may be ticked only if it is inside both the partner's ceiling and the customer's plan.

### Network and duplicate rules
- **D-31:** A network is an exact public IP. When allowing one, the Super Admin may widen the entry to a CIDR range (e.g. an office /29).
- **D-32:** Only the Super Admin allows or refuses a new network, for direct and partner customers alike.
- **D-33:** The tenant admin sees a machine held for a new network as Pending with the reason (e.g. "new network 203.0.113.7, waiting for platform approval") and cannot approve it.
- **D-34:** At go-live every public IP a tenant's enrolled agents report today becomes one of its allowed networks, so no current office is blocked from adding machines.
- **D-35:** Cross-tenant: a machine counts as live in tenant A when a seat-holding agent there with the same BIOS serial or SMBIOS UUID was seen in the last 24 hours (the in-tenant rule of spec C2). A MAC address alone never counts. Silent or uninstalled agents do not block.
- **D-36:** While held, tenant A sees nothing; tenant B's admin sees the machine Pending with an unnamed reason ("this computer is enrolled in another organization; waiting for platform approval"). Only the Super Admin sees both organizations' names.
- **D-37:** When the Super Admin approves a cross-tenant hold, the machine moves to B: A's agent is retired (marked Replaced) and its seat freed. One computer, one licence. — **Reversibility:** costly — a Replaced agent in A is not restored by any existing flow.
- **D-38:** When A's copy is silent (no hold, D-35), B's enrollment also retires A's stale agent (Replaced, seat freed); A sees it as Replaced without B's name.

### Settled after research (2026-11-10, user answers to 88-RESEARCH.md open questions)
- **D-39:** The payment route (`POST /api/payments/subscribe`) only records the subscription and validates the plan name; it no longer changes the plan. The plan changes only when the Super Admin, or the partner for its own customers, applies it (refines D-13).
- **D-40:** When the Super Admin ticks screens for a partner's customer, only the customer's plan limits it; the partner's screen ceiling limits only what the partner ticks (refines D-30).
- **D-41:** The Platform organization is exempt with no seat limit at all; D-18's 500 seats does not apply to it (supersedes D-18 for Platform; D-26 stands).
- **D-42:** When the Super Admin widens an allowed network to a range, the widest allowed is an IPv4 /24 or an IPv6 /48.
- **D-43:** D-38 stays, with a safeguard: every retirement of another tenant's silent copy raises a platform alert naming both organizations (Super Admin only), and the Super Admin can restore the retired agent.
- **D-44:** Moving a tenant from a partner to direct keeps its seats as an override (unless equal to its plan's number), so a later plan edit cannot shrink them; moving a tenant from direct to a partner clears the override and the partner's allotment decides.
- **D-45:** A machine held because the Free trial ended shows its own reason, `trial_ended` ("trial ended"), with the same behavior as an expired licence.
- **D-46:** Migration 034 ships the generated screen seed (research counts: 19 Free, 69 Pro, 120 Enterprise of 208 switches); the Super Admin edits each plan's list on the Plans screen afterwards. No review checkpoint before the migration. Live tenants keep their screens (D-28).

### Claude's Discretion
- Field names, collection layout, the migration number (034 or later; 033 is the uncommitted machine-identities migration) and where the plan table lives, as long as D-14 (editable, applies at once) and D-18 (go-live numbers) hold.
- Which IP the network rule checks. The agent reports its own `publicIp` (it controls that value); the server also sees the request's source address (`sourceIp`). Research must establish which one nginx passes through reliably and use a server-observed address, not the agent's claim, for the allow decision.
- How `feature_bundles.py` (assigned bundles) relates to plans: the enforced screen switches are `tenant_features` (C6); the planner decides whether bundles are mapped, left alone or retired, without changing what any tenant can use today except as D-27/D-28 say.
- Wording of the Pending reasons, notices and reminders, within D-33/D-36.
- Where the Plans screen sits for the Super Admin, and how the partner portal shows the plan ceiling.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and earlier decisions
- `.planning/ROADMAP.md` — Phase 88 goal (plan limits, network rule, cross-tenant duplicate hold).
- `.planning/PROJECT.md` — "Billing and subscription management" is out of scope; plans set limits, no payments.
- `.planning/REQUIREMENTS.md` — PART-01..08 (partner pools, ceilings, expiry) that plan limits must coexist with.
- `.planning/phases/87-partner-and-reseller-channel/87-CONTEXT.md` — D-05 (allotment = `license.maxAgents`, atomic), D-06 (never cut off), D-08 (expiry: new held, running continue), D-10/D-19 (screen ceiling; screens on stay on).

### Licensing and enrollment (spec C2/C3/C4; the spec itself was never filed, the code is the record)
- `backend/license_rules.py` — enrollment rule order (key, expiry, hardware allowlist, OS sub-limit, group sub-limit, then seat), hold reasons, `send_expiry_reminders` (30/7/1 days).
- `backend/licensing.py` — `license_of`, `try_claim_seat`, `seats_available`, `release_seats`, `NON_SEAT_STATUSES`.
- `backend/pending_agents.py` — Pending hold, approve/reject, denylist, platform alerts, admission gate.
- `backend/agent_allowlist.py` — hardware allowlist (entries, CSV import, `allowlistMode`): the pattern for allowed networks.
- `backend/agent_registry_endpoints.py` — `register_agent` (where enrollment rules run; publicIp/sourceIp; `_take_over_hardware_seat`, `_seen_within`, 24 h rule).
- `backend/seat_identity.py` — hardware keys; `hardware_match_filter` is tenant-scoped today (cross-tenant check needs an unscoped variant).
- `backend/machine_identity.py`, `backend/asset_identity.py` — one agent id per machine per tenant and hardware-bound assets (added 2026-11-10, uncommitted at the time of this discussion).

### Plans, screens and billing
- `backend/tenant_features.py` — C6 screen switches (`SWITCHABLE`, `enabledFeatures`), the enforced feature control.
- `backend/feature_catalog.py` — 59 features with `minTier` (10 Free, 32 Pro, 17 Enterprise), never enforced today.
- `backend/feature_bundles.py`, `backend/bundle_endpoints.py` — a third, bundle-based feature system.
- `backend/partner_platform_service.py` — partner screen ceiling checks (model for the plan ceiling).
- `backend/billing_service.py` — `SUBSCRIPTION_LIMITS` (data/API/AI, warnings only).
- `backend/payment_billing_endpoints.py` — sets `subscriptionTier` on subscription create (line ~76) and cancel (line ~181).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `license_rules.hold_reason`: the place to add the trial, network and cross-tenant checks as further hold reasons; the first failed rule holds the machine Pending with that reason.
- `pending_agents.hold / answer / approve`: the Pending flow, its platform alerts and the PendingAgentsPanel already show held machines and reasons to tenant admins and the Super Admin.
- `agent_allowlist`: entry normalization, list/add/remove and CSV import to mirror for allowed networks.
- `license_rules.send_expiry_reminders`: the hourly reminder job to extend for trial reminders (7 and 1 day).
- `_take_over_hardware_seat` + `_LiveDuplicate` (registration): the in-tenant duplicate rule; D-35..D-38 extend it across tenants.
- `audit_ledger.record_legacy` and the notification service: audit entries and in-app notices for plan changes (D-25) and trial extensions (D-15).

### Established Patterns
- Enrollment rules never touch enrolled agents (C4, Phase 87 D-06/D-08); every new rule here follows that.
- Seat changes are atomic conditional updates (`licensing.try_claim_seat`, Phase 87 D-05); plan-driven seat numbers must not break partner pool accounting.
- Ceilings limit future ticks only; screens already on stay on (Phase 87 D-19).
- Live tenants today: Platform Enterprise, Exafluence Pro (59 screens on), ABC Free (10), shieldforgetech Free (3); every tenant `license.maxAgents` 5.

### Integration Points
- `register_agent` (enrollment) and the licence PATCH / tenant endpoints (plan and override changes).
- Frontend: `components/AddNewTenantModal.tsx` (default tier Enterprise today), `components/ManageTenantModal.tsx` (tier select), `components/TenantLicensePanel.tsx` (tenant view, D-19), the Pending agents panel, the Phase 87 Partner portal, and a new Super Admin Plans screen.
- Migration (034+): plan numbers onto direct tenants (D-18), trial start for current Free tenants (D-08), allowed networks from enrolled agents' public IPs (D-34).

</code_context>

<specifics>
## Specific Ideas

- The user's own words on networks: "One IP should be allowed normally and other IP should be decided by the super admin to allow or disallow" (refined to D-06, D-07, D-31, D-32).
- The case that started this: EILT0197 enrolled three times on 2026-11-10 under different agent ids, which the one-id-per-machine work (machine_identity) already addressed; cross-tenant duplicates are the remaining hole.

</specifics>

<deferred>
## Deferred Ideas

- Payments, invoices, prices and tenant self-service upgrades (billing, out of scope per PROJECT.md).
- Enforcing the data/API/AI usage limits in `billing_service.SUBSCRIPTION_LIMITS` per plan (they stay warnings).
- Alert-only or hard-block variants of the network rule (the user chose hold-new-machines).
- Duplicate detection for machines identified only by a MAC address (MACs are too easy to copy).
- Two different computers with the same hostname in one tenant still get "already enrolled" (409); hostname uniqueness per tenant predates this phase.

</deferred>

---

*Phase: 88-plan-based-licensing-network-enrollment-rules*
*Context gathered: 2026-11-10*
