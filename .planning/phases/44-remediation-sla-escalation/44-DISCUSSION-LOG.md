# Phase 44: Remediation SLA & Escalation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-20
**Phase:** 44-remediation-sla-escalation
**Areas discussed:** SLA schema (prior, batch plan-phase), SLA threshold definition, Escalation target, Escalation tiers/repeat behavior

---

## SLA schema (captured earlier, batch plan-phase attempt)

| Option | Description | Selected |
|--------|-------------|----------|
| New fields | sla_status/escalated/escalation_level, doesn't touch existing status/priority. | ✓ |
| Reuse priority/status | Fewer new fields, risks collision. | |
| You decide | | |

**User's choice:** New fields (Recommended)

---

## SLA threshold definition

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable per-tenant | Mirrors STALE-02 precedent. | ✓ (Claude's choice) |
| Fixed threshold | Hardcoded, simpler. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose configurable per-tenant (Recommended)

---

## Escalation target

| Option | Description | Selected |
|--------|-------------|----------|
| Assignee + all tenant admins | No manager-of-assignee concept exists; admins are closest analog. | ✓ (Claude's choice) |
| Assignee only | Simpler, less visibility. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose assignee + admins (Recommended)

---

## Escalation tiers/repeat behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Tiered | escalation_level increments at 1/3/7 day intervals. | ✓ (Claude's choice) |
| One-time only | Single notification, simpler. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose tiered (Recommended)

## Claude's Discretion

- SLA threshold definition, escalation target, escalation tiers — all explicitly deferred by user.
- Exact tier day-boundaries.
- Default at-risk window value.

## Deferred Ideas

None — discussion stayed within phase scope.
