# Phase 81: Autonomy Gate, Stop Switch & Activity Ledger - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-25
**Phase:** 81-autonomy-gate-stop-switch-activity-ledger
**Areas discussed:** Turning it on, Who can do what, Stop switch behaviour, Safety limits
**Todo folded:** Fix stale capability-count assertions in integration.rs (user chose "Yes, fold it in" over "No, leave it")

---

## Turning it on

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Level for the 4 existing tenants at migration | Undoable-auto (same as new) / Suggest / Off | Undoable-auto ✓ |
| How shadow mode works | Server master + per tenant / Server setting only / Per tenant only | Server master + per tenant ✓ |
| Who may lift shadow for a tenant | Super Admin only / Super Admin or tenant admin | Super Admin only ✓ |
| Is the Platform tenant ever eligible | Never in v4.3 / Eligible like any tenant | Never in v4.3 ✓ |

**Notes:** Nothing acts until a Super Admin ticks the screen for a tenant; shadow mode is on regardless.

---

## Who can do what

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Default roles that may change the level | Tenant Admin only / Tenant Admin + Incident Responder | Tenant Admin only ✓ |
| Default roles that may approve/deny/undo | Admin + Security Analyst + Incident Responder / Tenant Admin only / Admin + Incident Responder | Admin + Security Analyst + Incident Responder ✓ |
| Approve/undo requires MFA | Yes, require MFA / No | Yes ✓ |
| Who can view the screen | Approvers + Auditor + Analyst / Approvers only / All tenant roles | Approvers + Auditor + Analyst ✓ |
| Autonomy permissions in custom roles | Yes, within the usual ceiling / No, built-in only | Yes, within ceiling ✓ |
| Platform Support across tenants | View all, approve none / Super Admin only / View and approve | View all, approve none ✓ |
| API keys | No, signed-in people only (may read and press stop) / Yes, if scoped | No, signed-in people only ✓ |

**Notes:** User asked for a second round of questions in this area. Consequence noted to the user: Security Analyst and Incident Responder users will be prompted to enrol MFA.

---

## Stop switch behaviour

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Who may press a tenant stop | Anyone who can approve / Tenant Admin only | Anyone who can approve ✓ |
| Who may clear a stop | Level changers only / Whoever can press it | Level changers only ✓ |
| What still works during a stop | Undo yes, approve no / Both still work / Nothing works | Undo yes, approve no ✓ |
| Approval expiry clock during a stop | Keeps running / Paused | Keeps running ✓ |
| Does a stop clear itself | Never / After a set time | Never ✓ |
| Visibility of an active stop | Banner + on-call alert / Autonomous Ops screen only | Banner + on-call alert ✓ |

---

## Safety limits

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Approval expiry | 24 hours / 7 days / 4 hours | 24 hours ✓ |
| Hosts per automatic decision | 1 host, more needs approval / Up to 5 / Up to 10% of tenant | 1 host ✓ |
| Circuit breaker trip | 3 in a row within 24 h / 5 in a row within 24 h / 30% of last 10 | 3 in 24 h ✓ |
| Breaker recovery | A person restores it / Automatically after 24 h | A person restores it ✓ |
| Never-touch list editors | Super Admin + own tenant admin / Super Admin only | Super Admin + own tenant admin ✓ |
| Per-tenant rate limit | 20 per hour, then pause / 50 per hour / No rate limit | 20 per hour ✓ |

---

## Claude's Discretion

- Exact permission strings and route shapes (within CONTEXT D-05); ledger schema, trace format, state names.
- Rolling window vs clock hour for the rate limit; definition of "management network".
- Decision-record retention length (longer than generic retention; 365 days suggested).
- Delete vs leave-unreachable for the legacy LLM code (deletion preferred).
- Read-only screen layout and copy; test structure; optional `hypothesis` dev dependency.

User was offered further gray areas (screen placement, record retention, legacy-code deletion) and chose "I'm ready for context", leaving these to Claude's discretion.

## Deferred Ideas

None beyond the milestone's later phases.
