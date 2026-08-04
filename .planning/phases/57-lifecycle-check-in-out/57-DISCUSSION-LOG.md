# Phase 57: Lifecycle & Check-In/Out - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-04
**Phase:** 57-Lifecycle & Check-In/Out
**Areas discussed:** Assignee model, Location field reuse, Overdue-audit threshold, Checkout metadata

---

## Assignee model

| Option | Description | Selected |
|--------|-------------|----------|
| Platform Users only | Reuses `backend/models.py` User + users collection. No new catalog kind needed. | ✓ |
| Users + lightweight Person record | Adds a new catalog-style "people" entity (name/email/dept, no auth) alongside platform Users. | |

**User's choice:** Platform Users only
**Notes:** Everyone who touches assets already has a login in this platform — no need for a non-login Person record in v1.

---

## Location field reuse

| Option | Description | Selected |
|--------|-------------|----------|
| Overwrite locationId | One field = current whereabouts, whether home storage or a checked-out location. | ✓ |
| Separate assignedLocationId | Keeps locationId as a fixed "home base" and adds a distinct field for the current checkout location. | |

**User's choice:** Overwrite locationId
**Notes:** Simplest model. Original home-location value remains recoverable from the append-only assignment history if ever needed.

---

## Overdue-audit threshold

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed default, e.g. 12 months | Hardcoded interval since last audit (or since creation if never audited). | ✓ |
| Per-tenant configurable | Add a tenant-level setting for the audit interval. | |
| Per-model configurable | Audit interval varies by asset Model. | |

**User's choice:** Fixed default, 12 months
**Notes:** Simplest for v1, no new settings surface needed.

---

## Checkout metadata

| Option | Description | Selected |
|--------|-------------|----------|
| Note + expected-return date | Both optional fields on the checkout transaction. | ✓ |
| Bare who/where/when only | Matches the requirement text exactly, smallest surface for v1. | |

**User's choice:** Note + expected-return date
**Notes:** Expected-return date is what makes a future "overdue check-out" report possible without a later schema change.

---

## Claude's Discretion

- Assignment-history collection/schema shape (separate collection vs. embedded array)
- Checkout/checkin endpoint routes and request/response contracts
- How the overdue-audit report is computed (live query vs. precomputed)

## Deferred Ideas

- Non-login "Person" checkout targets (contractors without platform accounts) — revisit if usage shows a gap.
- Per-tenant or per-model configurable audit interval — fixed default chosen for v1.
