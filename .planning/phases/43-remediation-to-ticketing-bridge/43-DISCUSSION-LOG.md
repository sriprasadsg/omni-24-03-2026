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
