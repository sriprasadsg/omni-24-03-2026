# Phase 88: Plan-Based Licensing & Network Enrollment Rules - Research

**Researched:** 2026-11-10
**Domain:** Multi-tenant licensing in the existing FastAPI + MongoDB backend (enrollment rules, plan table, screen ceiling, trial, source-IP trust, cross-tenant duplicate hold)
**Confidence:** HIGH (every finding below comes from files read, queries run and probes executed in this session; no external library is introduced)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Before the discussion (user, 2026-11-10)
- **D-01:** The network rule holds NEW machines only: a machine enrolling from a network that is not allowed is held Pending for approval, the same pattern as the C4 hardware allowlist (`license_rules.hold_reason`). Agents already enrolled are never re-checked or cut off, so laptops at home or travelling keep working.
- **D-02:** Cross-tenant duplicate hold: a machine whose hardware belongs to a live seat-holding agent in another tenant is held Pending for platform (Super Admin) approval instead of enrolling a second time. Details in D-31..D-36.

#### Plan limits table
- **D-03:** Seats per plan: Free 5, Pro 50, Enterprise 500, Custom set per tenant by contract.
- **D-04:** No OS or server-class restriction by plan: every plan may enroll every OS class. (The existing C4 OS-class sub-limits stay as they are, set per tenant.)
- **D-05:** Free is a 14-day trial. After it ends, new machines are held Pending (the existing licence-expiry rule) and running agents keep working. Nothing else stops: every screen stays on (see D-21).
- **D-06:** Allowed networks are the same on every plan: one network by default, learned automatically from the public IP the tenant's first agent enrolls from. Any further network is decided only by the Super Admin (allow or refuse). Plans do not change the network count.
- **D-07:** When the Super Admin allows a machine held for a new network, the network is allowed: it joins the tenant's allowed networks, so later machines from it enroll without a hold.
- **D-08:** Today's Free tenants (ABC, shieldforgetech) start their 14-day trial when Phase 88 goes live, not from their creation date. — **Reversibility:** costly — the trial start stored per tenant at go-live is what every later trial check and reminder reads.

#### Plan vs overrides, partners and downgrades
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

#### Screens by plan
- **D-27:** The plan is a screen ceiling: each plan lists the screens it may have, and the Super Admin or partner still ticks screens one by one (spec C6 `enabledFeatures`), but only within the plan. Same model as the Phase 87 partner screen ceiling (D-10 there). The server refuses a screen outside the ceiling.
- **D-28:** Moving to a smaller plan leaves screens already on switched on; the smaller plan only limits what can be ticked from then on (as Phase 87 D-19). During and after a Free trial the trial's ceiling is Free's list.
- **D-29:** Each plan's screen list starts from the `minTier` already in `backend/feature_catalog.py` (cumulative: Free within Pro within Enterprise) and is editable by the Super Admin on the Plans screen. Switchable screens with no `minTier` (the C6 switches outnumber the 59 catalogue features; the planner counts them) go into the plan of the catalogue feature they belong to (e.g. a Compliance sub-screen follows Compliance); anything left over starts on Enterprise.
- **D-30:** For a partner's customer, a screen may be ticked only if it is inside both the partner's ceiling and the customer's plan.

#### Network and duplicate rules
- **D-31:** A network is an exact public IP. When allowing one, the Super Admin may widen the entry to a CIDR range (e.g. an office /29).
- **D-32:** Only the Super Admin allows or refuses a new network, for direct and partner customers alike.
- **D-33:** The tenant admin sees a machine held for a new network as Pending with the reason (e.g. "new network 203.0.113.7, waiting for platform approval") and cannot approve it.
- **D-34:** At go-live every public IP a tenant's enrolled agents report today becomes one of its allowed networks, so no current office is blocked from adding machines.
- **D-35:** Cross-tenant: a machine counts as live in tenant A when a seat-holding agent there with the same BIOS serial or SMBIOS UUID was seen in the last 24 hours (the in-tenant rule of spec C2). A MAC address alone never counts. Silent or uninstalled agents do not block.
- **D-36:** While held, tenant A sees nothing; tenant B's admin sees the machine Pending with an unnamed reason ("this computer is enrolled in another organization; waiting for platform approval"). Only the Super Admin sees both organizations' names.
- **D-37:** When the Super Admin approves a cross-tenant hold, the machine moves to B: A's agent is retired (marked Replaced) and its seat freed. One computer, one licence. — **Reversibility:** costly — a Replaced agent in A is not restored by any existing flow.
- **D-38:** When A's copy is silent (no hold, D-35), B's enrollment also retires A's stale agent (Replaced, seat freed); A sees it as Replaced without B's name.

### Claude's Discretion
- Field names, collection layout, the migration number (034 or later; 033 is the uncommitted machine-identities migration) and where the plan table lives, as long as D-14 (editable, applies at once) and D-18 (go-live numbers) hold.
- Which IP the network rule checks. The agent reports its own `publicIp` (it controls that value); the server also sees the request's source address (`sourceIp`). Research must establish which one nginx passes through reliably and use a server-observed address, not the agent's claim, for the allow decision.
- How `feature_bundles.py` (assigned bundles) relates to plans: the enforced screen switches are `tenant_features` (C6); the planner decides whether bundles are mapped, left alone or retired, without changing what any tenant can use today except as D-27/D-28 say.
- Wording of the Pending reasons, notices and reminders, within D-33/D-36.
- Where the Plans screen sits for the Super Admin, and how the partner portal shows the plan ceiling.

### Deferred Ideas (OUT OF SCOPE)
- Payments, invoices, prices and tenant self-service upgrades (billing, out of scope per PROJECT.md).
- Enforcing the data/API/AI usage limits in `billing_service.SUBSCRIPTION_LIMITS` per plan (they stay warnings).
- Alert-only or hard-block variants of the network rule (the user chose hold-new-machines).
- Duplicate detection for machines identified only by a MAC address (MACs are too easy to copy).
- Two different computers with the same hostname in one tenant still get "already enrolled" (409); hostname uniqueness per tenant predates this phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

No requirement IDs exist in REQUIREMENTS.md for Phase 88 (ROADMAP says "TBD"). The contract is D-01..D-38. Proposed IDs for the planner to register (names are a proposal, not user decisions):

| ID | Description | Decisions | Research Support |
|----|-------------|-----------|------------------|
| LIC-01 | A direct tenant's seat limit comes from its plan (Free 5, Pro 50, Enterprise 500), with a per-tenant Super Admin override that survives plan changes; a partner customer's seats stay the partner's allotment; a plan the tenant already exceeds holds new machines only | D-03, D-09, D-10, D-11, D-12, D-14 (numbers), D-18, D-19 | Section "Seats: plan vs override vs partner pool" |
| LIC-02 | Plan changes (Super Admin, partner within its plan ceiling, payment route) go through one function that records the change, tells the tenant admins and keeps trial and seat rules; new organizations default to Free | D-13, D-24, D-25, D-26 | Section "Every writer of subscriptionTier / license.maxAgents" |
| LIC-03 | Free is a 14-day trial held in one persistent per-tenant record: new machines are held when it ends, running agents and screens carry on, one trial per tenant, extensions audited, 7/1-day reminders (partner told too) | D-05, D-08, D-15, D-16, D-20, D-21, D-22, D-23 | Section "Trial" |
| LIC-04 | Each plan is a screen ceiling, editable by the Super Admin; the server refuses a screen outside it (and, for a partner customer, outside the partner ceiling too); screens already on stay on | D-27, D-28, D-29, D-30 | Section "Screens by plan" |
| LIC-05 | Every tenant has allowed networks (first agent's server-observed IP learned; migration seeds current ones); a NEW machine from another network is held for the Super Admin, who allows (optionally widening to CIDR) or refuses; enrolled agents are never re-checked | D-01, D-06, D-07, D-31, D-32, D-33, D-34 | Section "Source IP" and "Network rule" |
| LIC-06 | A machine whose serial or SMBIOS UUID is live in another tenant is held for the Super Admin without naming either organization to the other; approval retires the other copy; a silent copy is retired by the new enrollment | D-02, D-35, D-36, D-37, D-38 | Section "Cross-tenant duplicate" |
| LIC-07 | A Super Admin Plans screen edits seats, trial days and screens per plan, applying at once to tenants without an override; OS/server-class sub-limits are untouched by plans | D-04, D-14, D-17 | Section "Plan table" |

</phase_requirements>

## Summary

All six research questions have a definite answer from the code and the live host. (1) The trustworthy source address is `request.client.host`: nginx sets `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` on `/api`, and uvicorn 0.53.0 runs with its default `--proxy-headers` and `forwarded_allow_ips` of `127.0.0.1,::1`, so it rewrites `scope["client"]` to the right-most address that is not a trusted proxy, i.e. the address nginx itself observed. A client-supplied `X-Forwarded-For` is ignored. I proved this with a throwaway uvicorn probe and with the live nginx access log (`103.174.161.233` on the register requests equals ABC's agent-reported `publicIp`). The code comments claiming `request.client.host` is the "actual TCP socket IP" are wrong in the narrow sense but the conclusion (cannot be forged) holds only because of this proxy configuration, which is therefore a security dependency to pin and test.

(2) There are four feature systems, not three: `tenant_features.py` (208 switchable keys, enforced), `feature_catalog.py` (59 features with `minTier`, unenforced), `feature_bundles.py` (no tenant uses `assignedBundles`; `require_feature` has no callers) and `feature_flags.FEATURE_TIERS` (tier map that drives `/platform/features` and only a cosmetic sidebar lock). Only 32 of the 59 catalogue permissions are switch keys; name matching adds 18 more; a seed built that way tiers 19 switches Free, 69 Pro, 120 Enterprise, and would place 30 of Exafluence's 56 ticked switches outside its own Pro ceiling (harmless under D-28, but the seed needs human review). Enforcement belongs in one shared function that the partner path (`partner_portal_service._final_screens`) and the Super Admin path (`tenant_endpoints.update_tenant`, which today validates nothing) both call.

(3) Keep `license.maxAgents` as the single effective seat column that `try_claim_seat`, `seats_available`, `license_summary` and the partner pool (`_true_sum`) already read. Add `license.seatOverride` and derive `license.maxAgents` from plan / override / partner allotment in one place inside `licensing.py` (already on the drift-guard allowlist). Plan-table edits must `update_many` direct, non-partner, non-override tenants only. (4) Trial state is its own persistent `tenants.trial` sub-document, not `license.expiresAt`, so it survives plan changes and does not collide with the manual contract expiry. (5) The cross-tenant check needs raw (`_db`) queries and two new sparse indexes on `agents.hardware.serialNumber` / `hardware.smbiosUuid` (a partial `$type` index is NOT used by equality queries; verified). (6) Eleven code paths write `subscriptionTier` or seat numbers; they are enumerated below, including a payment route where a tenant user can post an arbitrary `plan` string.

**Primary recommendation:** Build four small modules (`plan_service.py` for plans/trial/overrides/change_plan, `network_rules.py` for allowed networks and source-IP normalization, `cross_tenant.py` for the duplicate hold and retire, `screen_ceiling.py` extracted from the partner path), extend `license_rules.hold_reason` with `source_ip`, put the new migration at 034, and keep every `license.maxAgents` write inside `licensing.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Source-IP trust (client address) | Reverse proxy (nginx) | API / Backend (uvicorn proxy-headers) | nginx observes the TCP peer; uvicorn must trust only 127.0.0.1/::1 |
| Plan table (seats, trial days, screens) | Database / Storage | API / Backend | Stored data (D-14), read by plan_service, licence panels, partner portal |
| Enrollment rules (trial, network, cross-tenant) | API / Backend (`register_agent` + `license_rules.hold_reason`) | Database | Rules are server-side and must not trust agent claims |
| Seat accounting | Database (atomic conditional update) | API / Backend | `try_claim_seat` `$expr` update is the only safe counter |
| Screen ceiling enforcement | API / Backend (one shared function at every `enabledFeatures` writer) | Browser (picker shows ceiling) | UI hides, server refuses (as Phase 87 D-10) |
| Trial expiry and reminders | API / Backend (hourly `license_seat_tick`) | Database | Expiry evaluated lazily at enrollment; reminders by the existing hourly loop |
| Plans screen, licence panel, partner plan picker | Browser / Client | API / Backend | Display and edit forms only; every refusal is server-side |
| Pending reasons for tenant admins vs Super Admin | API / Backend (projection of what each caller may see) | Browser | D-36 requires the server to withhold the other organization's name |

## Standard Stack

No new external package is needed. Everything is Python standard library plus what is already installed.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `ipaddress` (stdlib) | Python 3.12.3 | Parse/normalize IPs and CIDR, containment test (`ip in network`) | Stdlib, handles IPv4/IPv6/IPv4-mapped; never hand-roll CIDR math |
| uvicorn | 0.53.0 | `ProxyHeadersMiddleware` already derives the real client from X-Forwarded-For | Already running; behaviour verified by probe |
| motor / pymongo | 3.7.1 / 4.18.2 | Atomic conditional updates for seats, trial, networks | Same as `licensing.try_claim_seat` and `partner_pool` |
| fastapi / pydantic | 0.141.1 / (installed) | Routes and request validation | Project standard |
| pytest + pytest-asyncio | 9.1.1 / 1.4.0 | Tests with real MongoDB via `tests/_mongo_test_db.py` | Project standard (`asyncio_mode = auto`) |
| vitest | project `npx vitest run src/__tests__` | Frontend tests for Plans screen, licence panel, partner portal | `workflow.test_command` in `.planning/config.json` |

[VERIFIED: backend/venv `pip list` run this session for uvicorn, starlette, fastapi, motor, pymongo, pytest, pytest-asyncio; `python --version` = 3.12.3]

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Embedded `tenants.allowedNetworks` array | A collection like `agent_allowlist` | The allowlist is a collection because of 10,000-row CSV import; networks are a handful per tenant, are read with the tenant document `hold_reason` already fetches, and `$addToSet` on one document is atomic. Use embedded, cap at 100 entries. |
| Separate `tenants.trial` | Reuse `license.expiresAt` | `expiresAt` is the Super Admin's manual contract date (PATCH licence sets/clears it and resets `expiryRemindersSent`); the trial must persist across plan changes (D-22) and uses 7/1-day reminders. Separate record. |
| Plan table in a `plans` collection | Constants in code | D-14 requires editable stored data. 4 documents, raw handle, seeded by migration 034. |

**Installation:** none.

## Package Legitimacy Audit

No external packages are installed by this phase (stdlib `ipaddress` plus already-installed backend dependencies). The `gsd-tools package-legitimacy` gate was therefore not run and there is nothing to REMOVE or flag.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | - | - | - | - | - | - |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
Agent (Windows/Linux/macOS) --HTTPS--> nginx :443  /api  (X-Forwarded-For = client-sent, + $remote_addr appended)
                                          |
                                          v   (127.0.0.1)
                              uvicorn :5000  ProxyHeadersMiddleware
                              trusts 127.0.0.1,::1 only -> scope["client"] = right-most untrusted entry
                                          |
                                          v
                         POST /api/agents/register  (register_agent)
   resolve install key -> tenant ; hostname ; hardware ; machine_identity.known_machine
        |
        |  new to tenant (not existing_agent)  OR  any seat claim (cross-tenant check only)
        v
   license_rules.hold_reason(db, tenant, hardware, platform, default_group, source_ip)
     1 license_expired (manual expiry, partner pool expiry)            existing
     2 trial_ended   (effective plan Free AND trial.endsAt passed)     NEW  (skipped for platform-admin, D-26)
     3 cross_tenant_duplicate (raw lookup: live seat-holder elsewhere) NEW  (before network, see Pitfall 6)
     4 not_allowlisted (C4 hardware allowlist)                         existing
     5 new_network   (server-observed IP not in tenant.allowedNetworks) NEW  (platform exempt; empty list => learn)
     6 sublimit:os / sublimit:group                                    existing
        |
        |-- reason  --> pending_agents.hold(...)  -> 202 pending ; alerts (tenant admins get the unnamed text)
        |                      |
        |                      v   Super Admin approves (manage:pending_agents)
        |            pending_agents.approve: by reason
        |              new_network      -> add network (opt. widen CIDR, D-31) then claim seat
        |              cross_tenant_dup -> retire A's agent (Replaced + revoke tokens + release A seat) then claim B seat
        |              trial_ended / seat_limit / ... -> claim seat (trial stays ended, D-20)
        |
        |-- no reason --> _take_over_hardware_seat (in-tenant, 24 h) -> licensing.try_claim_seat (atomic $expr on license.maxAgents)
                          silent live-elsewhere copy -> retire A's stale agent (D-38)
                          first agent of tenant -> learn network (atomic conditional $push)

Plan changes (Super Admin PATCH, partner, payment route, sign-up approve, create)
   --> plan_service.change_plan  (one CAS update: subscriptionTier + license.maxAgents/seatOverride + trial) --> audit_ledger.event + in-app notice
Plan table edits (Plans screen) --> plans collection --> licensing.apply_plan_seats (update_many: direct, non-partner, no override)
Screen ticks (update_tenant, create_tenant, partner set_customer_features/create_customer)
   --> screen_ceiling.final_screens(allowed = plan ∩ partner ceiling, current, submitted)
Hourly license_seat_tick --> send_expiry_reminders (existing 30/7/1) + send_trial_reminders (NEW 7/1, + partner)
```

### Recommended Project Structure
```
backend/
├── plan_service.py        # plans table access, plan_of(tenant), effective_seats, change_plan, trial start/extend/consume
├── network_rules.py       # normalize_ip, allowed(), learn_first(), add_network (CIDR widening validation)
├── cross_tenant.py        # live_elsewhere(), retire_agent(), platform-only details
├── screen_ceiling.py      # final_screens(allowed_sets, submitted, current) extracted from partner_portal_service
├── plan_endpoints.py      # Super Admin Plans screen API (mounted via catalogue_mounts_*, like partners)
├── license_rules.py       # hold_reason gains source_ip + 3 rules; send_trial_reminders
├── licensing.py           # keeps EVERY license.maxAgents write (drift-guard allowlist): apply_plan_seats, set_seat_override
├── migrations/034_plan_licensing.py
└── tests/test_plan_*.py, test_network_rule.py, test_cross_tenant_duplicate.py
```

### Pattern 1: Server-observed client address
**What:** Decide on `request.client.host` only; store it as `sourceIp` on admitted agents too (today only Pending agents store it); keep the agent's `publicIp` as information.
**When to use:** the network rule at `register_agent`, learning the first network, the "new network 203.0.113.7" reason text.
**Evidence:**
```
# Source: /etc/nginx/sites-enabled/omni-platform  (location /api)
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```
```
# Source: backend/venv/lib/python3.12/site-packages/uvicorn/config.py:362-363
self.forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1,::1")
```
Probe run this session (uvicorn 0.53.0, peer 127.0.0.1 standing in for nginx): no XFF -> `('127.0.0.1', 48948)`; `X-Forwarded-For: 10.9.9.9, 203.0.113.50` (client spoof, nginx appended the real address) -> `('203.0.113.50', 0)`; a lone spoofed `10.9.9.9` with no nginx append -> `('10.9.9.9', 0)` (cannot happen through nginx because nginx always appends, and cannot happen from outside because the backend ignores XFF from any peer other than 127.0.0.1/::1).

### Pattern 2: One shared ceiling function
**What:** Extract `_final_screens` from `partner_portal_service.py` so partner ticks, Super Admin ticks and tenant creation all call it with a list of allowed sets (partner ceiling, plan ceiling). Keep its rules: dedupe, keep already-on screens beyond the ceiling (D-28), add `START_FEATURES`, refuse `all` and unknown strings (`invalid_screen`), outside-ceiling (`screen_outside_ceiling`), missing parent (`missing_parent`).
**Example (existing, to be extracted):**
```python
# Source: backend/partner_portal_service.py:62-83 (read this session)
allowed = _allowed(partner_doc)
kept = [s for s in dict.fromkeys(current) if s not in allowed]
...
raise PartnerError(422, "screen_outside_ceiling", f"{_label(value)} is not one of the screens you can sell.", screen=value)
```

### Pattern 3: Hold reasons are strings the UI maps
**What:** Add `trial_ended`, `new_network:<ip>` (or `new_network` plus a stored `pendingDetail`), `cross_tenant_duplicate`. Update in lockstep: `pending_agents._REASON_TEXT` / `_REFUSAL_TEXT` (older builds get the raw code as the 403 detail otherwise), `PendingAgentsPanel.tsx` `REASONS` map, `alert_payload`.
**Existing values:**
```python
# Source: backend/license_rules.py:28-30
REASON_EXPIRED = "license_expired"
REASON_NOT_ALLOWLISTED = "not_allowlisted"
REASON_KEY_EXHAUSTED = "key_exhausted"
# Source: backend/pending_agents.py:33-34
REASON_SEAT_LIMIT = "seat_limit"
REASON_DUPLICATE_HARDWARE = "duplicate_hardware_id"
```

### Anti-Patterns to Avoid
- **Deciding the network rule on `data["publicIp"]`:** it is agent-controlled (`register_agent` reads `data.get("publicIp") or reg_meta.get("public_ip")`). Use it only for display and for the one-time D-34 migration seed.
- **Writing `license.maxAgents` outside `licensing.py` / `partner_pool.py`:** `tests/test_partner_license_writers.py` scans every top-level backend module for a `"license.maxAgents"` key or a `"license": {"maxAgents": <non-zero>}` literal and fails for any module not in `SEAT_WRITER_ALLOWLIST = {"licensing.py", "partner_pool.py", "tenant_docs.py", "pending_agents.py", "authentication_endpoints.py"}`.
- **A plan-table edit that touches partner customers:** `partner_pool._true_sum` sums customers' `license.maxAgents` and `partner.allocated` must equal it; a bulk update that changes a partner customer's seats desyncs the pool.
- **Evaluating the cross-tenant rule through the wrapper:** `db.agents` inside a request is auto-scoped to the tenant context set by `set_tenant_id(tenant["id"])`; use `getattr(db, "_db", db)` like `_take_over_hardware_seat` does.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IP / CIDR parsing and containment | Regex or string prefix matching | `ipaddress.ip_address`, `ip_network(strict=False)`, `ip in net`, `.ipv4_mapped` | IPv6, IPv4-mapped (`::ffff:a.b.c.d`), leading zeros and `/0` typos |
| Client IP behind nginx | Reading `X-Forwarded-For` / `X-Real-IP` yourself | `request.client.host` (uvicorn already did the trusted-hop walk) | Re-implementing the walk reintroduces spoofing (`tickets_endpoints.py:196` does exactly that wrong thing for a different purpose) |
| Seat counter | Read-then-write limit check | `licensing.try_claim_seat` (`$expr` `$lt` conditional `$inc`) | Concurrent enrollments |
| Partner pool arithmetic | Editing customers' `license.maxAgents` directly | `partner_pool.change_allotment` | Claim-first/release-later invariant |
| Audit + notices | New collections | `audit_ledger.event(...)`, `partner_store.audit(...)`, `pending_agents.post_to_recipients` / `_post_in_app` | Hash-chained ledger, audience filter (`notification_audience.reader_filter`) |
| Reminders | A new scheduler | Add a step to `app_background_tasks.license_seat_tick` | Each step already has its own failure guard |
| Screen ceiling | A second copy of the validation | Extract `_final_screens` | Parent rule, kept screens and START_FEATURES edge cases |

**Key insight:** this phase is wiring and rules on top of mature primitives. The risk is not missing a library; it is writing seat numbers, tiers or screens from a path that bypasses the one function that keeps the pool, the trial and the audit consistent.

## Question 1: Which source IP is trustworthy

**Answer:** `request.client.host`. [VERIFIED: nginx config read; uvicorn source read; live probe; nginx access log vs DB]

- nginx `/api` forwards `X-Real-IP $remote_addr` and `X-Forwarded-For $proxy_add_x_forwarded_for` (client-supplied value kept, real peer appended). `/socket.io` and `/static` forward neither; `/health`, `/trust/` do. Register is under `/api`.
- uvicorn is started by systemd as `python -m uvicorn app:socket_app --host 0.0.0.0 --port 5000 --log-level info`; the process environment has no `FORWARDED_ALLOW_IPS` (checked `/proc/<pid>/environ` names), so `forwarded_allow_ips` is the default `127.0.0.1,::1`. `ProxyHeadersMiddleware.get_trusted_client_address` walks the header right to left and returns the first host that is not trusted; its own docstring: "In general this is the first 'untrusted' host in the forwarded for list."
- Port 5000 is bound to 0.0.0.0 (`ss -ltnp`), so someone can reach uvicorn directly; their peer is not 127.0.0.1, so their headers are ignored and `client.host` is their real socket address. Either way the value is server-observed.
- Live check: nginx access log has `103.174.161.233 - - [10/Nov/2026:17:08:23 +0000] "POST /api/agents/register HTTP/1.1" 200`, and ABC's agent (EILT0197) stores `publicIp: '103.174.161.233'`. They agree (the agent's own claim happens to be honest here).
- Today admitted agents store only the agent-claimed `publicIp`; `sourceIp` is written only by `pending_agents.identity_fields` for held agents (grep: no other writer). Store `sourceIp` (server-observed) on admitted agents too, at register (and optionally on heartbeat) so later features and the migration have it.

**Risks to pin (tests + start script):**
1. Add `--proxy-headers --forwarded-allow-ips 127.0.0.1` explicitly to the generated unit (`start-all-services.sh` regenerates it: the unit's header says "Generated by start-all-services.sh — re-run the script to regenerate") so a future `FORWARDED_ALLOW_IPS=*` in an env file cannot silently make XFF spoofable. [ASSUMED: that `start-all-services.sh` is the only generator; not read in this session]
2. If nginx is ever placed behind a load balancer / CDN, `$remote_addr` becomes the balancer: add `real_ip_header`/`set_real_ip_from` in nginx first. Today `/etc/nginx/sites-enabled/omni-platform` has none.
3. nginx listens `listen 443 ssl;` only (IPv4 per `ss`: `0.0.0.0:443`, no `[::]:443`), so IPv6 clients are not seen today; normalize anyway (`ipv4_mapped`, lowercase IPv6) so enabling IPv6 later does not duplicate entries.
4. Agents behind a corporate proxy/VPN: the server sees the egress address, which is what the rule wants; the agent's self-reported `publicIp` may differ (split tunnel). Another reason not to use the claim.
5. Several code comments say `request.client.host` is the "actual TCP socket IP" (`tenant_middleware.py`, `rate_limiter.py`, `websocket_manager.py`). That is imprecise, harmless here; do not "fix" it by reading raw headers.

**Test to write:** instantiate `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1,::1")` around a trivial ASGI app and assert the three probe cases above (a unit test cannot go through nginx; the existing `register_agent` tests build `Request({... "client": ("203.0.113.7", 5555)})` directly and stay valid).

## Question 2: The feature systems and the plan screen ceiling

**Counts (run this session against `tenant_features` / `feature_catalog`):**
- `tenant_features.SWITCHABLE` = **208** keys: 74 `view:*`, 119 `screen:*`, 12 `manage:*`, 1 `remediate:*`, 1 `investigate:*`, 1 `export:*`. 53 are `EXPLICIT_SCREENS` (Security/Compliance, never auto-added). 122 have a parent switch. `HIDE_ONLY_SCREENS` = `['agents']`. `START_FEATURES` = `("view:dashboard", "view:profile", "screen:dashboard")` [VERIFIED: tenant_features.py:99; note `view:dashboard` and `view:profile` are NOT in SWITCHABLE].
- `feature_catalog.FEATURE_CATALOG` = 59 features: `Free` 10, `Pro` 32, `Enterprise` 17 [VERIFIED: matches CONTEXT].
- Mapping catalogue to switch keys: 32 catalogue `permission` values are switch keys directly; screens whose needed permission equals a catalogue permission map by `SCREEN_SWITCHES`; together 94 switches are covered directly (103 after adding name matches). Name matching (catalogue key with punctuation stripped equals a `screen:<view>` name) adds 18: `settings->screen:settings, knowledge_base->screen:knowledgeBase, apm->screen:apm, edr->screen:edr, ueba->screen:ueba, dlp->screen:dlp, siem->screen:siem, incident_response->screen:incidentResponse, risk_register->screen:riskRegister, vendor_management->screen:vendorManagement, custom_frameworks->screen:customFrameworks, cissp_oracle->screen:cissporacle, supply_chain->screen:supplyChain, sast, dast, playbooks, ai_remediation->screen:aiRemediation, digital_twin->screen:digitalTwin`. Still no switch: `tickets, users, support_chat, observability, hadr, chaos_engineering, data_lake, goal_system` (8 catalogue features; `hadr` is deliberately platform-only since migration 023).
- Seed result with D-29's rule (own mapped tier, else the parent's tier, never below the parent, else Enterprise): **19 Free, 69 Pro, 120 Enterprise**. 104 switches have no catalogue ancestor and fall to Enterprise by D-29 (includes `manage:settings`, `manage:rbac`, `manage:api_keys`, `screen:security`, `screen:ticketing`, `view:itam`, `view:autonomous_ops` ...).
- Against live tenants (read-only query): Platform 8 on / 0 outside; Exafluence (Pro) 56 switches on, **30 outside** its Pro ceiling under this seed (`view:security`, `investigate:security`, `manage:settings`, `manage:rbac`, `manage:api_keys`, `view:cloud_security` ...); ABC (Free) 8 on, 4 outside (`manage:settings`, `screen:knowledgeBase`, `view:autonomous_ops`, `manage:autonomous_ops`); shieldforgetech (Free) 1 on, 0 outside. Under D-28 these stay on (they become "kept"), so nothing breaks, but the Super Admin could not re-tick them after unticking. **Recommendation:** generate the seed with a one-off script, commit it as reviewed data in migration 034 (not computed at runtime), and review the Enterprise-default 120 before go-live (the user may want `manage:settings` and `manage:rbac` on Free/Pro). Unknown stored entries (e.g. `manage:itam` is in Exafluence's and Platform's lists but not in `SWITCHABLE`) must be tolerated as "kept".

**Per-plan ceiling storage:** `plans.<Plan>.screens` is a list of switch keys, or the single value `"all"` for Custom (D-17) and for the Platform org (exempt). Cumulative (Free within Pro within Enterprise) is applied when seeding and by validation on edit (reject a Free screen missing from Pro? recommended: store each plan's full list; the Plans screen edits them independently; validate keys with `tenant_features.SWITCHABLE` exactly as `partner_platform_service.validate_ceiling` does).

**Enforcement points (all write `enabledFeatures`):**
| Writer | File | Today | Change |
|--------|------|-------|--------|
| Super Admin PATCH tenant | `tenant_endpoints.py:216-217` (`update_data["enabledFeatures"] = data.enabledFeatures`) | No validation at all | Call `screen_ceiling.final_screens` with the plan set (and the partner set only if the user decides the Super Admin is bound by it, see Open Question 4) |
| Super Admin create tenant | `tenant_endpoints.py:107-109` -> `tenant_docs.build_tenant_doc` | Accepts any list, default `START_FEATURES` | Same function; default stays START |
| Partner create customer | `partner_portal_service.create_customer` -> `_final_screens(partner_doc, enabled_features or [], current=[])` | Partner ceiling only | allowed = partner ceiling ∩ plan ceiling (D-30) |
| Partner tick screens | `partner_portal_service.set_customer_features` (compare-and-set on the stored list) | Partner ceiling only | same; the partner view (`_features_view`) also returns the plan ceiling |
| Sign-up approval | `tenant_signup_endpoints.approve_signup` | Leaves START set | nothing to enforce (START features are always allowed) |
| Migrations | e.g. `migrations/017..023` | `$addToSet` | never run after go-live on user tenants; ignore |

`START_FEATURES` must stay allowed on every plan (the partner path already unions them: `return base | set(tenant_features.START_FEATURES)`).

**Trial ceiling (D-28):** "during and after a Free trial the trial's ceiling is Free's list" is just the Free plan's list; no special case, because trial state does not change the plan name. Tenants that moved off Free keep their ticks.

**The other systems, and what to do (change no tenant's access today):**
- `feature_bundles.py` + `bundle_endpoints.py`: no tenant document has `assignedBundles`, `customFeatures` or `blockedFeatures` (queried the 4 tenants). The only consumer, `feature_flags.require_feature`, has no callers (grep). The UI has a "bundle mode" (`useFeatures().assignedBundles`) that never triggers. **Recommend: leave untouched this phase** and note retirement as a follow-up; do not map bundles to plans.
- `feature_flags.FEATURE_TIERS` / `/platform/features`: returns `locked` per `subscriptionTier`; `hooks/useVisibleNav.ts` hides a tier-locked item for a tenant user only when its permission is not switchable (`isTenantUser && tierLock(item) && !isTenantSwitchable(...)`). A plan change therefore already changes the sidebar for non-switchable items. Leave as is; changing `subscriptionTier` for Platform-exempt or test tenants can still move these locks, so cover with the existing sidebar tests (`src/__tests__/SidebarTenantSwitches.test.tsx`).
- `billing_service.SUBSCRIPTION_LIMITS` keys are `"Free"`, `"Pro"`, `"Enterprise"`, `"Custom"` [VERIFIED: billing_service.py:26-45]; `feature_flags.TIER_ORDER` is `{"Free": 0, "Pro": 1, "Enterprise": 2, "Custom": 3}` [VERIFIED: feature_flags.py:30-35]. Use these four exact strings as plan keys; normalize case-insensitively on read (one test fixture stores `"enterprise"`), validate on write.

## Question 3: Plan-driven seats with licensing.py and the partner pool

**What the code does (read this session):**
- `licensing.license_of` reads `license.maxAgents`, falling back to legacy top-level `maxAgents`, then `DEFAULT_MAX_AGENTS = 5`.
- `try_claim_seat` runs `update_one({"id": tenant_id, "$expr": {"$lt": ["$license.seatsUsed", "$license.maxAgents"]}}, {"$inc": {"license.seatsUsed": 1}})`; it reads the limit from the tenant document live, so a changed `license.maxAgents` applies to the next claim with no cache.
- `partner_pool.change_allotment` writes `{"$set": {"license.maxAgents": new_seats, "maxAgents": new_seats}}` with a compare-and-set on the current value; `_true_sum` aggregates `$ifNull: ["$license.maxAgents", {"$ifNull": ["$maxAgents", 0]}]` over `partnerId`.
- `pending_agents.approve(raise_limit_by)` for a direct tenant does `$inc: {"license.maxAgents": raise_limit_by, "maxAgents": raise_limit_by}`.

**Design (recommended):**
1. `license.maxAgents` stays THE effective number. Nothing that reads it changes (enrollment, heartbeat seat claim, installer pre-check `agent_download_endpoints`, licence panels, `partner_store.customer_rows`, reconcile).
2. Add `license.seatOverride: int | absent`. Effective seats for a **direct, non-platform, non-partner** tenant = `seatOverride` if set, else `plans[plan].seats`, except Custom (no plan number: keep whatever is stored). A **partner customer**: unchanged, `license.maxAgents` is the allotment and no override/plan arithmetic applies (D-11). `platform-admin`: exempt (D-26; D-18 still sets 500, a harmless number the engine never recomputes).
3. All writes go through new functions in `licensing.py` (so the drift-guard test keeps passing and its allowlist is untouched): `apply_plan_seats(db, plan, seats)` = `update_many({"subscriptionTier": plan, "type": {"$ne": "partner"}, "partnerId": {"$exists": False}, "id": {"$ne": "platform-admin"}, "license.seatOverride": {"$exists": False}}, {"$set": {"license.maxAgents": seats, "maxAgents": seats}})` (D-14 "applies at once"), and `set_seat_override(db, tenant_id, seats | None)`. If the planner prefers a separate module it must add that file to `SEAT_WRITER_ALLOWLIST` deliberately (a visible test edit).
4. `licensing.update_license(max_agents=...)` (called only from `tenant_endpoints.update_tenant_license`) becomes "set override" for a direct tenant (D-09) and a new `null`/"clear override" path recomputes from the plan. `pending_agents.approve(raise_limit_by)` on a direct tenant must also set `seatOverride` to the raised number, otherwise a later plan-table edit silently shrinks what the Super Admin just granted.
5. Plan table edit (D-14) never touches partner customers (guard above) and never runs for Custom (no plan seats).
6. D-12 comes free: lowering the limit below `seatsUsed` is already allowed (`update_license` docstring: "Lowering below seatsUsed is allowed: running agents keep their seats, new enrollments are refused until seats free up") and the `$expr` `$lt` blocks new claims.
7. `partner_pool.move_customer` to **direct** keeps the seats (Phase 87 D-18) and releases the pool; after that the number is a hand-set one and a later plan edit would overwrite it. Set `seatOverride` = current seats in that move unless equal to the plan number. Direct -> partner: claims the pool for the current number, then the plan stops deciding seats (keep `seatOverride` dormant or clear it; planner decision, tests needed both ways).
8. Migration (D-18): for each direct tenant set `license.maxAgents` to the plan number. Today every tenant is 5 [VERIFIED: query: Platform, Exafluence, ABC, shieldforgetech all `license.maxAgents` 5]. Record the old number first (`license.maxAgentsBeforePlans`) plus one audit entry per tenant, since the overwrite is one-way. A tenant whose stored number is not 5 was hand-set: keep it as `seatOverride` instead of overwriting [ASSUMED; D-18 says "replaced", but today none exists]. Partner customers untouched.
9. Seat floor: the migration only raises (5 -> 50, 500) or keeps (5), so no `seatsUsed > maxAgents` situation arises.

## Question 4: Where trial state lives

**Recommended document on the tenant:**
```
tenants.trial = {
  "startedAt": "<iso>" | null,        # null = never started (paid from creation) or consumed
  "endsAt":    "<iso>",               # when the trial ends; consumed trials get endsAt = a past instant
  "consumed":  true | false,          # set the first time the tenant leaves Free for a paid plan with no trial record
  "extensions": [ {"at","by","days","from","to"} ],   # D-15, mirrored in the audit ledger
  "remindersSent": [7, 1]             # D-16, reset by an extension (as update_license resets expiryRemindersSent)
}
```
**Why not `license.expiresAt`:** [VERIFIED: licensing.py:134-161] a Super Admin's PATCH sets `license.expiresAt` and resets `license.expiryRemindersSent`; `expired()` and `send_expiry_reminders` read only that; `EXPIRY_REMINDER_DAYS = (30, 7, 1)` [VERIFIED: license_rules.py:35]. Reusing it would let a plan change or a contract date edit overwrite the trial (D-22) and cannot express 7/1 days. The trial must also persist when the tenant is on Pro.

**Rules:**
- Trial applies only while the effective plan is Free. `hold_reason`: `if plan == "Free" and trial.endsAt in the past -> "trial_ended"`. A Free tenant with **no** trial record is not held (do not invent an expiry; migration and every writer create the record; fail open for missing data because the control is a soft hold, unlike C6 switches which fail closed).
- `plan_service.change_plan`: moving to a paid plan on a tenant with no trial record writes `{consumed: true, endsAt: now}` so a later return to Free has the trial "already ended" (D-22). Moving to Free with an existing record changes nothing. Never reset a trial.
- D-23: `build_tenant_doc` (direct create and partner create) starts the trial at creation when the plan is Free; sign-up approval (`tenant_signup_endpoints.approve_signup`) starts it at approval. The sign-up path today builds its own tenant dict (`authentication_endpoints.py` ~lines 400-410: `"subscriptionTier": "Free"`, `"maxAgents": 5`, no `license` sub-document) and does not use `build_tenant_doc`.
- D-08: migration 034 sets `startedAt = now`, `endsAt = now + 14 days` on tenants whose plan is Free (ABC, shieldforgetech); paid tenants (Platform, Exafluence) get `consumed: true`. 14 days comes from the plan table (`trialDays`), not a literal.
- Custom has no trial (D-17); platform-admin exempt (D-26).
- D-20: approving a `trial_ended` hold is an ordinary `pending_agents.approve`; nothing extends the trial.
- Reminders: add `license_rules.send_trial_reminders` as a step in `app_background_tasks.license_seat_tick` (its loop is `steps + [licensing.reclaim_inactive_agents, license_rules.send_expiry_reminders]`, each guarded separately). It mirrors `send_expiry_reminders` (atomic claim on `trial.remindersSent` using `$nin`, then `pending_agents.post_to_recipients`) with thresholds `(7, 1)`. `post_to_recipients` posts to the platform feed and the tenant's admins (`audience: tenant_admins`). For a partner customer also post to the partner's own tenant feed without an audience tag (the audience filter `reader_filter` hides `tenant_admins` notices from users lacking `manage:agents`; whether a partner admin has it is unverified, so test that a `partner_admin` actually reads the notice) [ASSUMED].
- Extension (D-15): Super Admin or the customer's partner; add days to `endsAt` (from now if already ended), clear `remindersSent`, `audit_ledger.event("trial.extended", ...)` and `partner_store.audit(...)` for the partner's ledger.

## Question 5: Cross-tenant duplicate (D-31..D-38 in CONTEXT; D-35..D-38 here)

**Lookup.** `seat_identity.hardware_match_filter(tenant_id, hardware)` returns `{"tenantId": tenant_id, "$or": [{"hardware.serialNumber": ...}, {"hardware.smbiosUuid": ...}]}` and `None` when neither is known (a MAC alone never counts; matches D-35) [VERIFIED: seat_identity.py:94-104]. Add `hardware_match_other_tenants_filter(hardware, exclude_tenant_id)` returning the same `$or` with `"tenantId": {"$ne": exclude_tenant_id}` and the seat-holding status filter `{"status": {"$nin": sorted(licensing.NON_SEAT_STATUSES)}}`, then apply `_seen_within(owner, _HARDWARE_TAKEOVER_AFTER)` (24 h) in Python exactly as the in-tenant code does [VERIFIED: agent_registry_endpoints.py:71 `_HARDWARE_TAKEOVER_AFTER = timedelta(hours=24)`; `NON_SEAT_STATUSES = frozenset({"Pending", "Rejected", "Inactive", "Decommissioned", "Replaced", "Uninstalled"})` licensing.py:25]. Run on the raw collection (`getattr(db, "_db", db)`): the wrapper `TenantIsolatedCollection` injects the context tenant and `_HIDDEN_FROM_LISTS` removes Pending/Rejected from list reads.

**Indexes (new, in migration 034).** `agents` has no index on hardware fields today (live indexes: `_id_`, `hostname_1`, `tenantId_1`, `id_1`, `tenantId_1_status_1`, `idx_agents_tenant_lastseen`, `idx_agents_tenant_hostname_unique`). Probe on mongod 8.0.34 in a throwaway database: a **partial** index with `partialFilterExpression {"hardware.serialNumber": {"$type": "string"}}` was NOT used by an equality query (`COLLSCAN`); **sparse** single-field indexes are used (`FETCH` over `IXSCAN`), and an `$or` over both resolves to `FETCH` / `OR` / `IXSCAN`. Create `create_index([("hardware.serialNumber", 1)], sparse=True)` and the same for `hardware.smbiosUuid`, and keep one query per field or the `$or`. (`machine_identities` is unique per `(tenantId, hardwareKey)`, which serves the in-tenant case only.)

**Hold behavior.**
- When: new machine in the tenant (`not existing_agent`) AND any path that claims a seat for a hardware-identified machine (known-machine take-over, a returning Inactive/Uninstalled agent at register), because a take-over record skips `hold_reason` (`hold_reason` is only called `if not existing_agent`). Order it BEFORE the network rule: approving a hold for another reason only claims a seat (`pending_agents.approve`), so a machine that is both a duplicate and on a new network would bypass the duplicate rule if the network reason won. Also re-check at approval time for non-duplicate reasons and convert instead of admitting (Pitfall 6).
- Reason `cross_tenant_duplicate`; store the other organization's agent id, tenant id and name only in a platform-only field (`crossTenant: {agentId, tenantId, tenantName}`) and exclude it from `pending_agents.list_not_admitted` for non-platform callers (today its projection only drops `agentSecretHash` and `uninstallProtection`). Tenant A: write nothing at hold time (no notice, no flag).
- B's admin text (D-36): "this computer is enrolled in another organization; waiting for platform approval" for `reason_text`, `_REFUSAL_TEXT` (older builds' 403 detail), the PendingAgentsPanel `REASONS` map, and `alert_payload` for the tenant-facing notice. `notify_pending` calls `post_to_recipients`, which sends the SAME title/message/metadata to the platform feed and the tenant's admins: needs a variant that sends the named version to the platform feed and the unnamed one to the tenant, otherwise A's name leaks to B.
- `pending_agents.reject` already refuses to denylist a duplicate: `agent.get("pendingReason") != REASON_DUPLICATE_HARDWARE`. Add the new reason to that condition (a denylist entry for B would otherwise be keyed on a machine that is live in A, and the key `seatKey` is tenant-scoped so it would block B forever for a machine that may later be legitimately B's).

**Approval moves the machine (D-37).** In `pending_agents.approve` for `cross_tenant_duplicate`: re-verify A's agent is still seat-holding (it may have gone silent or been deleted meanwhile), then (a) `update_one({"id": A_agent, "status": {"$nin": NON_SEAT}}, {"$set": {"status": "Replaced", "replacedAt": now, "replacedReason": "moved"}})` and only if it modified, (b) `licensing.release_seats(db, A_tenant)`, (c) `authentication_service.revoke_agent_tokens(db, A_agent, "machine moved to another organization")` [VERIFIED: signature `revoke_agent_tokens(db, agent_id: str, reason: str)` authentication_service.py:230], (d) forget the admission cache `pending_agents.forget_status`, (e) then the normal B claim (`try_claim_seat`), (f) audit on the platform ledger with both names and, separately, a B-ledger and an A-ledger entry that name neither. Do NOT set `replacedBy` to B's agent id on A's record (the in-tenant flow does; here it would be a cross-tenant reference visible to A's users); keep the link in the platform-only audit entry.
- A's `machine_identities` row (tenantId A, hardwareKey) can stay: if the machine ever returns to A, `known_machine` finds the Replaced record, `is_live` is false and the duplicate check runs again.
- A's asset record stays with its history; B's enrollment resolves its own asset via `asset_identity.resolve_asset_id`, which already avoids a cross-tenant `asset-{hostname}` id clash (`_belongs_elsewhere` returns True when `asset.get("tenantId") != tenant_id`).
- `machine_identity.remember` for B runs at the end of a successful register (agent_registry_endpoints.py:339), also after approval-time admission? Approval does not go through that line (it only flips status), so after approve the machine's id is the Pending record's id, and `remember` is called on its next successful `register`/never. Check `machine_identity` row for B is written on approval, or the next enrollment under another name gets a random id again (add `machine_identity.remember` to the approve path for hardware keys).

**Silent copy (D-38).** At admission (no hold), if a seat-holding agent with the same serial/UUID exists in another tenant and was NOT seen within 24 h, retire it as above (atomic conditional update; release the seat; revoke tokens; platform audit with both names, A's ledger "Replaced" without B's name) and notify the platform feed. Security note in Pitfall 7.

**Race.** The check is read-then-write across two tenants and cannot be made atomic without a platform-wide unique claim collection; two tenants enrolling the same new machine in the same second can both pass. Accept (it is a soft control, same as the C4 sub-limit counts which the module docstring already declares non-atomic), document it, and let the hourly job report any pair of live seat-holders sharing a serial/UUID (cheap aggregate on the new indexes) as a platform alert.

## Question 6: Every writer of `subscriptionTier` and `license.maxAgents`

**`subscriptionTier` (production code, tests and seeds excluded):**
| # | Location | What it does | Phase 88 action |
|---|----------|--------------|-----------------|
| 1 | `tenant_docs.build_tenant_doc` (`subscription_tier: str = "Free"`) | Shared builder for direct create and partner create | Becomes the one place new tenants get plan, seats and trial; partner customers default to Free (they get a trial too, D-11) |
| 2 | `tenant_endpoints.create_tenant` (`subscription_tier=data.subscriptionTier`; model default `"Free"`) | Super Admin Add Tenant; `TenantCreate.maxAgents` defaults to `licensing.DEFAULT_MAX_AGENTS` (5), so "unspecified" is indistinguishable from "5" | Make `maxAgents` Optional: None = plan seats, an explicit number = override. UI `components/AddNewTenantModal.tsx:12` defaults to `'Enterprise'`; change to Free (D-24) |
| 3 | `tenant_endpoints.update_tenant` (`update_data["subscriptionTier"] = data.subscriptionTier`) | Super Admin PATCH; free string, no validation, no audit of the tier change specifically (a generic "Tenant Updated" notice lists changed keys) | Route through `plan_service.change_plan`; validate against the 4 plans |
| 4 | `authentication_endpoints.py` sign-up (~line 406 tenant doc, ~line 430 user doc: both `"subscriptionTier": "Free"`, `"maxAgents": 5`) | Own dict; tenant has no `license` object and no trial; the user document also carries `subscriptionTier` and `maxAgents` copies | Use the plan engine; trial starts at approval (D-23) |
| 5 | `payment_billing_endpoints.create_subscription` (`$set subscriptionTier = subscription.plan`) | Any user with `manage:settings` of a tenant (`SUBSCRIPTION_GUARD`); `SubscriptionCreate.plan` is an unvalidated `str` | Validate the plan; route through `change_plan`; see Pitfall 8 (tenant self-upgrade now buys seats and screens) |
| 6 | `payment_billing_endpoints` cancel (`$set subscriptionTier = "Free"`) | Cancellation | `change_plan(..., "Free")`: trial already ended (D-22); seat/override rules; running agents kept (D-12) |
| 7 | `app_startup.py` ~line 319 | Creates the platform tenant as Enterprise, `enabledFeatures: []` | Leave; platform exempt (D-26) |
| 8 | `seed_demo_data.py`, `seed_vulns_for_super.py`, `unlock_enterprise_features.py` | Dev/demo scripts | Leave; not production paths (grep confirms no import from the app) [ASSUMED] |
| 9 | `partner_platform_service.appoint` | Partner org has no `subscriptionTier` | n/a; add `partner.planCeiling` here and in `update_partner` (mirrors `screenCeiling`) |

**`license.maxAgents` / seats:**
| # | Location | Phase 88 action |
|---|----------|-----------------|
| 1 | `licensing.update_license` (only caller `tenant_endpoints.update_tenant_license`, PATCH `/{tenant_id}/license`, platform `manage:tenant_license`) | Direct tenants: sets/clears `seatOverride`; partner customers keep going through `partner_pool.change_allotment` |
| 2 | `licensing.ensure_license` | Materializes `license` from legacy fields; leave |
| 3 | `partner_pool.change_allotment` / `move_customer` | Unchanged; `move_customer` to direct sets `seatOverride` (see Q3.7) |
| 4 | `pending_agents.approve(raise_limit_by)` direct branch (`$inc`) | Also write `seatOverride` |
| 5 | `tenant_docs.build_tenant_doc` | plan seats unless override |
| 6 | `authentication_endpoints` sign-up | plan engine |
| 7 | `migrations/011`, `034` | 034 does the D-18 rewrite |

`tests/test_partner_license_writers.py` pins `PRE_CHANGE_KEYS` (the exact key set of the tenant document `create_tenant` stores: `{"id", "name", "subscriptionTier", "registrationKey", "enabledFeatures", "agentCapabilities", "notificationPreferences", "emailConfig", "maxAgents", "license", "createdAt", "updatedAt"}`) and the writer allowlist; adding `trial` to the document is a deliberate edit of that test (add `trial` and, if stored at creation, `allowedNetworks`).

**Plan change function contract (`plan_service.change_plan(db, tenant_id, new_plan, actor, via)`):**
one compare-and-set `update_one` filtered on the old `subscriptionTier` setting `subscriptionTier`, the derived `license.maxAgents`/`maxAgents` (unless override, partner customer or Custom), the trial record, `updatedAt`; refuses an unknown plan, `platform-admin`, and (for a partner caller) a plan outside `partner.planCeiling` and a customer that is not its own; then `audit_ledger.event("plan.changed", tenant_id, actor=..., from=..., to=..., via=...)` (+ `partner_store.audit` for partner actors), then an in-app notice to the tenant's admins (`post_to_recipients`-style, audience `tenant_admins`). A seat change from an override add/remove produces its own `seats.changed` entry (D-25 covers "plan or seat limit").

## Network rule design (D-01, D-06, D-07, D-31..D-34)

- **Storage:** `tenants.allowedNetworks: [{cidr, source: "learned"|"approved"|"migrated", addedAt, addedBy, hostnameAtLearn}]`, normalized via `ipaddress.ip_network(value, strict=False)`; a single IP is stored as `/32` (IPv6 `/128`) per D-31 ("a network is an exact public IP"). Cap 100.
- **Check:** `hold_reason` gets the observed `source_ip` (from `request.client.host`), parses it, and holds with `new_network` if no entry contains it. Unparsable/missing observed address: hold with the same reason (never admit on a failed parse). Skipped for `platform-admin`.
- **Learn first network (D-06):** when the tenant has no allowed network and this machine passed every other rule, add the observed IP atomically: `update_one({"id": tenant_id, "allowedNetworks.0": {"$exists": False}}, {"$push": {"allowedNetworks": entry}})`; if `modified_count == 0` another enrollment won, so re-evaluate against the fresh list (hold if not contained). Learn only when the machine is admitted (after the seat claim), not when it is held for another reason.
- **Approve (D-07, D-31, D-32):** `ApproveBody` gains `widenTo: Optional[str]`; validate that it contains the observed IP and refuse a prefix shorter than a floor the planner sets (recommend IPv4 `/24`, IPv6 `/48`; a `/8` typo would allow a continent) and refuse non-global ranges unless the observed IP itself is private (LAN-attached test agents). Only `manage:pending_agents` platform deciders reach this (already enforced by `_require_decider`; D-33 holds because tenant users only get the read-only list). Adding the network is idempotent (`$addToSet` by cidr); other Pending machines of the same network stay Pending until approved (acceptable; optional: offer "approve all from this network").
- **Never cut off:** `hold_reason` is only called when `not existing_agent` at register; heartbeat only claims a seat. Both leave enrolled agents alone. Pre-existing gap worth knowing: the heartbeat's "new agent" path (token valid, record missing) creates an agent without `hold_reason`; this is the same bypass C4 rules have today and matches "already enrolled machines are never cut off".
- **D-34 migration:** collect `publicIp` of agents whose status is not `Pending`/`Rejected` per tenant (the only data available: admitted agents have no stored `sourceIp`); validate with `ipaddress`, skip invalid/private; store `source: "migrated"`. Live today: only ABC has one (`103.174.161.233`, EILT0197); Platform's agent (`10.0.0.4`, no `publicIp`) is exempt; shieldforgetech has no agents, so its first agent learns.
- **IP version/NAT pitfalls:** carrier-grade NAT or a dynamic ISP address changes the observed IP; the reaction is a Pending hold for the Super Admin (by design, D-01). IPv4-mapped IPv6 must be unwrapped before comparing.

## Plan table (LIC-07, D-14)

`plans` collection, one document per plan: `{key: "Free"|"Pro"|"Enterprise"|"Custom", seats: int|null, trialDays: int|null, screens: [..]|"all", updatedAt, updatedBy}`; seeded by migration 034 from D-03 (Free 5 / Pro 50 / Enterprise 500 / Custom null; Free `trialDays` 14; others null) and the reviewed screen seed. Read through the raw handle (`db._db`): the tenant wrapper would inject `tenantId` into a new collection (only `TENANT_ISOLATION_EXEMPT_COLLECTIONS` entries such as `tenants` are exempt). Enrollment never reads this table (it reads the tenant's own `license.maxAgents`, `trial` and `allowedNetworks`), so no cache is needed and a Plans edit is visible to the next enrollment. Editing seats calls `licensing.apply_plan_seats`; editing screens changes only future ticks (D-28); editing `trialDays` applies to trials started afterwards (existing `endsAt` values are stored data; say so on the screen).

**Route and screen registration pattern (follow Phase 87):** mount the Plans API through `catalogue_mounts_*` with `catalogue_guard(...)` and add the screen to `shared/catalogue-access.json`; `test_catalogue_route_parity`, `test_catalogue_manifest` and `_route_walk.py` fail for an unmounted route. The Partners screen (`catalogue_mounts_partners.py`: `PARTNERS_GUARD = catalogue_guard("partners", read=("manage:partners",), write=("manage:partners",))`) is the model; a Super Admin-only permission is the analogue.

## Frontend touch points (from component reads; sizes: TenantLicensePanel 164 lines, PendingAgentsPanel 275, PartnerPortal 418, ManageTenantModal 427)
- `components/TenantLicensePanel.tsx` + `GET /api/tenants/{id}/license` (`licensing.license_summary`): add plan, `seatOverride` flag, `allowedNetworks`, trial days left (D-19; tenant admins read-only).
- `components/PendingAgentsPanel.tsx`: `REASONS` map and `reasonText`; approve dialog gets the "widen to CIDR" input for `new_network` and a named two-organization view for the platform user only.
- `components/AddNewTenantModal.tsx:12` default `'Enterprise'` -> `'Free'`; `components/ManageTenantModal.tsx` tier select via the plan-change route.
- Partner portal (`PartnerPortal.tsx`, `PartnerCustomerModals.tsx`, `PartnerScreenPicker.tsx`): plan per customer row (add `plan`, `trialEndsAt` to `partner_store.CUSTOMER_FIELDS`; its docstring says that tuple is "the whole of what a partner may see about a customer (D-01)" and customer rows are "rebuilt key by key from it", and a test pins it), plan change within `planCeiling`, trial extension, plan ceiling shown next to the screen ceiling.
- New Super Admin Plans screen.

## Common Pitfalls

### Pitfall 1: A plan edit or migration touches partner customers
**What goes wrong:** `partner.allocated` no longer equals the sum of customers' `license.maxAgents`; the pool over- or under-sells.
**Why:** bulk `update_many` on `subscriptionTier` without excluding `partnerId`.
**How to avoid:** every plan-seat write filters `partnerId: {"$exists": False}`, `type != "partner"`, `id != "platform-admin"`, no `seatOverride`; test with a partner customer on the same plan.
**Warning signs:** `partner_pool.reconcile_pools` logs "seat counter drift repaired".

### Pitfall 2: The override is lost
**What goes wrong:** Super Admin approves-and-raises a direct tenant (or sets a number in the licence panel), then a Plans edit resets it.
**How to avoid:** every direct manual seat write sets `seatOverride`; the "remove override" action is the only way back to the plan number (D-09/D-10).

### Pitfall 3: Trusting a header
**What goes wrong:** someone "improves" the IP read to `X-Forwarded-For[0]` (as `tickets_endpoints.py:196` does for ticket display) and any client can pick its network.
**How to avoid:** the proxy-headers unit test (Q1), explicit `--forwarded-allow-ips 127.0.0.1` in the unit, and a grep-style test that `license_rules`/`network_rules` never read `X-Forwarded-For`.

### Pitfall 4: Old agent builds see raw reason codes
**What goes wrong:** builds without `supportsPending` get a 403 whose detail is `_REFUSAL_TEXT.get(reason, reason)`; a new reason without text shows `new_network`.
**How to avoid:** add the three reasons to `_REFUSAL_TEXT`, `_REASON_TEXT`, the UI map, and the `alert_payload` message.

### Pitfall 5: Heartbeat resurrects a Replaced agent
**What goes wrong:** `agent_heartbeat_endpoints.report_heartbeat` treats any status in `NON_SEAT_STATUSES` as "returning" (`needs_seat = not existing_agent or existing_agent.get("status") in licensing.NON_SEAT_STATUSES`), claims a seat in A and sets it Online. A's retired agent (or a clone holding its credentials) would take a second licence for the same computer, defeating D-37/D-38.
**How to avoid:** revoke A's agent tokens at retirement (`revoke_agent_tokens`; `verify_agent_key` checks `agent_token_revoked`) and make the heartbeat refuse `Replaced` (403 `agent_replaced`). Without this "one computer, one licence" is not true. [VERIFIED: agent_heartbeat_endpoints.py:88-96, agent_auth.py:88]

### Pitfall 6: Approving one reason bypasses another
**What goes wrong:** `pending_agents.approve` only claims a seat. A machine held for `new_network` that is also live in another tenant is admitted twice.
**How to avoid:** evaluate cross-tenant first, and at approval re-run the cross-tenant check for every reason except the duplicate itself; if it now fails, convert the hold to `cross_tenant_duplicate` and return 409 `reason_changed`.

### Pitfall 7: Hardware identifiers are agent-controlled
**What goes wrong:** a tenant that knows another organization's machine serial can enroll a fake agent presenting it; D-38 then retires the other organization's silent agent and frees its seat (e.g. a laptop switched off for a weekend). The in-tenant code already notes "a spoofed serial cannot take a live agent's seat".
**How to avoid / surface:** D-38 is locked, so keep it but add safeguards: platform alert on every D-38 retirement (names both orgs), audit on both ledgers, and a Super Admin "restore agent" operation to be considered by the planner (the CONTEXT notes none exists). Flag to the user as an Assumption (A4).

### Pitfall 8: Plan strings from tenant users
**What goes wrong:** `POST /api/payments/subscribe` lets any user holding `manage:settings` set `subscriptionTier` to any string. Before this phase that only moved cosmetic locks; now it moves seats and ceilings. A tenant admin could post `Enterprise` or `Custom`.
**How to avoid:** validate against the plan table; the payment route may move only among Free/Pro/Enterprise (never Custom); verify `price_id` corresponds to the plan or document that billing stays out of scope and the route is trusted [ASSUMED: gateway verification of price vs plan was not read]. Ask the user whether a tenant admin's own subscribe call should change the plan at all before a payment is confirmed (Open Question 3).

### Pitfall 9: Tenant-leak through shared notification/alert paths
**What goes wrong:** `post_to_recipients` sends identical text to platform and tenant; `list_not_admitted` returns every stored field; audit entries are written with `tenant_id=agent["tenantId"]`.
**How to avoid:** unnamed variants for tenant-facing output, platform-only fields projected out for non-platform callers, tests that assert A's feed/list/ledger and B's feed/list/ledger contain neither name.

### Pitfall 10: Migration timing and re-runs
**What goes wrong:** the trial `startedAt` and the D-18 overwrite are taken at the first backend restart after the migration file exists (the runner applies pending migrations at startup and records them in `_migrations`); the old seat numbers vanish if not recorded; a second `up()` in tests must be a no-op.
**How to avoid:** make 034 idempotent (`$exists` guards, `$setOnInsert`), record previous values, and plan the restart as the go-live moment (the user restarts the backend). Note `Exafluence`'s manual `license.expiresAt` is `2026-10-30T23:59:59+00:00`, already past (queried), so its new machines are held `license_expired` today regardless of this phase; raising it to 50 seats does not change that. Tell the user.

### Pitfall 11: Heartbeat/known-machine paths skip `hold_reason`
`known_machine` returns an existing record for a reinstalled machine, so `hold_reason` (guarded by `if not existing_agent`) is skipped: trial/network rules do not apply to a reinstall of a known machine (acceptable: it is not new, D-01), but the cross-tenant rule must run for any seat claim (see Q5).

## Code Examples

### Right-most untrusted address (what uvicorn does; the app only reads `request.client.host`)
```python
# Source: backend/venv/lib/python3.12/site-packages/uvicorn/middleware/proxy_headers.py (read this session)
for host_port in reversed(x_forwarded_for_hosts):
    host, port = _parse_host_port(host_port)
    if host not in self:
        return host, port
```

### Atomic first-network learn (new; pattern from licensing.try_claim_seat)
```python
# network_rules.py (proposed). Values: tenant ids come from the tenants collection, entry built here.
res = await raw.tenants.update_one(
    {"id": tenant_id, "allowedNetworks.0": {"$exists": False}},
    {"$push": {"allowedNetworks": entry}},
)
learned = res.modified_count == 1   # False: someone else learned first, re-check containment
```

### Containment (stdlib)
```python
import ipaddress
ip = ipaddress.ip_address(observed)
if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
    ip = ip.ipv4_mapped          # unwrap ::ffff:a.b.c.d before comparing
allowed = any(ip in ipaddress.ip_network(e["cidr"], strict=False) for e in tenant.get("allowedNetworks") or [])
```

### Seat claim (existing, unchanged; it reads the limit live)
```python
# Source: backend/licensing.py:91-98 (read this session)
res = await _raw(db).tenants.update_one(
    {"id": tenant_id, "$expr": {"$lt": ["$license.seatsUsed", "$license.maxAgents"]}},
    {"$inc": {"license.seatsUsed": 1}},
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Seats hand-set per tenant | Plan table + override | This phase | `license.maxAgents` becomes derived data; every seat writer routes through `licensing.py` |
| `minTier` unenforced; tier map cosmetic | Plan screen ceiling over C6 switches | This phase | Server refuses out-of-plan ticks |
| Dedupe only within a tenant (24 h rule) | Cross-tenant live duplicate hold | This phase | Needs raw lookups and hardware indexes |

**Deprecated/outdated:** `feature_bundles` / `require_feature` (no tenant uses bundles; leave, retire later). Top-level `maxAgents` (legacy reader kept "one release" per `licensing.update_license`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `start-all-services.sh` is the only generator of the systemd unit and nginx site, so pinning `--forwarded-allow-ips` and any nginx change belongs there | Q1 | Change lost on next regeneration (low) |
| A2 | A hand-set number other than 5 (none exists today) should survive the D-18 migration as an override rather than be overwritten | Q3.8 | Contradicts D-18 wording for a case that does not occur today (low) |
| A3 | A `partner_admin` can read an audience-free notice in the partner's own tenant feed; `tenant_admins`-tagged notices may be hidden from partner users | Q4 reminders | Partner never sees the trial reminder (medium); needs a test |
| A4 | D-38's retirement of a silent copy accepts the spoofed-serial risk (Pitfall 7) | Q5 | A hostile tenant can knock a silent agent off another tenant; the user may want a safeguard or restore operation |
| A5 | The payment gateway's `create_subscription` does not itself bind `price_id` to the `plan` string | Pitfall 8 | If it does, the self-upgrade concern is smaller |
| A6 | Seed/demo scripts (`seed_demo_data.py`, `seed_vulns_for_super.py`, `unlock_enterprise_features.py`) are not imported by the running app | Q6 | An unknown writer of `subscriptionTier` exists (low) |
| A7 | IPv4 `/24` and IPv6 `/48` as the narrowest-allowed CIDR widening floor | Network rule | Too strict for a real office /23, or too loose; the planner/user decides the floor |
| A8 | Cross-tenant check also runs for `platform-admin` as the enrolling tenant, and platform agents count as "another tenant" for A | Q5 | A platform-owned test machine enrolled in a customer is held; benign but surprising |

## Open Questions (RESOLVED)

Q1-Q6 were answered by the user on 2026-11-10 (88-CONTEXT.md D-39..D-46). Q7 got no user decision; the planner declined it (see Q7).

1. **The seed for the Enterprise-default screens (120 of 208).** RESOLVED by D-46: migration 034 ships the generated seed (19 Free, 69 Pro, 120 Enterprise of 208), with no review checkpoint before the migration; the Super Admin edits each plan's list on the Plans screen afterwards, and live tenants keep their screens (D-28).
   - Known: D-29 sends every switch with no catalogue ancestor to Enterprise; that includes `manage:settings`, `manage:rbac`, `manage:api_keys`, `screen:security`, `screen:ticketing`, `view:itam`, `view:autonomous_ops`.
   - Unclear: whether the user wants those on Free/Pro by default.
   - Recommendation: generate the seed, ship it as reviewed data in migration 034, and let the Plans screen edit it; no live tenant loses a screen under D-28.
2. **Do the Platform number and D-26 agree?** D-18 sets Platform to 500 seats; D-26 says Platform has no plan limits. Recommendation: write 500, but the engine ignores `platform-admin` thereafter. RESOLVED by D-41: the Platform organization has no seat limit at all and D-18's 500 does not apply to it; migration 034 leaves its stored number untouched (88-11).
3. **Should a tenant admin's own `/api/payments/subscribe` change the plan immediately?** Today it does (arbitrary string). Recommendation: validate the plan, allow only Free/Pro/Enterprise, and ask the user whether it should require Super Admin confirmation. RESOLVED by D-39: the route only records the subscription and validates the plan name; it no longer changes the plan, which only the Super Admin (or the partner for its own customers) applies.
4. **Is the Super Admin bound by a partner's screen ceiling when ticking a partner customer's screens (D-30)?** Today `update_tenant` is not. Recommendation: bind the Super Admin by the plan only; the partner ceiling limits the partner. RESOLVED by D-40: as recommended, only the customer's plan limits the Super Admin; the partner's ceiling limits only what the partner ticks.
5. **Direct <-> partner moves and `seatOverride`.** Recommendation in Q3.7; needs a decision and tests both ways. RESOLVED by D-44: partner to direct keeps the seats as an override (unless equal to the plan's number); direct to partner clears the override and the partner's allotment decides.
6. **Reason code for the trial hold:** D-05 says "the existing licence-expiry rule". Recommendation: separate `trial_ended` code with identical behavior, so the UI and platform alerts can say "trial ended". RESOLVED by D-45: a separate `trial_ended` reason ("trial ended") with the same behavior as an expired licence.
7. **Approve-all-from-this-network:** optional convenience for several Pending machines from one new office. RESOLVED as declined (deferred) by the planner: the user made no decision on it (D-39..D-46 answer Q1-Q6 only), so no "approve every machine from this network" action is planned. Built instead (88-05): the bulk approve endpoint is unchanged and, through the same approve path, allows each approved `new_network` machine's exact observed address (/32, or /128 for IPv6); the single approve accepts a `widenTo` range within the D-42 limit (IPv4 /24, IPv6 /48). Either way, later machines from the allowed network enroll without a hold (D-07); machines already held from it are approved one by one or by selecting them for bulk approve. The user can ask for the convenience action in a later phase.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv (`backend/venv`) | all backend work, tests | yes | 3.12.3 | - |
| MongoDB (`mongod`) | real-Mongo tests, migration | yes (127.0.0.1:27017, no auth for local reads) | 8.0.34 | tests skip if unreachable (`mongo_db` fixture) |
| nginx | source-IP behaviour, deploy | yes | 1.24.0 | - |
| Node | vitest frontend tests | yes | v20.20.2 | - |
| uvicorn | proxy-headers behavior | yes | 0.53.0 | - |
| Backend restart / UI publish | go-live (migration 034) | user's action (per project memory: restarts and UI publishes are the user's) | - | give the user the command |

**Missing dependencies with no fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`); frontend vitest |
| Config file | `/home/azureuser/enterprise-omni-agent-ai-platform/pytest.ini` (`testpaths = . backend`); `workflow.test_command` = `npx vitest run src/__tests__` |
| Quick run command | `cd /home/azureuser/enterprise-omni-agent-ai-platform/backend && venv/bin/python -m pytest tests/test_enrollment_controls.py tests/test_pending_agents.py tests/test_licensing.py tests/test_machine_identity.py tests/test_asset_identity.py -q -p no:cacheprovider` (57 passed in 11.3 s this session) |
| Full suite command | `cd /home/azureuser/enterprise-omni-agent-ai-platform/backend && venv/bin/python -m pytest tests -q -p no:cacheprovider` plus `cd .. && npx vitest run src/__tests__` |
| Real-Mongo fixture | `tests/_mongo_test_db.py::mongo_db` creates a throwaway `omni_test_<12 hex>` database, creates unique indexes on `agents` `(tenantId, hostname)` and `id`, drops it afterwards; skips when mongod is unreachable. Register harness: `tests/test_enrollment_controls.py` `_register(db, hostname, key, hardware, **body)` builds `Request({... "client": ("203.0.113.7", 5555)})` and patches `reg.get_database` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LIC-01 | plan seats at create; override wins and survives plan change; partner customer keeps allotment; exceeding plan holds new machines only; plan edit hits only direct non-override tenants | real-Mongo unit | `pytest tests/test_plan_seats.py -q` | no, Wave 0 |
| LIC-01 | concurrency: plan edit during enrollments never exceeds the new limit (extend `tests/test_license_seat_toctou.py` pattern) | real-Mongo | `pytest tests/test_license_seat_toctou.py tests/test_plan_seats.py -q` | partly |
| LIC-01 | drift guard still passes with new seat writer location | AST scan | `pytest tests/test_partner_license_writers.py -q` | yes (edit `PRE_CHANGE_KEYS` for `trial`) |
| LIC-02 | every `subscriptionTier` writer goes through `change_plan`; audit entry + tenant notice; partner outside `planCeiling` refused; payment route validates plan; cancel returns to Free with trial ended | real-Mongo + route call | `pytest tests/test_plan_change.py -q` | no, Wave 0 |
| LIC-02 | repo-wide scan: no module outside the allowed set writes `subscriptionTier` (like the seat writer scan) | AST scan | `pytest tests/test_plan_writers_scan.py -q` | no, Wave 0 |
| LIC-03 | trial start at create / at sign-up approval / go-live migration; ends -> `trial_ended` only for new machines; one trial per tenant across plan changes; extension audit; reminders 7/1 once each, partner notified | real-Mongo | `pytest tests/test_trial.py -q` (+ `tests/test_enrollment_controls.py::test_expiry_reminders_go_out_once_per_threshold` as the model) | no, Wave 0 |
| LIC-04 | plan ceiling refuses outside screens at Super Admin PATCH, create, partner create and tick; both ceilings for partner customers; kept screens survive downgrade; START features always allowed; seed tier counts pinned (19/69/120) | real-Mongo/unit | `pytest tests/test_plan_ceiling.py tests/test_partner_ceiling.py tests/test_tenant_feature_switches.py -q` | partly |
| LIC-05 | proxy-headers semantics (spoofed XFF ignored); network hold for new machine; enrolled agents never held; first network learned atomically (two concurrent enrollments -> one network); approve adds network, `widenTo` validation (contains IP, prefix floor); migration seeds from `publicIp`; IPv4-mapped normalization; tenant admin cannot approve | unit + real-Mongo | `pytest tests/test_network_rule.py tests/test_proxy_headers.py -q` | no, Wave 0 |
| LIC-06 | live duplicate in another tenant held (serial or UUID, MAC-only never); silent/Inactive copy does not block and is retired (D-38); approval retires A (Replaced, seat freed, tokens revoked); heartbeat of Replaced refused; neither org's name appears in the other's list/feed/ledger; reject does not denylist; indexes used (`explain`) | real-Mongo | `pytest tests/test_cross_tenant_duplicate.py -q` | no, Wave 0 |
| LIC-07 | Plans API: only Super Admin, validation, edit applies at once, route guard parity | route + manifest | `pytest tests/test_plan_endpoints.py tests/test_catalogue_route_parity.py tests/test_catalogue_manifest.py -q` | partly |
| UI | licence panel (plan, override mark, networks, trial days), Pending reasons + widen input, Plans screen, partner plan picker, Add Tenant default Free | vitest | `npx vitest run src/__tests__/PendingAgentsPanel.test.tsx src/__tests__/PartnerPortal.test.tsx src/__tests__/PlansScreen.test.tsx` | partly |
| Migration | 034 idempotent: plan docs, seats, trial, networks, indexes, old numbers recorded | real-Mongo | `pytest tests/test_migration_034_plans.py -q` | no, Wave 0 |

### Sampling Rate
- **Per task commit:** the quick run command above plus the new test file for the task.
- **Per wave merge:** full backend suite and `npx vitest run src/__tests__`.
- **Phase gate:** full suite green before `/gsd-verify-work`; browser/UAT items (Pending reason text, Plans screen) verified on the published UI by the user, per project practice ("verify UAT claims on the server").

### Wave 0 Gaps
- [ ] `tests/test_plan_seats.py`, `test_plan_change.py`, `test_plan_writers_scan.py`, `test_trial.py`, `test_plan_ceiling.py`, `test_network_rule.py`, `test_proxy_headers.py`, `test_cross_tenant_duplicate.py`, `test_plan_endpoints.py`, `test_migration_034_plans.py`
- [ ] A shared fixture that builds two tenants (A, B) with agents and install keys on `mongo_db`, reusing the `_register` harness (move it to a shared helper rather than importing from another test module)
- [ ] Framework install: none needed

## Security Domain

### Applicable ASVS Categories (level 1, `security_enforcement` enabled in `.planning/config.json`)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no new login flow); agent credentials/tokens revoked on retirement | existing `revoke_agent_tokens` |
| V3 Session Management | no | - |
| V4 Access Control | yes | Plans API behind `catalogue_guard` + Super Admin permission; approve/widen only `manage:pending_agents`; partner scoped by `current_partner`; tenant admins read-only on networks/plan; D-36 projection rules |
| V5 Input Validation | yes | Pydantic models; `ipaddress` parsing; CIDR prefix floor; plan names against the table; screen keys against `tenant_features.SWITCHABLE` |
| V6 Cryptography | no | - |
| V8/V9 Data protection / communication | yes (tenant isolation, forwarded headers) | raw-handle explicit filters; pinned `forwarded_allow_ips` |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Spoofed `X-Forwarded-For` to pick an allowed network | Spoofing | Decide on `request.client.host` behind trusted-hop-only uvicorn; pin config; test |
| Agent-claimed `publicIp` used for the decision | Spoofing | Server-observed address only |
| Forged hardware serial/UUID to retire or block another tenant's agent | Spoofing / DoS | Platform alert + dual-ledger audit on every cross-tenant retirement; consider restore operation (A4) |
| Cross-tenant name leak through shared notification/list/audit paths | Information disclosure | Unnamed tenant-facing variants; platform-only projection; leak tests |
| Tenant admin self-upgrade through the payment route | Elevation of privilege | Validate plan, never `Custom`, confirmation policy (Open Question 3) |
| CIDR widening typo allows a huge range | Tampering | Prefix floor, must contain the observed IP, audit |
| Replaced agent resurrects through heartbeat | Elevation / licence evasion | Token revocation + heartbeat refuses `Replaced` |
| Bulk plan update corrupts partner pool | Tampering | Filter excludes partner customers; reconcile drift test |

## Sources

### Primary (HIGH confidence) - files read and probes run this session
- `/etc/nginx/sites-enabled/omni-platform`, `/etc/nginx/proxy_params` (proxy headers); `ss -ltnp`; `/proc/<pid>/environ` names and cmdline of the running backend; `systemctl cat omni-backend`
- `backend/venv/lib/python3.12/site-packages/uvicorn/middleware/proxy_headers.py` and `config.py` (0.53.0); throwaway uvicorn probe (three header cases)
- `/var/log/nginx/access.log` (register requests from `103.174.161.233`) vs read-only MongoDB query of `omni_platform` (tenants, agents, indexes)
- `backend/license_rules.py`, `licensing.py`, `pending_agents.py`, `agent_allowlist.py`, `agent_registry_endpoints.py`, `agent_heartbeat_endpoints.py`, `seat_identity.py`, `machine_identity.py`, `asset_identity.py`, `tenant_features.py`, `feature_catalog.py`, `feature_bundles.py`, `bundle_endpoints.py`, `feature_flags.py`, `partner_platform_service.py`, `partner_portal_service.py`, `partner_pool.py`, `partner_store.py`, `tenant_docs.py`, `tenant_endpoints.py`, `tenant_signup_endpoints.py`, `authentication_endpoints.py` (sign-up block), `payment_billing_endpoints.py`, `pending_agent_endpoints.py`, `database.py` (wrapper), `notification_audience.py`, `audit_ledger.py`, `app_background_tasks.py`, `migrations/runner.py`, `migrations/033_machine_identities.py`, `tests/test_partner_license_writers.py`, `tests/_mongo_test_db.py`, `tests/test_enrollment_controls.py`, `tests/test_pending_agents.py`
- Scripts run: switch/catalogue mapping and tier seeding; MongoDB sparse-vs-partial index `explain` on mongod 8.0.34 (throwaway `omni_test_*` database, dropped); quick test run (57 passed)
- `.planning/phases/88-.../88-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` (Phase 88 section), `.planning/config.json`

### Secondary (MEDIUM confidence)
- none

### Tertiary (LOW confidence)
- none (assumptions are listed in the Assumptions Log)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new packages; versions read from the venv
- Architecture: HIGH - built on read code; the module split is a recommendation
- Pitfalls: HIGH for the verified ones (Pitfalls 1-6, 10); MEDIUM for A3-A5/A7 items flagged as assumptions

**Research date:** 2026-11-10
**Valid until:** 2026-12-10 for code facts (the working tree changes daily; re-check `agent_registry_endpoints.py` and `license_rules.py` before planning); nginx/uvicorn facts hold until the unit or nginx file is regenerated
