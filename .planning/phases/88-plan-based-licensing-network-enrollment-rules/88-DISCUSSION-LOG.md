# Phase 88: Plan-Based Licensing & Network Enrollment Rules - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-10
**Phase:** 88-plan-based-licensing-network-enrollment-rules
**Areas discussed:** Pre-discussion (2026-11-10, AskUserQuestion before discuss-phase), Plan limits table, Plan vs overrides & downgrades, Screens by plan, Network & duplicate rules

---

## Pre-discussion (2026-11-10, AskUserQuestion before discuss-phase)

### How should the public-IP rule act?

| Option | Selected |
|--------|----------|
| Hold new machines (Recommended) | ✓ |
| Alert only |  |
| Block outside networks |  |

**User's choice:** Hold new machines: a NEW machine enrolling from outside the allowed networks is held Pending for approval; enrolled machines are never cut off

### What should each plan limit?

| Option | Selected |
|--------|----------|
| Agent seats | ✓ |
| Allowed networks | ✓ |
| OS / server types | ✓ |
| Features by plan | ✓ |

**User's choice:** Agent seats, Allowed networks, OS / server types, Features by plan (OS later answered: no restriction)

### How should I build it?

| Option | Selected |
|--------|----------|
| New GSD phase 88 (Recommended) | ✓ |
| Implement directly now |  |

**User's choice:** New GSD phase 88

### Cross-tenant duplicates

**User's choice:** Add to phase 88: hardware (serial/UUID) live as a seat-holding agent in another tenant is held Pending for platform approval

---

## Plan limits table

### How many agent seats should each plan include?

| Option | Selected |
|--------|----------|
| 5 / 50 / 500 / contract (Recommended) |✓ |
| 5 / 100 / contract / contract |  |
| 3 / 25 / 250 / contract |  |

**User's choice:** Free 5 / Pro 50 / Enterprise 500 / Custom per contract

### How many allowed public networks (sites) may each plan register?

| Option | Selected |
|--------|----------|
| 1 / 5 / 25 / contract (Recommended) |  |
| Free none / 5 / unlimited |  |
| Unlimited on every plan |  |

**User's choice:** FREE TEXT: "One IP should be allowed normally and other IP should be decided by the super admin to allow or disallow" (clarification pending)

### Which OS / server classes may each plan enroll?

| Option | Selected |
|--------|----------|
| Free: workstations only (Recommended) |  |
| Servers from Enterprise |  |
| All classes on every plan | ✓ |

**User's choice:** All classes on every plan (no OS restriction by plan)

### Does the Free plan expire?

| Option | Selected |
|--------|----------|
| No, Free is permanent (Recommended) |  |
| 30-day trial |  |
| 14-day trial | ✓ |

**User's choice:** 14-day trial: after it, new machines are held Pending (existing expiry rule), running ones keep working

### Follow-up 1: how is the one default allowed IP set?

| Option | Selected |
|--------|----------|
| automatic (suggested) | ✓ |
| typed in by the tenant admin |  |

**User's choice:** Automatically, learned from the network the tenant's first agent enrolls from

### Follow-up 2: same on every plan?

| Option | Selected |
|--------|----------|
| same on every plan | ✓ |
| bigger plans start with more |  |

**User's choice:** Same on every plan: one network by default; any further network only by the Super Admin (plans do not change the network count)

### Follow-up 3: when the Super Admin allows a machine from another IP, what is allowed?

| Option | Selected |
|--------|----------|
| the network | ✓ |
| only that machine |  |

**User's choice:** The network: it joins the tenant's allowed networks, so later machines from it enroll freely

### Follow-up 4: trial clock for today's Free tenants (ABC, shieldforgetech)?

| Option | Selected |
|--------|----------|
| starts at go-live |✓ |
| counts from creation (expired at once) |  |
| exempt |  |

**User's choice:** Starts when Phase 88 goes live

---

## Plan vs overrides & downgrades

### Does the plan set a tenant's seat limit itself, or only cap what the Super Admin sets?

| Option | Selected |
|--------|----------|
| Plan sets it, override allowed (Recommended) |✓ |
| Plan is a hard ceiling |  |
| Plan sets it, no overrides |  |

**User's choice:** Plan sets it (5/50/500/contract); the Super Admin may override one tenant's number, shown as an override; removing the override returns to the plan number

### For a partner's customer, partner allotment or plan?

| Option | Selected |
|--------|----------|
| Partner allotment wins (Recommended) | ✓ |
| Plan caps the allotment |  |
| No plans for partner customers |  |

**User's choice:** Partner allotment wins (Phase 87 D-05); the plan still decides screens and the Free trial

### Tenant moves to a plan it already exceeds?

| Option | Selected |
|--------|----------|
| Keep running, hold new (Recommended) | ✓ |
| Refuse the downgrade |  |
| Stop the extra agents |  |

**User's choice:** Keep running, hold new: every agent keeps working; new machines are held Pending until under the limit

### Who may change a tenant's plan?

| Option | Selected |
|--------|----------|
| Super Admin only (Recommended) |  |
| Super Admin and partners | ✓ |

**User's choice:** Super Admin and partners (a partner for its own customers); the existing payment-subscription route keeps setting the plan

### Which plans may a partner put its own customers on?

| Option | Selected |
|--------|----------|
| Plans the Super Admin allows (Recommended) | ✓ |
| Any plan |  |
| Any plan except Custom |  |

**User's choice:** Only the plans the Super Admin allows that partner (a per-partner plan ceiling, like its screen ceiling)

### Does the 14-day Free trial apply to a partner's customers?

| Option | Selected |
|--------|----------|
| Yes, same as direct (Recommended) | ✓ |
| No trial for partner customers |  |

**User's choice:** Yes, same as direct customers

### Can the plan numbers change later?

| Option | Selected |
|--------|----------|
| Super Admin edits the table (Recommended) | ✓ |
| Fixed in code |  |

**User's choice:** Super Admin edits the plan table on a Plans screen; changing a plan's seats moves every tenant on it without an override at once

### Can a Free trial be extended?

| Option | Selected |
|--------|----------|
| Yes, by Super Admin or partner (Recommended) |✓ |
| No extensions |  |

**User's choice:** Yes, by the Super Admin or by the partner for its own customers; recorded in the audit ledger

### Who is warned before a Free trial ends?

| Option | Selected |
|--------|----------|
| Tenant admins, 7 and 1 day before (Recommended) |✓ |
| Tenant admins and Super Admin |  |
| No reminders |  |

**User's choice:** Tenant admins 7 and 1 day before (reusing the licence-expiry reminders); for a partner customer the partner too

### What does the Custom plan mean?

| Option | Selected |
|--------|----------|
| Every limit set per tenant (Recommended) |✓ |
| Enterprise plus overrides |  |

**User's choice:** No defaults: the Super Admin (or partner) sets seats and screens per tenant by contract; no trial

### At go-live, what happens to today's hand-set 5-seat limits?

| Option | Selected |
|--------|----------|
| Replaced by the plan (Recommended) | ✓ |
| Kept as overrides |  |

**User's choice:** Replaced by the plan number (Exafluence Pro -> 50, Platform Enterprise -> 500, ABC/shieldforgetech Free stay 5); partner customers keep their allotments

### What do tenant admins see about their plan?

| Option | Selected |
|--------|----------|
| Plan, limits, usage, trial days (Recommended) |✓ |
| Seats only, as today |  |

**User's choice:** Licence panel shows plan name, seats used of limit (marked if override), allowed networks, days left in a Free trial

### A machine held because the Free trial ended: can the Super Admin approve it anyway?

| Option | Selected |
|--------|----------|
| Yes, like any hold (Recommended) |✓ |
| No |  |

**User's choice:** Yes, like any Pending hold; the trial stays ended

### How far can a seat override go?

| Option | Selected |
|--------|----------|
| Any number (Recommended) | ✓ |
| Only below the plan |  |

**User's choice:** Any number, above or below the plan

### A tenant goes back to Free: new trial?

| Option | Selected |
|--------|----------|
| One trial per tenant (Recommended) | ✓ |
| Fresh trial each time |  |

**User's choice:** One trial per tenant: a tenant that already had its trial or a paid plan returns to Free with the trial ended (running agents carry on, new machines held)

### Seat override when the plan changes?

| Option | Selected |
|--------|----------|
| Override stays (Recommended) | ✓ |
| Plan change clears it |  |

**User's choice:** Override stays until removed

### Does the Platform organization follow plan limits?

| Option | Selected |
|--------|----------|
| Exempt (Recommended) | ✓ |
| Treated as Enterprise |  |

**User's choice:** Exempt: no plan, trial or network limits

### When does a new organization's 14-day trial start?

| Option | Selected |
|--------|----------|
| When it is created/approved (Recommended) | ✓ |
| At its first agent |  |

**User's choice:** When it is created (for sign-ups, when the Super Admin approves the sign-up)

### Which plan does a new organization start on?

| Option | Selected |
|--------|----------|
| Free trial for all (Recommended) | ✓ |
| Sign-ups Free, Add Tenant as chosen |  |

**User's choice:** Free trial for all: sign-ups and Add Tenant both default to Free (Add Tenant form defaults to Enterprise today); creator may pick another plan

### After a Free trial ends, does anything stop besides enrolling new machines?

| Option | Selected |
|--------|----------|
| Nothing else (Recommended) | ✓ |
| Screens drop to a basic set |  |

**User's choice:** Nothing else: running agents and every screen keep working

### Are tenant admins told when their plan or seat limit changes?

| Option | Selected |
|--------|----------|
| Yes, notice + audit (Recommended) |✓ |
| Audit only |  |

**User's choice:** Yes: in-app notice to the tenant's admins + audit ledger entry (who, from, to)

---

## Screens by plan

### How should a plan relate to a tenant's screen switches?

| Option | Selected |
|--------|----------|
| Plan is a ceiling (Recommended) | ✓ |
| Plan switches its screens on |  |
| Plan sets the starting set |  |

**User's choice:** Plan is a ceiling: each plan lists the screens it may have; the Super Admin or partner ticks screens one by one within it (same model as the Phase 87 partner ceiling)

### Moving to a smaller plan: screens the new plan doesn't include?

| Option | Selected |
|--------|----------|
| Stay on (Recommended) | ✓ |
| Turn off at once |  |
| Turn off after 14 days |  |

**User's choice:** Stay on; the smaller plan limits only future ticks (as Phase 87 D-19)

### Where does each plan's screen list come from?

| Option | Selected |
|--------|----------|
| minTier, editable (Recommended) |✓ |
| Super Admin builds each list |  |
| Fixed by minTier in code |  |

**User's choice:** Start from feature_catalog.py minTier (cumulative Free < Pro < Enterprise), editable by the Super Admin on the Plans screen

### For a partner's customer, which screens may be ticked?

| Option | Selected |
|--------|----------|
| Both limits apply (Recommended) |✓ |
| Partner ceiling only |  |

**User's choice:** Only screens inside both the partner's ceiling and the customer's plan

### During the 14-day Free trial, which screens may be ticked?

| Option | Selected |
|--------|----------|
| Free's list only (Recommended) | ✓ |
| Pro's list during the trial |  |

**User's choice:** Free's list only

### Switchable screens with no minTier (estimate ~150 of ~206; planner to count): which plans?

| Option | Selected |
|--------|----------|
| Placed by the planner, then editable (Recommended) |✓ |
| Every plan |  |
| Enterprise only |  |

**User's choice:** Planner places each with the catalogue feature it belongs to (e.g. a Compliance sub-screen follows Compliance); leftovers start on Enterprise; Super Admin can move any on the Plans screen

---

## Network & duplicate rules

### What counts as the same network as an allowed one?

| Option | Selected |
|--------|----------|
| Exact IP, ranges by Super Admin (Recommended) |✓ |
| The IP's /24 block |  |
| The same ISP (ASN) |  |

**User's choice:** Exact public IP; when allowing, the Super Admin may widen an entry to a CIDR range (e.g. an office /29)

### Who approves a machine held for a new network when the tenant belongs to a partner?

| Option | Selected |
|--------|----------|
| Super Admin only (Recommended) | ✓ |
| Super Admin or the partner |  |

**User's choice:** Super Admin only, for direct and partner customers alike

### What does the tenant admin see when a machine is held for a new network?

| Option | Selected |
|--------|----------|
| It, with the reason (Recommended) |✓ |
| Nothing |  |

**User's choice:** The machine as Pending with the reason (e.g. 'new network 203.0.113.7, waiting for platform approval'); cannot approve it

### At go-live, which networks start as allowed?

| Option | Selected |
|--------|----------|
| Every network in use (Recommended) |✓ |
| Only the first agent's |  |

**User's choice:** Every public IP a tenant's enrolled agents report today

### Machine live in org A tries to enroll in org B and is held: what does A see?

| Option | Selected |
|--------|----------|
| Nothing (Recommended) | ✓ |
| A notice, unnamed |  |

**User's choice:** Nothing; only the Super Admin sees both organizations

### What does org B's admin see about the held machine?

| Option | Selected |
|--------|----------|
| Pending, unnamed reason (Recommended) |✓ |
| Nothing |  |

**User's choice:** Pending with an unnamed reason: 'this computer is enrolled in another organization; waiting for platform approval'

### When the Super Admin approves it?

| Option | Selected |
|--------|----------|
| The machine moves to B (Recommended) | ✓ |
| It counts in both |  |
| Super Admin chooses each time |  |

**User's choice:** The machine moves to B: A's agent is retired (Replaced) and its seat freed; one computer, one licence

### When is the machine 'live' in A?

| Option | Selected |
|--------|----------|
| Seen in 24 h, by serial/UUID (Recommended) |✓ |
| Any enrolled agent |  |

**User's choice:** A seat-holding agent with the same BIOS serial or SMBIOS UUID seen in the last 24 h (same as the in-tenant rule); silent/uninstalled agents do not block; MAC alone never counts

### A's copy is silent (>24 h) so B enrolls without a hold: retire A's stale agent?

| Option | Selected |
|--------|----------|
| Yes, retire it (Recommended) |✓ |
| No, leave A alone |  |

**User's choice:** Yes: A's silent agent is marked Replaced and its seat freed; A sees Replaced without B's name

---

## Claude's Discretion

- Field names, collection layout, migration number (034+) and where the plan table lives.
- Which IP the network rule checks: research must use a server-observed address (sourceIp via nginx), not the agent-reported publicIp.
- How feature_bundles.py relates to plans; wording of Pending reasons, notices and reminders; placement of the Plans screen and the partner portal's plan ceiling.

## Deferred Ideas

- Payments, invoices, prices, tenant self-service upgrades (billing out of scope).
- Enforcing billing_service.SUBSCRIPTION_LIMITS data/API/AI figures per plan.
- Alert-only or hard-block variants of the network rule.
- Duplicate detection for MAC-only machines.
- Same-hostname different computers in one tenant (409, pre-existing).
