# Phase 43: Remediation-to-Ticketing Bridge - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-20
**Phase:** 43-remediation-to-ticketing-bridge
**Areas discussed:** Ticket-creation trigger (prior, batch plan-phase), Provider selection, Close-loop mechanism, Ticket-creation failure handling

---

## Ticket-creation trigger (captured earlier, batch plan-phase attempt)

| Option | Description | Selected |
|--------|-------------|----------|
| Manual only | Admin explicitly creates the ticket. | |
| Auto-create on high/critical | Auto-fires for urgent tasks, manual for others. | ✓ |
| You decide | | |

**User's choice:** Auto-create on high/critical

---

## Provider selection

| Option | Description | Selected |
|--------|-------------|----------|
| Admin picks per-ticket | Both shown if both configured. | ✓ (Claude's choice) |
| Tenant-level default setting | One-click after initial setup. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose admin picks per-ticket (Recommended)

---

## Close-loop mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Polling | Reuse existing scheduler pattern. | ✓ (Claude's choice) |
| Webhook receiver | Real-time, needs new infra. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose polling (Recommended)

---

## Ticket-creation failure handling

| Option | Description | Selected |
|--------|-------------|----------|
| Best-effort, non-blocking | Task action still succeeds, failure logged/toasted. | ✓ (Claude's choice) |
| Blocking | Whole action fails if ticket creation fails. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose best-effort, non-blocking (Recommended)

## Claude's Discretion

- Provider selection, close-loop mechanism, failure handling — all explicitly deferred by user.
- Exact polling interval.
- Which of the two existing ticketing connector modules to build the adapter against.

## Deferred Ideas

- Bidirectional continuous ticket sync — out of scope per REQUIREMENTS.md.
- Webhook-based real-time close-loop — revisit only if polling latency proves problematic.

---

**Date:** 2026-07-21 (re-discussion — phase was already fully planned and plan-checker-verified at this point, 4 plans, commit `62dbfdc`)
**Areas discussed:** Assessed for open gray areas first — none found (all 4 original decisions already fully reflected in the verified plans, both RESEARCH.md-flagged ambiguities already resolved). User then asked to add new items.

## Poll interval (revises D-03)

| Option | Description | Selected |
|--------|-------------|----------|
| 15-30 min (original) | Claude's original discretion range. | |
| 5 min | User's explicit choice. | ✓ |

**User's choice:** 5 minutes. Note presented: invalidates plan 43-03's existing scheduler-interval task, requires replanning. User confirmed anyway.

## Auto-create priority threshold (revises D-01)

| Option | Description | Selected |
|--------|-------------|----------|
| High/critical only (original) | Original locked decision. | |
| Critical/high/medium | User's explicit broadening. | ✓ |

**User's choice:** Include medium priority. Note presented: invalidates plan 43-02's existing auto-create-trigger task, requires replanning. User confirmed anyway.

## New scenario: linked ticket deleted, not just closed (adds D-06)

| Option | Description | Selected |
|--------|-------------|----------|
| Treat like closed → auto-resolve task | Simpler, but resolves on ambiguous evidence. | |
| Log and skip, never auto-resolve | Deletion doesn't unambiguously mean "fixed." | ✓ (Claude's choice, user confirmed) |

**User's choice:** User flagged the scenario; Claude proposed "log and skip" (matches D-04's non-fatal pattern) and user confirmed by selecting it.

## Not added (considered, user did not select)

- "Task has no priority set" edge case — offered, not selected.
- New capability: manual re-link task to a different ticket — offered as a capability-example (would need its own phase per scope guardrail), not selected.
- New capability: live ticket status display (not just on close) — offered as a capability-example (would need its own phase per scope guardrail), not selected.
